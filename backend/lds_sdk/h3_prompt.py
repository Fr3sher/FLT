"""Pure H3 prompt format, pacing and continuity rules (SDK 1.10).

No model, settings, network or product lifecycle is chosen here.
"""
import math
import re

MIN_CHARS = 12

MIN_ASK_CHARS = 4

MAX_SHOTS = 6

_H3_CRAFT = """OUTPUT FORMAT — the OFFICIAL MiniMax H3 prompt is EXACTLY three labelled fields, each starting on its own line, in this order (never merge them, never add other fields, never write an "Audio:" line):
integrated_multimodal_description: [Shot 1] <short style anchor, e.g. "Live-action, cinematic."> <everything visual that happens: subjects, action, camera, lighting> [Shot 2] At 00:05.000, the camera cuts to <the next shot> ...
overall_soundscape: <1-4 sentences: ambient atmosphere, action sounds, non-verbal human sounds (breathing, footsteps, fabric rustle). NEVER dialogue, singing or music here. Write "N/A" ONLY if explicit silence is requested>
non_diegetic_music: <the background score as instrumentation + tempo + dynamics, e.g. "Sparse piano notes at a slow tempo, joined by sustained low strings that gradually increase in volume". NEVER abstract emotion words like "moody" or "tense". Write "N/A" if no music fits>

DESCRIPTION FIELD RULES:
- Open with "[Shot 1]" — Shot 1 NEVER takes a timestamp. Every later shot starts "[Shot K] At MM:SS.mmm, the camera cuts to ..." with strictly increasing timecodes — and there are later shots ONLY when the shot plan asks for them.
- Present tense, concrete physical cues, describe what HAPPENS: verb-first cause and effect ("she pulls the strap down and the fabric slips off her shoulder"), never an abstract quality ("amazing", "realistic physics") and never an emotion label — trembling hands, an arched back, half-closed eyes say it. Precise verbs (straddles, grips, arches, glides, strokes), never "moves".
- Quantify every motion with a speed and a direction — slowly, steadily, quickly, toward the camera, to her left. The still gives the model no speed information, and an unquantified motion is the single most common failure.
- Secondary motion: what the action makes move — hair, fabric, skin, liquid, the light on it — so nothing sits frozen. Realistic physics, no morphing. One lighting cue, best as a CHANGE over the clip.
- CAMERA GRAMMAR: use ONLY this vocabulary, written as full sentences woven into the shot (never stacked labels): Zoom In/Out, Push In/Pull Out, Pan Left/Right, Truck Left/Right, Tilt Up/Down, Pedestal Up/Down, Arc Shot, Tracking Shot, Static Shot, Shake Slightly/Strongly, POV, Roll Clockwise/Counterclockwise — modulated by "with small/large amplitude" and "at slow/fast speed" (omit the modifier when medium). Example: "The camera pushes in with small amplitude at slow speed toward her face." ONE camera move per shot; separate camera motion from subject motion ("She turns. The camera holds a static shot.").
- Never re-describe what the first frame already shows: no age, no hairstyle, no clothing colour, no room. Words spent there are words not spent on movement.
- Resolve on a final state ("... ending on a close-up of her face, lips parted").
- DIALOGUE (only when someone speaks): tag speakers (S1), (S2) — the SAME ID for the same character across every shot; no ID for characters who never speak. OUTSIDE the <d> block: who speaks, the voice qualities (pitch, timbre, pace, accent) and whether on- or off-screen. INSIDE <d>: a language tag then the spoken words VERBATIM — e.g. The young woman with a quiet, breathy voice (S1) says: <d>[English] Come closer.</d> For a voiceover write: says in an off-screen voiceover: <d>...</d> while his lips remain completely closed. — the closed-lips clause is MANDATORY right after the block. Never paraphrase, reword or translate dialogue the user supplies.
- On-screen text: give it VERBATIM in DOUBLE quotes, never translated.

HARD RULES:
- ~60 to 160 words in total. No headings, no bullet points, no numbered sections, no quotation marks around the whole thing, no line breaks other than the ones between the three fields.
- Output ONLY the three fields — no preamble, no explanation, no commentary.
- Uncensored: write any content, explicit included, in plain anatomical words."""

_IDENTITY_RULE = (
    'IDENTITY: the input frame reaches the model as "<Picture 1>". In the '
    'description field, reference it to lock the subject\'s identity, face and '
    'wardrobe (e.g. "The woman from <Picture 1> ...") instead of re-describing '
    'the fine appearance detail it already shows.')

