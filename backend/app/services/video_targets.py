"""The video training-target catalogue — what each target model demands of a clip.

Every other piece of the video lane derives from this table: the cutter reads the
fps and the frame count, the length selector offers only counts that appear here,
the exporter reads the audio policy and the folder layout. It is pure data plus
arithmetic on purpose — no ffmpeg, no torch, no database — so it stays importable
and testable on an install that has none of the video extras.

WHY A CATALOGUE AND NOT CONSTANTS. The obvious shortcut is to hard-code Wan 2.2's
16 fps and its 4n+1 frame rule, because Wan is the target we understand best. That
is wrong for three targets out of four: the rule is a property of each model's
VAE, not a property of video. LTX compresses time by 8, so 29 frames is legal for
Wan and illegal for LTX. MiniMax H3 wants frames congruent to 5 modulo 17. A clip
cut to the wrong rule does not fail loudly — the trainer floors it in latent space,
or samples across the whole duration and speeds the motion up.

That counter-example is worth choosing carefully, and 29 is not an arbitrary pick:
EVERY length Wan actually offers (17, 25, 33 … 121) happens to satisfy 8n+1 as
well. A rule shared between the two therefore looks correct on every value in the
menu and only breaks on a snapped or hand-entered one — which is exactly the shape
of a bug that survives review.

WHERE THESE NUMBERS COME FROM. The models' own config files and the trainers' own
source, never the model cards — several cards are wrong in ways that matter:

  * Alibaba's Wan2.2-T2V-A14B card carries "720P@24fps" boilerplate whose subject
    is the 5B. The A14B card never states an fps for the A14B at all. This is why
    "Wan 2.2 is 24 fps" is repeated everywhere and is false for the 14B, whose
    shared_config.py says sample_fps = 16.
  * Wan's "the number should be 4n+1" is a CLI HELP STRING. Nothing asserts it.
    The pipelines compute ((F-1)//4)+1 and floor. The app must enforce the rule
    itself, because it will never be told it got it wrong.

Two vocabularies that must not be conflated:
  `frame_rule`        — which frame counts the model's VAE can ingest at all.
  `training_verified` — whether a LoRA trainer for this target is known to exist.
The app can know a model's geometry perfectly and still have no way to train it.
Exactly one target currently clears the second bar.
"""

# Frame-count rules. Each maps to "is this count ingestible?", and the concrete
# offered lengths of every profile are checked against its own rule by the tests —
# so correcting a rule later forces its lengths to be corrected with it.
#   n4plus1     temporal VAE stride of 4 (both Wan variants).
#   n8plus1     temporal VAE stride of 8 (LTX). NOT interchangeable with 4n+1:
#               every 8n+1 count is also 4n+1, so the looser rule would pass
#               illegal lengths through in silence.
#   mod17plus5  MiniMax H3. Not a plain stride — it falls out of a chunked VAE
#               (vae_clip_length 17, vae_token_drop 3 in MiniMax's own config).
#   any         no known constraint — accept anything positive and say nothing.
_RULES = {
    'n4plus1': lambda f: f > 0 and (f - 1) % 4 == 0,
    'n8plus1': lambda f: f > 0 and (f - 1) % 8 == 0,
    'mod17plus5': lambda f: f > 0 and f % 17 == 5,
    'any': lambda f: f > 0,
}

