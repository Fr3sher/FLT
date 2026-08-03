"""The video training-target catalogue: what every profile must declare, and the
arithmetic that turns a user's "how long should a clip be?" into a frame count the
trainer will actually accept.

These tests are PURE — no ffmpeg, no GPU, no database. That is deliberate: the
catalogue is what every other piece of the video lane derives from, so it has to
stay green on an install that has none of the video extras.
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
    required = {'label', 'fps', 'frame_rule', 'frame_choices', 'resolutions',
                'caption_format', 'dataset_layout', 'training_verified'}
    for key in vt.PROFILE_KEYS:
        assert required <= set(vt.get(key)), f'{key} is missing part of the contract'


def test_training_verified_is_an_explicit_boolean_everywhere():
    """'We know how to GENERATE with this model' is not 'we know how to TRAIN it'.
    The UI must be able to say which is which, so no profile is allowed to be
    silent about it."""
    for key in vt.PROFILE_KEYS:
        assert isinstance(vt.get(key)['training_verified'], bool)


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


def test_wan_frame_counts_are_n_times_four_plus_one():
    """A hard constraint of Wan's VAE, not a preference."""
    for frames in vt.get('wan22_14b')['frame_choices']:
        assert (frames - 1) % 4 == 0


def test_minimax_h3_frame_counts_are_five_modulo_seventeen():
    assert vt.is_legal_frames('minimax_h3', 56)
    assert not vt.is_legal_frames('minimax_h3', 57)


def test_ti2v5b_accepts_only_its_single_documented_length():
    assert vt.is_legal_frames('wan22_ti2v5b', 121)
    assert not vt.is_legal_frames('wan22_ti2v5b', 81)


def test_generic_profile_accepts_any_positive_frame_count():
    """The escape hatch for a target we have not catalogued. It must not silently
    impose someone else's rule."""
    assert vt.is_legal_frames('generic', 57)
    assert vt.is_legal_frames('generic', 1000)
    assert not vt.is_legal_frames('generic', 0)


# --- snapping a requested length ----------------------------------------------

def test_snap_frames_returns_the_nearest_legal_count():
    """64 frames is the classic mistake: it looks round, and Wan's trainer takes it
    and truncates. The selector must move it to 65 rather than pass it through."""
    assert vt.snap_frames('wan22_14b', 64) == 65


def test_snap_frames_breaks_ties_downward():
    """57 sits exactly between 49 and 65. Prefer the SHORTER clip: a shorter clip is
    a smaller latent cache and a faster step, and the user asked for neither."""
    assert vt.snap_frames('wan22_14b', 57) == 49


def test_snap_frames_never_returns_an_illegal_count():
    for requested in range(1, 200):
        assert vt.is_legal_frames('wan22_14b', vt.snap_frames('wan22_14b', requested))


def test_snap_frames_clamps_to_the_offered_range():
    choices = vt.get('wan22_14b')['frame_choices']
    assert vt.snap_frames('wan22_14b', 1) == min(choices)
    assert vt.snap_frames('wan22_14b', 10_000) == max(choices)


def test_snap_frames_on_the_generic_profile_returns_the_request_untouched():
    assert vt.snap_frames('generic', 57) == 57


# --- frames <-> seconds -------------------------------------------------------

def test_clip_seconds_derives_from_the_target_fps_not_the_source():
    """81 frames at Wan 14B's 16 fps is 5.0625 s. Reading the SOURCE's fps here is
    how you get clips whose motion plays back too fast."""
    assert vt.clip_seconds('wan22_14b', 81) == pytest.approx(5.0625)


def test_clip_seconds_uses_twenty_four_for_ti2v5b():
    """The variant that actually is 24 fps — the one the '"Wan 2.2 is 24 fps"' myth
    comes from."""
    assert vt.clip_seconds('wan22_ti2v5b', 121) == pytest.approx(121 / 24)


def test_clip_seconds_is_none_when_the_profile_has_no_fixed_fps():
    """A profile whose fps we have not verified must not invent one."""
    assert vt.clip_seconds('generic', 57) is None


# --- resolution ---------------------------------------------------------------

def test_ti2v5b_resolutions_are_a_closed_list():
    assert vt.validate_resolution('wan22_ti2v5b', 704, 1280)
    assert vt.validate_resolution('wan22_ti2v5b', 1280, 704)
    assert not vt.validate_resolution('wan22_ti2v5b', 848, 480)


def test_a_profile_with_free_resolutions_accepts_any_sane_size():
    assert vt.validate_resolution('wan22_14b', 848, 480)


def test_no_profile_accepts_a_zero_or_negative_size():
    for key in vt.PROFILE_KEYS:
        assert not vt.validate_resolution(key, 0, 480)
        assert not vt.validate_resolution(key, 848, -1)