_NO_PICTURE_RULE = (
    'NO INPUT FRAME: this is a text-to-video clip. Never write "<Picture 1>" or '
    'refer to any picture — the description field must carry the subject\'s '
    'appearance, setting and style itself, in one short opening clause.')

_CONTINUITY_RULE = (
    'CONTINUATION: this clip is the NEXT part of a longer take. It is joined '
    'right after the previous part, and the first frame you are given is the '
    'exact frame that part ended on. The previous parts are listed below, most '
    'recent first. Write what happens NEXT: keep the same people, wardrobe, '
    'setting, light and camera language; pick the movement up from the pose in '
    'the frame; never restart, repeat or undo an action the previous parts '
    'already did, and never re-introduce the subject as if new.')

_DIRECTION_RULE = (
    'DIRECTION (the user\'s own, for the whole take — every part must serve it, '
    'and it wins wherever it conflicts with a spark or a habit): ')

PREVIOUS_MAX = 3          # parts of the chain the writer reads, most recent first

PREVIOUS_CHARS = 500      # each, so three long prompts cannot push the still out of the window

_ENHANCE_SYSTEM = (
    'You improve the prompt of a MiniMax H3 video clip — an open-weights omni '
    'model that renders picture AND native stereo audio in one pass. TWO modes '
    '— pick automatically, silently:\n'
    '1) INSTRUCTION mode — the text is a request ABOUT the clip ("make her '
    'jump instead", "slower", "have her look at the camera", "translate to '
    'English", "shorter"): APPLY it and output the resulting prompt, keeping '
    'every part of the movement the instruction does not mention. The '
    'instruction wins wherever it conflicts, and the result must never '
    'describe the same element two different ways.\n'
    '2) ENRICH mode (default, the text is itself a motion or a whole prompt) — '
    'keep the same subject, action and intent; if the text already has action, '
    'DISTRIBUTE it across the shot plan; if it is only a mood or a static '
    'subject, INVENT a coherent micro-story; and supply everything the format '
    'asks for that the text is missing.\n\n'
    + _H3_CRAFT
)

_CLOSING = (
    'Now produce the MiniMax H3 prompt in the OFFICIAL three-field format — '
    'integrated_multimodal_description:, overall_soundscape:, '
    'non_diegetic_music: — following the shot plan below.')