_TARGETS = {
    'wan22_14b': {
        'label': 'Wan 2.1 / 2.2 14B',
        # 16, NOT 24 — see the module docstring for why that error is everywhere.
        # Confirmed three times over: Wan's shared_config.py, musubi-tuner's
        # TARGET_FPS_WAN, and diffusion-pipe's framerate for this model.
        'fps': 16,
        'frame_rule': 'n4plus1',
        'frame_choices': (17, 25, 33, 49, 65, 81, 97, 121),
        # 81 frames = 80 intervals = exactly 5.00 s at 16 fps. It is the value
        # Wan's own config ships as frame_num.
        'frame_default': 81,
        # A STEP, not a list. All three trainers agree on 16 for this variant.
        'size_multiple': 16,
        # Mirrors the official inference sizes purely as a convenience. These are
        # NOT constraints: the size list in Wan's configs is an inference-CLI
        # assert, and encoding it here would refuse perfectly trainable data.
        'recommended_sizes': ((832, 480), (480, 832), (1280, 720), (720, 1280)),
        'keep_audio': False,
        'caption_style': 'freeform',
        'dataset_layout': 'flat',
        'training_verified': True,
        'licence_note': None,
    },
    'wan22_ti2v5b': {
        'label': 'Wan 2.2 TI2V-5B',
        'fps': 24,
        # The SAME rule as the 14B — the temporal stride is still 4. Treating this
        # variant as "exactly 121 frames" would hide every other legal length.
        'frame_rule': 'n4plus1',
        'frame_choices': (25, 49, 81, 97, 121),
        'frame_default': 121,          # 120 intervals at 24 fps = 5.00 s again
        # 32, not 16: this variant's VAE compresses space by 16 and then patches
        # 2x2. It is why the official 720P size here is 1280x704 and not 1280x720
        # — 720 is not divisible by 32. Sharing one "Wan 2.2" profile between the
        # two variants walks straight into that.
        'size_multiple': 32,
        'recommended_sizes': ((1280, 704), (704, 1280)),
        'keep_audio': False,
        'caption_style': 'freeform',
        'dataset_layout': 'flat',
        # Looks trainable, is not. musubi-tuner has no 'ti2v-5B' key at all (the
        # entry in its size table is dead data), and diffusion-pipe covers t2v/t2i
        # only. Marking this verified because it says "Wan 2.2" would send a user
        # down a dead end after they built the dataset.
        'training_verified': False,
        'licence_note': None,
    },
    'ltx23': {
        'label': 'LTX 2.3',
        # Not an LTX requirement but a downstream one, and worth stating plainly:
        # Lightricks' own trainer is fps-agnostic — it reads the CONTAINER's fps
        # tag and divides temporal coordinates by it, so what matters there is
        # that the tag be truthful. 24 is what diffusion-pipe force-resamples to
        # and what ai-toolkit defaults to, so 24 is what we write.
        'fps': 24,
        # Temporal stride 8, NOT 4. Copying Wan's rule here emits lengths
        # diffusion-pipe rounds down without a word.
        'frame_rule': 'n8plus1',
        # The counts Lightricks actually ships in its own configs. 73 and 97 are
        # legal and deliberately absent: they come from an illustrative "e.g."
        # list in a doc, not from anything anyone trained.
        'frame_choices': (25, 49, 81, 89, 121),
        'frame_default': 81,
        'size_multiple': 32,
        'recommended_sizes': ((960, 544), (768, 448), (512, 512)),
        # LTX-2.3 trains audio and video JOINTLY. Stripping the track when cutting
        # degrades the training signal with no error anywhere, and it contradicts
        # the caption spec, which asks for the soundtrack to be described.
        'keep_audio': True,
        'caption_style': 'paragraph_with_audio',
        'dataset_layout': 'flat',
        # The official trainer wants Linux, CUDA 13 and 80 GB (32 GB with an INT8
        # config). diffusion-pipe is the only 24 GB-class route and its own author
        # hedges it. Nobody has demonstrated this on Windows at 24 GB.
        'training_verified': False,
        'licence_note': 'LTX-2 Community License — not Apache-2.0; read the terms '
                        'before publishing anything trained on it.',
    },
    'minimax_h3': {
        'label': 'MiniMax H3',
        'fps': 24,
        'frame_rule': 'mod17plus5',
        'frame_choices': (39, 56, 73, 90, 107, 124, 141, 158, 175, 192, 209),
        # The model card documents 4–15 s. 124 is the value both ComfyUI and
        # ai-toolkit default to; it is a default here, never a floor.
        'frame_default': 124,
        'size_multiple': 32,
        'recommended_sizes': ((1344, 768), (768, 1344), (768, 768)),
        # Joint audio-video, 32 kHz stereo. A silent dataset teaches silence.
        'keep_audio': True,
        'caption_style': 'paragraph_with_audio',
        'dataset_layout': 'flat',
        # No example config ships for it anywhere, no measured training VRAM
        # exists for a 33B dense model, and no round-trip of a trained LoRA back
        # into ComfyUI has been demonstrated.
        'training_verified': False,
        # NOT a footnote. The MiniMax H3 Community Licence grants rights SOLELY
        # within its "Applicable Territory", and names the EU, the UK, South Korea
        # and the USA as Excluded Territories — the grant does not exist there at
        # all. It reaches the OUTPUTS too, so keeping the training private is not
        # a way around it. A user must not discover this in a forum thread after
        # building a dataset.
        'licence_note': 'MiniMax H3 Community License grants NO rights in the EU, '
                        'UK, South Korea or USA — and the restriction covers the '
                        'outputs, not just the model. Check your territory first.',
    },
    'generic': {
        'label': 'Generic / other',
        # The escape hatch for a target we have not catalogued. It must impose
        # nothing — no fps, no rule, no lengths — rather than quietly apply Wan's.
        'fps': None,
        'frame_rule': 'any',
        'frame_choices': (),
        'frame_default': None,
        'size_multiple': None,
        'recommended_sizes': (),
        'keep_audio': False,
        'caption_style': 'freeform',
        'dataset_layout': 'flat',
        'training_verified': False,
        'licence_note': None,
    },
}

