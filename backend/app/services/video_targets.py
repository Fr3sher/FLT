"""The video training-target catalogue — what each target model demands of a clip.

Every other piece of the video lane derives from this table: the cutter reads the
fps and the frame count, the length selector offers only counts that appear here,
the exporter reads the caption format and the folder layout. It is pure data plus
arithmetic on purpose — no ffmpeg, no torch, no database — so it stays importable
and testable on an install that has none of the video extras.

WHY A CATALOGUE AND NOT CONSTANTS. The obvious shortcut is to hard-code Wan 2.2's
16 fps and its N*4+1 frame rule, because Wan is the target we understand best.
That would be wrong for three targets out of four: the rule is a property of each
model's VAE, not a property of video. Wan 2.2 TI2V-5B is 24 fps with a single legal
length; MiniMax H3 wants frames congruent to 5 modulo 17. A clip cut to the wrong
rule does not fail loudly — the trainer truncates it, or samples across it and
speeds the motion up. Silence is exactly why this belongs in one reviewable table.

Two vocabularies that must not be conflated:
  `frame_rule`        — which frame counts the model's VAE can ingest at all.
  `training_verified` — whether a LoRA trainer for this target is known to exist.
The app can know a model's geometry perfectly and still have no way to train it.
Generating with a model is not training it, and the UI has to be able to say so.
"""

# Frame-count rules. Each maps to "is this count ingestible?", and the concrete
# offered lengths of every profile are checked against its own rule by the tests —
# so correcting a rule later forces its lengths to be corrected with it.
#   n4plus1     Wan's VAE: 4x temporal compression plus the anchor frame.
#   mod17plus5  MiniMax H3, observed in our own ComfyUI integration.
#   fixed       exactly the lengths listed, nothing else.
#   any         no known constraint — accept anything positive and say nothing.
_RULES = {
    'n4plus1': lambda f: f > 0 and (f - 1) % 4 == 0,
    'mod17plus5': lambda f: f > 0 and f % 17 == 5,
    'fixed': None,           # resolved against the profile's own frame_choices
    'any': lambda f: f > 0,
}

_TARGETS = {
    'wan22_14b': {
        'label': 'Wan 2.2 14B',
        # 16, NOT 24. "Wan 2.2 is 24 fps" is a widespread error that is true only of
        # the TI2V-5B variant below. Training 14B data at 24 fps produces motion that
        # plays back accelerated at inference, and nothing warns you.
        'fps': 16,
        'frame_rule': 'n4plus1',
        # 2.06 s / 3.06 s / 4.06 s / 5.06 s at 16 fps — the band the public video
        # datasets settled on for LoRA-scale training sets.
        'frame_choices': (33, 49, 65, 81),
        'resolutions': None,             # None = no closed list; any sane size
        'caption_format': 'txt_sidecar',
        'dataset_layout': 'flat',
        'training_verified': True,
    },
    'wan22_ti2v5b': {
        'label': 'Wan 2.2 TI2V-5B',
        'fps': 24,
        'frame_rule': 'fixed',
        'frame_choices': (121,),
        # A closed list, not a suggestion: this variant's VAE stride only resolves
        # at these two sizes.
        'resolutions': ((704, 1280), (1280, 704)),
        'caption_format': 'txt_sidecar',
        'dataset_layout': 'flat',
        'training_verified': True,
    },
    'ltx23': {
        'label': 'LTX 2.3',
        'fps': 24,
        # TODO(video-targets): the frame rule and the legal lengths are NOT verified
        # against a primary source yet, so this profile deliberately offers none.
        # An empty frame_choices means "we have no lengths to propose", which is the
        # honest state; inventing plausible ones is the failure mode this whole
        # module exists to prevent.
        'frame_rule': 'any',
        'frame_choices': (),
        'resolutions': None,
        'caption_format': 'txt_sidecar',
        'dataset_layout': 'flat',
        'training_verified': False,
    },
    'minimax_h3': {
        'label': 'MiniMax H3',
        # Inferred, not read from a spec: a 56-frame run measured 2.3 s in our own
        # ComfyUI integration, which is 24 fps to within the rounding. Pending a
        # primary source.
        'fps': 24,
        'frame_rule': 'mod17plus5',
        'frame_choices': (39, 56, 73, 90),
        'resolutions': None,
        'caption_format': 'txt_sidecar',
        'dataset_layout': 'flat',
        'training_verified': False,
    },
    'generic': {
        'label': 'Generic / other',
        # The escape hatch for a target we have not catalogued. It must impose
        # nothing — no fps, no rule, no lengths — rather than quietly apply Wan's.
        'fps': None,
        'frame_rule': 'any',
        'frame_choices': (),
        'resolutions': None,
        'caption_format': 'txt_sidecar',
        'dataset_layout': 'flat',
        'training_verified': False,
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
    if profile['frame_rule'] == 'fixed':
        return frames in profile['frame_choices']
    return _RULES[profile['frame_rule']](frames)


def snap_frames(key, requested):
    """Move a requested clip length to the nearest length this target accepts.

    This is what keeps a free-text "about 4 seconds" from becoming 64 frames that
    the trainer silently truncates. With no offered lengths (an uncatalogued or
    unverified target) the request passes through untouched — we have no grounds
    to move it.

    Ties break DOWNWARD. A shorter clip is a smaller latent cache and a faster
    step, and a request landing exactly between two lengths expressed a preference
    for neither.
    """
    choices = frame_choices(key)
    if not choices:
        return requested
    return min(choices, key=lambda c: (abs(c - requested), c))


def clip_seconds(key, frames):
    """How long `frames` frames last ONCE ENCODED AT THE TARGET'S fps — not at the
    source's. None when the profile declares no fps.

    The distinction is the whole point: the source clip's own duration is
    irrelevant, because the cutter re-encodes to the target rate. Reading the
    source's fps here is how a 16 fps target ends up with accelerated motion.
    """
    profile = _TARGETS.get(key)
    if profile is None or not profile['fps']:
        return None
    return frames / profile['fps']


def validate_resolution(key, width, height):
    """Is width x height acceptable for this target? Unknown profile → False."""
    profile = _TARGETS.get(key)
    if profile is None or width <= 0 or height <= 0:
        return False
    allowed = profile['resolutions']
    return True if allowed is None else (width, height) in allowed