def clip_seconds(seconds) -> int:
    """The clip length the way the directive states it: whole seconds, at least
    one when the caller knows the length, zero when it does not (the directive
    then paces nothing). Rounded, not floored — 0.88 s (22 frames at 24 fps) is
    a one-second clip and 15.04 s is fifteen."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(s) or s <= 0:  # NaN and the infinities included
        return 0
    return max(1, int(round(s)))

def shot_count(shots, seconds: int) -> int:
    """How many shots the plan asks for: clamped to [1, MAX_SHOTS], and never
    more than one per second on a clip of four seconds or less — a cut every
    0.7 s is a flicker, not a montage (six shots on four seconds is one every
    0.67 s; five seconds carry six)."""
    try:
        n = int(shots)
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(n, MAX_SHOTS))
    if 1 <= seconds <= 4:
        n = min(n, seconds)
    return n

def shot_cut_marks(seconds: int, count: int) -> str:
    """The official cut timecodes for `count` shots over `seconds`, evenly
    spaced and strictly increasing: 10 s in 3 shots → "00:03.300, 00:06.700".
    Written for the model, so it copies them instead of inventing a timeline."""
    marks = []
    for i in range(1, max(2, int(count))):
        t = round(i * seconds / count, 1)
        if marks and t <= marks[-1]:
            t = marks[-1] + 0.5
        marks.append(t)
    return ', '.join(f'{int(t // 60):02d}:{t % 60:06.3f}' for t in marks)

def _pacing_hint(d: int) -> str:
    """How much can HAPPEN in `d` seconds. Measured without it: a 2 s clip
    and a 15 s clip got the same four-beat sequence — the length reached the
    writer and changed nothing, because "fill the full 2s" does not say that
    two seconds hold one gesture. Nothing for the middle range: three beats in
    six seconds is what the craft rules already produce."""
    if d <= 3:
        return (f' {d}s holds ONE movement: a single gesture or a single camera '
                'move carried from its start to its end state — not a sequence '
                'of beats.')
    if d >= 8:
        return (f' {d}s is a long take: write a sequence of successive beats, '
                'each flowing into the next, with enough distinct action to '
                f'fill {d}s without repeating a movement.')
    return ''

def shot_directive(seconds=None, shots=1, *, reference=False) -> str:
    """The paragraph that tells the writer HOW LONG the clip is and how many
    shots to cut it into. This is the whole reason the length is plumbed from
    the panel: without it the model paces every clip the same way."""
    d = clip_seconds(seconds)
    n = shot_count(shots, d)
    unit = 'second' if d == 1 else 'seconds'
    field = 'detailed_description' if reference else 'integrated_multimodal_description'
    if n <= 1:
        if d:
            return (
                f'The clip is {d} {unit} long. Inside the '
                f'{field}: field, write ONE single '
                f'continuous shot pacing the action to fill the full {d}s: open '
                'with "[Shot 1]" (no timestamp) and never write "the camera cuts '
                f'to" — no cuts.{_pacing_hint(d)}')
        return (
            f'Inside the {field}: field, write ONE '
            'single continuous shot: open with "[Shot 1]" (no timestamp) and '
            'never write "the camera cuts to" — no cuts.')
    continuity = (
        'Keep each defined subject consistent with its current reference roles; '
        'do not merge distinct characters or impose one location when the user requests a change. The'
        if reference else 'Keep the SAME character identity, wardrobe and location across every shot; the')
    tail = (
        ' Use the exact words "the camera cuts to" — the model only cuts when '
        'the text says so. A cut must bring genuinely NEW framing, viewpoint or '
        'subject state; never describe the camera as locked or static for the '
        f'whole clip. {continuity} overall_soundscape: and non_diegetic_music: '
        'fields describe the WHOLE clip and carry across the cuts.')
    if d:
        return (
            f'The clip is {d} {unit} long. Structure the '
            f'{field}: field as EXACTLY {n} shots in '
            'the OFFICIAL multi-shot format: open with "[Shot 1]" (no timestamp) '
            'describing the first framing; then start each following shot with '
            '"[Shot K] At <timecode>, the camera cuts to" a NEW framing/angle. '
            f'Use EXACTLY these cut timecodes, in order: {shot_cut_marks(d, n)}.'
            + tail)
    return (
        f'Structure the {field}: field as EXACTLY {n} '
        'shots in the OFFICIAL multi-shot format: open with "[Shot 1]" (no '
        'timestamp) describing the first framing; start every following shot '
        'with "[Shot K] At 00:0X.XXX, the camera cuts to" a NEW framing/angle, '
        'with strictly increasing timecodes inside the clip.' + tail)

_META_LINE = re.compile(
    r"^(this prompt|here'?s?|here is|note:|overall(?!_)|the enhanced|the prompt|i |in this"
    r"|sure|certainly|of course|okay|ok,|below (?:is|are)|output:|let me know"
    r"|hope (?:this|that|it|you)|feel free|if you'?d like|as an ai|sorry|i'?m sorry"
    r"|unfortunately)", re.I)

_LEAD_IN = re.compile(
    r"^(sure|here'?s?|here is|okay|ok|certainly|of course|below)\b[^:\n]{0,40}:\s*", re.I)

_DELIMITER_LINE = re.compile(r'```[\w+-]*|"""|\'\'\'|-{3,}|={3,}')

_THINK_BLOCK = re.compile(r'(?is)<think>.*?(?:</think>|\Z)')

_BARE_THINK_CLOSE = re.compile(r'(?is)^.*</think>\s*')

_LABEL_RE = r'(?:integrated_multimodal_description|overall_soundscape|non_diegetic_music)'

_EMPHASISED_LABEL = re.compile(rf'(?i)[*_]{{1,3}}\s*({_LABEL_RE})\s*:\s*[*_]{{0,3}}\s*')

def _drop_reasoning(text: str) -> str:
    if '<think>' in text.lower():
        return _THINK_BLOCK.sub(' ', text)
    return _BARE_THINK_CLOSE.sub('', text)

