"""The video training-target catalogue: what every profile must declare, and the
arithmetic that turns a user's "how long should a clip be?" into a frame count the
trainer will actually accept.

These tests are PURE — no ffmpeg, no GPU, no database. That is deliberate: the
catalogue is what every other piece of the video lane derives from, so it has to
stay green on an install that has none of the video extras.

The numbers here were taken from the models' own configs and the trainers' own
source, not from model cards — several of the cards are wrong. The most costly
one: Alibaba's Wan2.2-T2V-A14B card carries "720P@24fps" boilerplate whose subject
is the 5B, and the A14B never states an fps at all. The config file says 16.
"""
import pytest

from app.services import video_targets as vt


# --- the catalogue's contract -------------------------------------------------

def test_profile_keys_are_stable():
    """These keys land in user databases (VideoDataset.target_profile), so renaming
    one silently orphans every dataset that carries it. Same rule as the catalog
    labels and What's-new ids: a rename needs an alias path, and this test is what
    makes someone notice."""
    assert vt.PROFILE_KEYS == (
        'wan22_14b', 'wan22_ti2v5b', 'ltx23', 'minimax_h3', 'generic')


def test_every_profile_declares_the_full_contract():
    """A half-declared profile is worse than a missing one: the cutter would read a
    None fps and produce clips at the source's rate without saying so."""
    required = {'label', 'fps', 'frame_rule', 'frame_choices', 'frame_default',
                'size_multiple', 'recommended_sizes', 'keep_audio',
                'caption_style', 'dataset_layout', 'training_verified',
                'licence_note'}
    for key in vt.PROFILE_KEYS:
        assert required <= set(vt.get(key)), f'{key} is missing part of the contract'


def test_training_verified_is_an_explicit_boolean_everywhere():
    """'We know how to GENERATE with this model' is not 'we know how to TRAIN it'.
    The UI must be able to say which is which, so no profile is allowed to be
    silent about it."""
    for key in vt.PROFILE_KEYS:
        assert isinstance(vt.get(key)['training_verified'], bool)


def test_only_wan_14b_claims_verified_training_support():
    """The one target with a reference 24 GB config in a maintained trainer.

    TI2V-5B in particular looks trainable and is not: musubi-tuner has no
    'ti2v-5B' key at all, and diffusion-pipe covers t2v/t2i only. Marking it
    verified because it is 'Wan 2.2' would send a user down a dead end."""
    verified = [k for k in vt.PROFILE_KEYS if vt.get(k)['training_verified']]
    assert verified == ['wan22_14b']


def test_unknown_profile_key_returns_none():
    assert vt.get('wan27_ultra') is None


# --- frame-count rules --------------------------------------------------------

def test_every_frame_choice_obeys_its_own_declared_rule():
    """The consistency check that survives being wrong about a model: whatever rule
    a profile declares, its offered frame counts must satisfy it. If research later
    corrects a rule, this test fails until the choices are corrected too."""
    for key in vt.PROFILE_KEYS:
        profile = vt.get(key)
        for frames in profile['frame_choices']:
            assert vt.is_legal_frames(key, frames), (
                f'{key} offers {frames} frames, which breaks its own '
                f'{profile["frame_rule"]} rule')


def test_every_default_length_is_one_of_the_offered_lengths():
    for key in vt.PROFILE_KEYS:
        profile = vt.get(key)
        if profile['frame_choices']:
            assert profile['frame_default'] in profile['frame_choices']


def test_both_wan_variants_share_the_four_n_plus_one_rule():
    """A hard consequence of a temporal VAE stride of 4 — and it applies to the 5B
    too. Treating the 5B as 'exactly 121 frames' would hide every other legal
    length it has."""
    for key in ('wan22_14b', 'wan22_ti2v5b'):
        assert vt.is_legal_frames(key, 49)
        assert not vt.is_legal_frames(key, 50)


def test_ltx_uses_a_temporal_stride_of_eight_not_four():
    """LTX's VAE compresses time by 8, so Wan's 4n+1 is not enough — 29 frames is
    legal for Wan and illegal for LTX.

    The counter-example has to be chosen with care, and that is the point: every
    length Wan actually OFFERS (17, 25, 33 … 121) happens to satisfy 8n+1 as well,
    so a shared rule looks correct on all the obvious values and only breaks on
    a snapped or hand-entered one. Copying Wan's rule onto LTX would emit clips
    diffusion-pipe rounds down without a word."""
    assert vt.is_legal_frames('wan22_14b', 29)
    assert not vt.is_legal_frames('ltx23', 29)
    assert vt.is_legal_frames('ltx23', 49)


def test_minimax_h3_frame_counts_are_five_modulo_seventeen():
    """From MiniMax's own released VAE config (vae_clip_length 17, token_drop 3),
    not from a ComfyUI quirk."""
    assert vt.is_legal_frames('minimax_h3', 124)
    assert not vt.is_legal_frames('minimax_h3', 125)


def test_generic_profile_accepts_any_positive_frame_count():
    """The escape hatch for a target we have not catalogued. It must not silently
    impose someone else's rule."""
    assert vt.is_legal_frames('generic', 57)
    assert vt.is_legal_frames('generic', 1000)
    assert not vt.is_legal_frames('generic', 0)