# Stable, ordered, and STORED IN USER DATABASES (VideoDataset.target_profile).
# Renaming a key orphans every dataset that carries it, so a rename needs an alias
# path — the same rule the catalog labels and What's-new ids already live under.
PROFILE_KEYS = tuple(_TARGETS)


def get(key):
    """The profile dict for `key`, or None if the key is unknown.

    Returns a copy: the catalogue is module-level state and a caller that mutates
    what it reads would change the rules for every later reader in the process.
    """
    profile = _TARGETS.get(key)
    return dict(profile) if profile is not None else None


def frame_choices(key):
    """The clip lengths, in frames, this profile can offer. Empty when we have no
    verified lengths — which the caller must render as "no presets", never as
    "any length is fine"."""
    profile = _TARGETS.get(key)
    return profile['frame_choices'] if profile else ()


def is_legal_frames(key, frames):
    """Can this target's VAE ingest a clip of exactly `frames` frames?

    False for an unknown profile: refusing is the safe answer when we cannot say.
    """
    profile = _TARGETS.get(key)
    if profile is None:
        return False
    return _RULES[profile['frame_rule']](frames)


def snap_frames(key, requested):
    """Move a requested clip length to the nearest length this target accepts.

    This is what keeps "about four seconds" from becoming 64 frames. No trainer
    will object to 64: Wan floors it in latent space, diffusion-pipe rounds the
    bucket down, ai-toolkit does not check the dataset at all. The app is the only
    place the rule can be enforced.

    With no offered lengths (an uncatalogued target) the request passes through
    untouched — we have no grounds to move it.

    Ties break DOWNWARD. A shorter clip is a smaller latent cache and a faster
    step, and a request landing exactly between two lengths expressed a preference
    for neither.
    """
    choices = frame_choices(key)
    if not choices:
        return requested
    return min(choices, key=lambda c: (abs(c - requested), c))


def clip_seconds(key, frames):
    """How long a clip of `frames` frames lasts at the TARGET's fps. None when the
    profile declares no fps.

    (frames - 1) / fps, because N frames span N-1 intervals. The off-by-one is not
    cosmetic: it decides how much source a cut needs, so the frames/fps version
    rejects segments that fit. The cross-check that it is right is that BOTH Wan
    variants land on exactly 5.00 s at their own rate — 81 at 16, and 121 at 24.

    Reading the SOURCE's fps here instead of the target's is the other way to get
    this wrong, and that one produces accelerated motion rather than a rejection.
    """
    profile = _TARGETS.get(key)
    if profile is None or not profile['fps']:
        return None
    return (frames - 1) / profile['fps']


def validate_resolution(key, width, height):
    """Is width x height acceptable for this target?

    A STEP, not a whitelist. The official size lists are inference-CLI asserts;
    refusing anything outside them would reject perfectly trainable data. What is
    real is the divisibility the VAE and the patch size impose together.
    Unknown profile → False.
    """
    profile = _TARGETS.get(key)
    if profile is None or width <= 0 or height <= 0:
        return False
    step = profile['size_multiple']
    return step is None or (width % step == 0 and height % step == 0)