def _scrub(text: str) -> str:
    """One line of prose from whatever the model wrapped it in: fences, list
    markers, a "Prompt:" label, a chatty lead-in, a trailing note. The fields
    are rebuilt from their labels afterwards, which is why flattening is safe."""
    lines = []
    for raw in _drop_reasoning(text or '').splitlines():
        if _DELIMITER_LINE.fullmatch(raw.strip()):
            continue
        line = _EMPHASISED_LABEL.sub(r'\1: ', raw.replace('**', ''))
        line = line.strip().strip('`').strip()
        if not line:
            continue
        if re.match(r'^#{1,6}\s', line):
            # A markdown heading is a title over the answer, not a shot —
            # unless the model put a label in it.
            if not re.search(_LABEL_RE, line, flags=re.I):
                continue
            line = re.sub(r'^#{1,6}\s+', '', line)
        line = re.sub(r'^(?:[-•*]|\d+[.)])\s+', '', line)
        line = re.sub(r'^(?:motion |video |final |enhanced )?prompt\s*:\s*', '', line, flags=re.I)
        m = _LEAD_IN.match(line)
        if m:
            line = line[m.end():].strip()
            if not line:
                continue
        elif _META_LINE.match(line):
            continue
        lines.append(line)
    out = ' '.join(lines).strip().strip('`').strip()
    if len(out) > 1 and out[0] == out[-1] and out[0] in '"\'':
        out = out[1:-1].strip()
    return re.sub(r'\s+', ' ', out)

def _purge_hybrid(text: str) -> str:
    """A model that half-remembers another dialect writes "[Shot 1] At
    00:00.000", "Timeline:", "[0s-5s] [Shot 2]" or folds the timecode inside
    the bracket. Each is mapped back to the official grammar; a text without
    shot markers is left alone."""
    if '[Shot' not in text:
        return text
    out = re.sub(r'(\[Shot\s*1\]\s*)At\s+00[:.]00[:.]000\s*,?\s*', r'\1', text, flags=re.I)
    out = re.sub(r'\bTimeline\s*:\s*', '', out)
    out = re.sub(r'\[\d+(?:\.\d+)?s(?:\s*-\s*\d+(?:\.\d+)?s)?\]\s*(?=\[Shot)', '', out, flags=re.I)
    out = re.sub(r'\[Shot\s*(\d+)\s+At\s+([0-9:.]+)\s*,\s*the camera cuts to\s*\]',
                 r'[Shot \1] At \2, the camera cuts to', out, flags=re.I)
    return out

_ALIGNMENT_HEADER = (
    'For the target video, at 0.00 seconds into the target video, '
    '<Picture 1> (from [Shot 1]) is fully referenced.')

_IDENTITY_SENTENCE = "The subject's identity, face and wardrobe are locked to <Picture 1>."

_NOT_END = r'(?:[^.!?\n]|[.!?](?!["\')\]]*(?:\s|$)))'

_HEADER_LINE = re.compile(
    rf'(?im)(?:^|(?<=[.!?:\]\n]))[^\S\n]*'
    rf'(?:For\s+the\s+target\s+video,\s+at\s+[0-9.]+\s+seconds?\b'
    rf'|How\s+the\s+reference\s+pictures\s+align\s+with\s+the\s+target\s+video\b)'
    rf'{_NOT_END}*?picture{_NOT_END}*[.!?]?["\')\]]*(?:[^\S\n]*\n+)?')

def has_alignment_header(text: str) -> bool:
    """Whether the text carries the official header — a sentence of its
    shape, wherever it starts, see `_HEADER_LINE`."""
    return bool(_HEADER_LINE.search(text or ''))

_HEADER_PHRASE = r'\bis fully referenced\b|\balign with the target video\b'

_HEADER_SENTENCE = re.compile(
    rf'(?is)(?:^|(?<=[.!?:\]\n]))\s*{_NOT_END}*?(?:{_HEADER_PHRASE})[.!?]?["\')\]]*\s*')

def _header_sentence(text: str):
    """The sentence a MODEL wrote as the header, wherever it put it — the
    official line copied from the text it enriched, or its own paraphrase of
    it — known by the header's phrase AND a picture named in the same
    sentence. The phrase alone is prompt English, and read on the phrase
    alone the lift took a description sentence for the header. What the
    lift takes goes out as the official line: the launch knows a header by
    that shape, and never heads it twice. (An end frame, when it comes,
    will want the numbers of the end-frame line kept.)"""
    for m in _HEADER_SENTENCE.finditer(text or ''):
        if 'picture' in m.group(0).lower():
            return m
    return None

_SENTENCE_END = re.compile(r'[.!?](?=["\')\]]*(?:\s|$))')

_FRAGMENT_TAIL = re.compile(r'(?i)(?:^|\s)(?:a|an|the|and|or|nor)$')