# --- snapping a requested length ----------------------------------------------

def test_snap_frames_returns_the_nearest_legal_count():
    """64 frames is the classic mistake: it looks round, and no trainer will tell
    you it was wrong. Wan's own code never validates the count — the '4n+1' text is
    a CLI help string, and the pipelines just floor in latent space."""
    assert vt.snap_frames('wan22_14b', 64) == 65


def test_snap_frames_breaks_ties_downward():
    """A request landing exactly between two offered lengths expressed a preference
    for neither; prefer the shorter clip, which is a smaller latent cache and a
    faster step."""
    assert vt.snap_frames('wan22_14b', 57) == 49


def test_snap_frames_never_returns_an_illegal_count():
    for key in ('wan22_14b', 'wan22_ti2v5b', 'ltx23', 'minimax_h3'):
        for requested in range(1, 400):
            assert vt.is_legal_frames(key, vt.snap_frames(key, requested))


def test_snap_frames_clamps_to_the_offered_range():
    choices = vt.get('wan22_14b')['frame_choices']
    assert vt.snap_frames('wan22_14b', 1) == min(choices)
    assert vt.snap_frames('wan22_14b', 10_000) == max(choices)


def test_snap_frames_on_the_generic_profile_returns_the_request_untouched():
    assert vt.snap_frames('generic', 57) == 57


# --- frames <-> seconds -------------------------------------------------------

def test_a_clip_lasts_one_frame_interval_less_than_its_frame_count_suggests():
    """81 frames is 80 INTERVALS. At 16 fps that is 5.00 s exactly, which is what
    Wan documents — not 5.0625. Getting this wrong asks the cutter for one frame
    more of source than the segment needs, and rejects clips that fit."""
    assert vt.clip_seconds('wan22_14b', 81) == pytest.approx(5.0)


def test_the_five_second_design_point_holds_for_the_other_wan_variant_too():
    """121 frames at 24 fps is also exactly 5.00 s. Both variants were designed
    around the same duration at different rates — a cross-check that the formula
    is (frames - 1) / fps and not frames / fps."""
    assert vt.clip_seconds('wan22_ti2v5b', 121) == pytest.approx(5.0)


def test_clip_seconds_is_none_when_the_profile_has_no_fixed_fps():
    """A profile whose fps we have not verified must not invent one."""
    assert vt.clip_seconds('generic', 57) is None


# --- resolution ---------------------------------------------------------------

def test_wan_14b_requires_both_sides_divisible_by_sixteen():
    """Not a free-for-all, and not a closed list either: all three trainers agree
    on a step of 16 for the 14B. 832x480 is legal; 830x480 is not."""
    assert vt.validate_resolution('wan22_14b', 832, 480)
    assert not vt.validate_resolution('wan22_14b', 830, 480)


def test_the_five_b_needs_thirty_two_because_its_vae_compresses_further():
    """1280x704 passes, 1280x720 does NOT — 720 is not divisible by 32. That is
    exactly why the official 720P size for this variant is 704, and it is the trap
    a 'Wan 2.2' profile shared between the two variants would walk into."""
    assert vt.validate_resolution('wan22_ti2v5b', 1280, 704)
    assert not vt.validate_resolution('wan22_ti2v5b', 1280, 720)


def test_recommended_sizes_are_suggestions_not_limits():
    """The official inference size lists are CLI asserts, not training constraints.
    Encoding them as limits would refuse perfectly trainable data."""
    assert (832, 480) in vt.get('wan22_14b')['recommended_sizes']
    assert vt.validate_resolution('wan22_14b', 1024, 1024)   # not in the list


def test_the_generic_profile_imposes_no_grid():
    assert vt.validate_resolution('generic', 831, 479)


def test_no_profile_accepts_a_zero_or_negative_size():
    for key in vt.PROFILE_KEYS:
        assert not vt.validate_resolution(key, 0, 480)
        assert not vt.validate_resolution(key, 848, -1)


# --- audio --------------------------------------------------------------------

def test_the_joint_audio_video_models_keep_their_soundtrack():
    """LTX-2.3 and MiniMax H3 train audio and video together. Stripping the track
    when cutting teaches the model to be silent — a degradation with no error
    message anywhere, which is why it is a profile property and not a global flag."""
    assert vt.get('ltx23')['keep_audio'] is True
    assert vt.get('minimax_h3')['keep_audio'] is True


def test_wan_drops_audio_because_nothing_reads_it():
    for key in ('wan22_14b', 'wan22_ti2v5b'):
        assert vt.get(key)['keep_audio'] is False


# --- licence ------------------------------------------------------------------

def test_a_licence_restricted_target_says_so_in_the_catalogue():
    """MiniMax H3's community licence grants no rights at all in the EU, the UK,
    South Korea or the USA — and it extends to the outputs, so keeping the training
    private is not a workaround. A user must not meet that in a forum thread after
    building a dataset."""
    assert vt.get('minimax_h3')['licence_note']


def test_targets_without_a_licence_restriction_carry_none():
    for key in ('wan22_14b', 'wan22_ti2v5b', 'generic'):
        assert vt.get(key)['licence_note'] is None