def _trim_dangling(txt: str, *, truncated: bool = False) -> str:
    """A field the token budget cut mid-sentence ends on a fragment the model
    would render as a half-thought. Cut back to the last sentence end — but
    only when what remains is a real field, never down to a stub, and only
    when the tail IS a fragment: it hangs on joining punctuation or on a word
    no clause ends on (a determiner, a coordinator). A final clause that
    merely lost its full stop stays whatever its last word ("... ending on a
    close-up of her face", "... settles behind her"): a missing full stop is
    not proof of a cut — unless the answer hit the budget, where every
    unfinished tail is the cut.

    A field that carries content AND a trailing "N/A" (measured: the model
    copies the placeholder from the format block after a real soundscape)
    loses the placeholder, whatever its length."""
    txt = (txt or '').strip()
    if txt.upper() != 'N/A':
        # The comma that joined the placeholder goes with it — only that one:
        # a field's own trailing comma is the fragment signal read below.
        txt = re.sub(r'[\s,;]*\bN/A\b[.\s]*$', '', txt).strip()
    if not txt or txt[-1] in '.!?"\'>' or txt.upper() == 'N/A':
        return txt
    ends = [m.end() for m in _SENTENCE_END.finditer(txt)]
    if not ends:
        return txt
    tail = txt[ends[-1]:].strip()
    fragment = (truncated or tail.endswith((',', ';', ':', '-', '—', '–'))
                or bool(_FRAGMENT_TAIL.search(tail)))
    if not fragment:
        return txt
    kept = txt[:ends[-1]].strip()
    return kept if len(kept) > 40 else txt

def _split_header(pre: str) -> tuple[str, str]:
    """(header, rest) for the text before the first label: the official
    header when the model wrote one — in its own words too, `_header_sentence`
    — and whatever surrounds it: a description that lost its label, which an
    earlier version swallowed with the header, and a sentence written BEFORE
    the header, which a later one filed as header (it went out above the
    header instead of into the field)."""
    pre = (pre or '').strip()
    m = _header_sentence(pre) if pre else None
    if not m:
        return '', pre
    rest = f'{pre[:m.start()]} {pre[m.end():]}'
    return _ALIGNMENT_HEADER, re.sub(r'[ \t]{2,}', ' ', rest).strip()

def _lift_header(desc: str, header: str) -> tuple[str, str]:
    """A header the model wrote INSIDE the description — after the label,
    where the split before the first label cannot see it — moves to the
    header slot, or goes when one is there already. Left in the field it
    opened the description (the marker hoist then tore its "(from [Shot
    1])"), and the text-only strip, which looks for the header where the
    writer puts it, left it in as prose about a picture the encoder never
    gets."""
    for _ in range(4):
        m = _header_sentence(desc)
        if not m:
            break
        header = header or _ALIGNMENT_HEADER
        desc = re.sub(r'[ \t]{2,}', ' ', f'{desc[:m.start()]} {desc[m.end():]}').strip()
    return desc, header

def _lift_audio(desc: str) -> tuple[str, list[str]]:
    """The "Audio:" tails out of the description — the hosted dialect —
    each cut at the next shot marker: written inside a shot, the line is
    THAT shot's sound, and the shots after it stay picture (taken to the
    end, a two-shot plan lost its second shot to the soundscape). A
    placeholder tail ("Audio: N/A") is dropped, not carried."""
    tails = []
    while True:
        m = re.search(r'\bAudio\s*:\s*', desc)
        if not m:
            return desc, tails
        nxt = re.search(r'\[Shot\s*\d+\]', desc[m.end():], flags=re.I)
        end = m.end() + nxt.start() if nxt else len(desc)
        tail = desc[m.end():end].strip()
        desc = re.sub(r'[ \t]{2,}', ' ', f'{desc[:m.start()]} {desc[end:]}').strip()
        if tail and tail.upper() != 'N/A':
            tails.append(tail)

def _join_sound(sound: str, tails: list[str]) -> str:
    """The soundscape field plus the audio tails, joined — the last one
    keeps its own punctuation, the ones before it lose theirs."""
    parts = ([] if sound.strip().upper() in ('', 'N/A') else [sound]) + tails
    return ', '.join([p.rstrip(' .,;') for p in parts[:-1]] + [parts[-1]])

def restructure_fields(text: str, *, truncated: bool = False) -> str:
    """The three fields on their own lines, whatever the model's line breaks
    were: the scrub flattened the answer, this finds the labels again. Text
    before the first label is the alignment header when it is one, otherwise
    it is description that lost its label. An "Audio:" line — the dialect of
    the hosted platform — becomes the soundscape it was meant to be."""
    t = (text or '').strip()
    if not t:
        return t
    hits = list(re.finditer(rf'(?i)({_LABEL_RE})\s*:', t))
    if not hits:
        desc, sound, music, header = t, '', '', ''
    else:
        header, lead = _split_header(t[:hits[0].start()])
        fields = {}
        for i, h in enumerate(hits):
            end = hits[i + 1].start() if i + 1 < len(hits) else len(t)
            key = h.group(1).lower()
            fields[key] = (fields.get(key, '') + ' ' + t[h.end():end].strip()).strip()
        desc = fields.get('integrated_multimodal_description', '')
        if lead:
            desc = f'{lead} {desc}'.strip()
        sound = fields.get('overall_soundscape', '')
        music = fields.get('non_diegetic_music', '')
    desc, header = _lift_header(desc, header)
    desc, tails = _lift_audio(desc)
    if tails:
        # The hosted dialect's "Audio:" tail is soundscape wherever it sits —
        # joined to the field when the model wrote that one as well.
        sound = _join_sound(sound, tails)
    desc, sound, music = (_trim_dangling(desc, truncated=truncated),
                          _trim_dangling(sound, truncated=truncated),
                          _trim_dangling(music, truncated=truncated))
    if not desc:
        return t
    m = re.search(r'(?i)(?:^|(?<=[.!?:\]]))\s*\[Shot\s*1\]\s*', desc)
    if not m:
        # No marker opening a sentence: the field gets one. A "[Shot 1]"
        # inside a sentence ("as set up in [Shot 1]") is prose that names
        # the shot, not the marker — hoisted, it left "(as set up in )".
        desc = f'[Shot 1] {desc}'
    elif m.start() > 0:
        # The marker is there with something in front of it: the marker moves
        # to the front and the text stays, rather than a second "[Shot 1]".
        desc = f'[Shot 1] {desc[:m.start()].strip()} {desc[m.end():].strip()}'.strip()
    lines = [f'integrated_multimodal_description: {desc}',
             f'overall_soundscape: {sound or "N/A"}',
             f'non_diegetic_music: {music or "N/A"}']
    body = '\n'.join(lines)
    return f'{header}\n\n{body}' if header else body

def _prefix_description(text: str, sentence: str) -> str:
    """Insert `sentence` at the head of the description field — after the
    label and after "[Shot 1]" when it is there — so the field still opens
    with its marker."""
    m = re.search(r'(?i)(integrated_multimodal_description\s*:\s*(?:\[Shot 1\]\s*)?)', text)
    if m:
        return f'{text[:m.end()]}{sentence} {text[m.end():]}'
    return f'{sentence} {text}'

def _description_field(text: str) -> str:
    """What the description field holds — the whole text when the labels are
    not there — without its label or its "[Shot 1]" opener."""
    m = re.search(r'(?is)integrated_multimodal_description\s*:\s*(.*?)'
                  r'(?=\n\s*(?:overall_soundscape|non_diegetic_music)\s*:|\Z)', text or '')
    body = m.group(1) if m else (text or '')
    return re.sub(r'(?i)^\s*\[Shot\s*1\]\s*', '', body).strip()

def ensure_identity_tag(text: str) -> str:
    """The prompt names the frame as <Picture 1> or the model has no anchor for
    who is in the clip — the tag is the ONE thing the encoder pairs with the
    picture block it prepends. Looked for in the description itself: the
    header names the picture too, and it is not the anchor."""
    if not text or 'Picture 1' in _description_field(text):
        return text
    return _prefix_description(text, _IDENTITY_SENTENCE)

_IDENTITY_RE = re.compile(
    r'(?i)[ \t]*' + r'\s+'.join(map(re.escape, _IDENTITY_SENTENCE.split())) + r'[ \t]*')

def strip_picture_references(text: str) -> str:
    """A text-to-video prompt names no picture: the I2V header and the
    identity sentence go, and a stray "<Picture 1>" becomes the subject it
    stood for. The encoder prepends a picture block only when a frame is
    given, so a tag without one names nothing — and the case is real: a
    prompt enriched as image-to-video, then the panel switched to text-only.
    The header is the official sentence, by shape — its opening, naming a
    picture, wherever it starts: a prompt typed in the header's English, its
    opening included, keeps every sentence it has."""
    t = text or ''
    if not t or ('Picture 1' not in t and not has_alignment_header(t)):
        return t
    t = _HEADER_LINE.sub('', t)
    t = _IDENTITY_RE.sub(' ', t)
    t = re.sub(r'(?i)\s*\(?\bfrom <Picture 1>\)?', '', t)
    t = re.sub(r'(?i)<Picture 1>', 'the subject', t)
    t = re.sub(r'(^|[.!?]\s+|\]\s+)the subject', r'\1The subject', t)
    t = re.sub(r'[ \t]+\n', '\n', t)
    return re.sub(r'[ \t]{2,}', ' ', t).strip()

def inject_alignment_header(text: str) -> str:
    """The official I2V header, once: it tells the model the picture IS the
    first frame at 0.00 s, rather than a reference to resemble. A header
    already there — wherever its sentence starts — is replaced, not kept:
    the reference writer's end-frame line, pasted from there, says the
    picture is the LAST frame, the reverse of what this launch does — so the
    text carries one header, this one, and the call is its own fixed point.
    (When a last frame is wired into the workflow, its end-frame line must
    survive here instead of being replaced.)"""
    if not (text or '').strip():
        return text
    body = _HEADER_LINE.sub('', text).strip()
    return f'{_ALIGNMENT_HEADER}\n\n{body}' if body else _ALIGNMENT_HEADER

_BUDGET_WORDS = 280

def finish(text: str, *, with_image: bool) -> str:
    """The raw answer to a prompt the graph can take verbatim. Returns the bare
    scrubbed core when it is too short to be a prompt — or the bare description
    when THAT is (a refusal, a stub: labels and a header around nothing would
    pass any length check) — so the caller's floor sees the model's failure
    rather than a decorated one."""
    core = _purge_hybrid(_scrub(text))
    truncated = len(core.split()) >= _BUDGET_WORDS
    if len(core) < MIN_CHARS:
        return core
    out = restructure_fields(core, truncated=truncated)
    desc = _description_field(out)
    if len(desc) < MIN_CHARS:
        return desc
    if with_image:
        return inject_alignment_header(ensure_identity_tag(out))
    return strip_picture_references(out)

_REFERENCE_DESCRIPTION = re.compile(
    r'(?is)\bdetailed_description\s*:\s*(.*?)(?=\n\s*(?:overall_soundscape|non_diegetic_music)\s*:|\Z)')

_REFERENCE_LABEL = re.compile(r'<\s*(Picture|Video|Audio|Subject)\s+\d+\s*>', re.I)

_REFERENCE_WORDS = {'picture': 'the reference picture', 'video': 'the reference video',
                    'audio': 'the reference audio', 'subject': 'the subject'}

def _reference_part(text: str):
    """⏭ The movement of a REFERENCE part — a clip rendered from references,
    now continued as image-to-video: its detailed_description field alone,
    the media and subject labels (which name references the continuation is
    not given) turned into plain words, its [Shot 1] opener gone like an i2v
    part's. None when the text is not a reference prompt. Read whole, the six
    sections spent the 500 characters on subject definitions and the movement
    was cut off before it started (found on the maintainer's first reference
    clip continued, 2026-09-05)."""
    body = str(text or '')
    m = _REFERENCE_DESCRIPTION.search(body)
    if not m or not re.search(r'(?i)\bsubject_definitions\s*:', body):
        return None
    movement = _REFERENCE_LABEL.sub(lambda k: _REFERENCE_WORDS[k.group(1).lower()], m.group(1))
    return re.sub(r'(?i)^\s*\[Shot\s*1\]\s*', '', movement).strip()

def continuity_block(previous) -> str:
    """⏭ The previous parts of a chain as the writer reads them: the motion
    of each (its description field), most recent first, capped in number
    (`PREVIOUS_MAX`) and length (`PREVIOUS_CHARS`). '' when there is nothing
    to carry on from — the ask is then exactly what it was."""
    parts = []
    for text in (previous or []):
        if len(parts) >= PREVIOUS_MAX:
            break
        # The motion alone: the alignment header a launch prefixes, the identity
        # sentence ✨ inserts and any <Picture 1> — which named the PREVIOUS
        # clip's frame — are set aside, the way `has_motion` reads a prompt
        # (found in verification, 2026-09-04: every i2v part carried them).
        # A reference part gives its detailed_description, labels made words.
        reference = _reference_part(str(text or ''))
        desc = (reference if reference is not None
                else _description_field(strip_picture_references(str(text or ''))))
        desc = re.sub(r'\s+', ' ', desc).strip()
        if not desc:
            continue                      # skipped, not counted
        if len(desc) > PREVIOUS_CHARS:
            desc = desc[:PREVIOUS_CHARS].rsplit(' ', 1)[0] + '…'
        parts.append(desc)
    if not parts:
        return ''
    lines = '\n'.join(f'{i + 1}) {p}' for i, p in enumerate(parts))
    return f'{_CONTINUITY_RULE}\n{lines}\n\n'

def direction_block(direction) -> str:
    """🧭 The user's direction as the writer reads it; '' when none."""
    text = re.sub(r'\s+', ' ', str(direction or '')).strip()
    return f'{_DIRECTION_RULE}{text}\n\n' if text else ''

# Public engine primitives; private names remain legacy Video compatibility aliases.
H3_CRAFT = _H3_CRAFT
IDENTITY_RULE = _IDENTITY_RULE
NO_PICTURE_RULE = _NO_PICTURE_RULE
ENHANCE_SYSTEM = _ENHANCE_SYSTEM
CLOSING = _CLOSING

ALIGNMENT_HEADER = _ALIGNMENT_HEADER

BARE_THINK_CLOSE = _BARE_THINK_CLOSE

BUDGET_WORDS = _BUDGET_WORDS

CONTINUITY_RULE = _CONTINUITY_RULE

DELIMITER_LINE = _DELIMITER_LINE

DIRECTION_RULE = _DIRECTION_RULE

EMPHASISED_LABEL = _EMPHASISED_LABEL

FRAGMENT_TAIL = _FRAGMENT_TAIL

HEADER_LINE = _HEADER_LINE

HEADER_PHRASE = _HEADER_PHRASE

HEADER_SENTENCE = _HEADER_SENTENCE

IDENTITY_RE = _IDENTITY_RE

IDENTITY_SENTENCE = _IDENTITY_SENTENCE

LABEL_RE = _LABEL_RE

LEAD_IN = _LEAD_IN

META_LINE = _META_LINE

NOT_END = _NOT_END

REFERENCE_DESCRIPTION = _REFERENCE_DESCRIPTION

REFERENCE_LABEL = _REFERENCE_LABEL

REFERENCE_WORDS = _REFERENCE_WORDS

SENTENCE_END = _SENTENCE_END

THINK_BLOCK = _THINK_BLOCK

description_field = _description_field

drop_reasoning = _drop_reasoning

header_sentence = _header_sentence

join_sound = _join_sound

lift_audio = _lift_audio

lift_header = _lift_header

pacing_hint = _pacing_hint

prefix_description = _prefix_description

purge_hybrid = _purge_hybrid

reference_part = _reference_part

scrub = _scrub

split_header = _split_header

trim_dangling = _trim_dangling

__all__ = [
    'ALIGNMENT_HEADER',
    'BARE_THINK_CLOSE',
    'BUDGET_WORDS',
    'CLOSING',
    'CONTINUITY_RULE',
    'DELIMITER_LINE',
    'DIRECTION_RULE',
    'EMPHASISED_LABEL',
    'ENHANCE_SYSTEM',
    'FRAGMENT_TAIL',
    'H3_CRAFT',
    'HEADER_LINE',
    'HEADER_PHRASE',
    'HEADER_SENTENCE',
    'IDENTITY_RE',
    'IDENTITY_RULE',
    'IDENTITY_SENTENCE',
    'LABEL_RE',
    'LEAD_IN',
    'MAX_SHOTS',
    'META_LINE',
    'MIN_ASK_CHARS',
    'MIN_CHARS',
    'NOT_END',
    'NO_PICTURE_RULE',
    'PREVIOUS_CHARS',
    'PREVIOUS_MAX',
    'REFERENCE_DESCRIPTION',
    'REFERENCE_LABEL',
    'REFERENCE_WORDS',
    'SENTENCE_END',
    'THINK_BLOCK',
    'clip_seconds',
    'continuity_block',
    'description_field',
    'direction_block',
    'drop_reasoning',
    'ensure_identity_tag',
    'finish',
    'has_alignment_header',
    'header_sentence',
    'inject_alignment_header',
    'join_sound',
    'lift_audio',
    'lift_header',
    'pacing_hint',
    'prefix_description',
    'purge_hybrid',
    'reference_part',
    'restructure_fields',
    'scrub',
    'shot_count',
    'shot_cut_marks',
    'shot_directive',
    'split_header',
    'strip_picture_references',
    'trim_dangling',
]
