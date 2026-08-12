"""👥 Group by person: how small a face may be and still be identified.

Community feedback: "I thought I'd be able to point it at a large photos library
and it would group people together. It doesn't really work, finding only about a
tenth of the dataset."

The size gate was a fraction of the image AREA (6%, i.e. ~25% of the linear
dimension). That is a statement about the CAMERA, not about the face: the same
head passes on a small photo and fails on a big one, so a general photo library
— full-body shots, groups, scenes — had almost every face filed 'too_small',
never embedded, never clustered.

What is pinned here: the verdict is taken on ABSOLUTE PIXELS, an old cache keeps
working (and keeps its verdicts) without anyone re-embedding a bank, and the
re-detection of the faces an old scan skipped stays OPT-IN and narrow.
"""
import sys

import numpy as np
import pytest

from app.services import image_bank_service as banks

sys.path.insert(0, str(banks.cfg.BACKEND_DIR / 'infer'))
import face_embed_infer as fei                            # noqa: E402


def _cache(state='too_small', *, yaw=0.0, px=None):
    """One cache entry. ``px=None`` is the LEGACY shape: an entry written before
    the pixel size was stored (it round-trips through the .npz as NaN)."""
    entry = (state, 0.9, 0.001, np.zeros(4, dtype='float32'), yaw,
             '1:2', b'\1' * 32, float('nan') if px is None else float(px))
    return {'x.png': entry}


# --- the gate itself ---------------------------------------------------------

def test_the_size_verdict_is_pixels_not_a_fraction_of_the_image():
    """A face the old gate would have dropped for being 1% of a big photo is
    identified, because 200 px of face is 200 px of face on any camera."""
    assert fei.FACE_PX_MIN == 64.0
    assert not hasattr(fei, 'BBOX_MIN')       # the fraction no longer gates
    assert fei._verdict(0.9, 200.0, 0.0) == 'scorable'


def test_a_face_under_the_pixel_floor_is_too_small():
    """Under ~64 px the 112x112 recognition crop is upscaled more than 2x and the
    embedding drifts into other people — the floor is where the number stops
    meaning anything, not a taste."""
    assert fei._verdict(0.9, 63.9, 0.0) == 'too_small'
    assert fei._verdict(0.9, 64.0, 0.0) == 'scorable'
    # No size at all is not a pass.
    assert fei._verdict(0.9, float('nan'), 0.0) == 'too_small'


def test_the_short_side_decides_so_a_sliver_is_not_a_face():
    """A 300x40 box has plenty of area and no identifiable face in it: the gate
    reads the SHORT side, which is what the aligned crop is limited by."""
    assert min(300.0, 40.0) < fei.FACE_PX_MIN
    assert fei._verdict(0.9, min(300.0, 40.0), 0.0) == 'too_small'


def test_detection_and_pose_gates_are_untouched():
    """Only the size question changed. A weak detection is still 'low_det' and an
    extreme profile is still refused an embedding (embedding one merges people),
    while a face with NO measured pose is still not treated as turned away."""
    assert fei.DET_MIN == 0.50 and fei.YAW_MAX == 40.0
    assert fei._verdict(0.49, 200.0, 0.0) == 'low_det'
    assert fei._verdict(0.9, 200.0, 70.0) == 'extreme_pose'
    assert fei._verdict(0.9, 200.0, -70.0) == 'extreme_pose'
    assert fei._verdict(0.9, 200.0, float('nan')) == 'scorable'


def test_low_det_wins_over_the_size_floor():
    """Order preserved: the reason shown is the first one that applies, so a
    barely-detected tiny face still reads 'low_det' as it always did."""
    assert fei._verdict(0.1, 10.0, 0.0) == 'low_det'


# --- the cache ---------------------------------------------------------------

def test_a_cache_without_the_pixel_array_still_loads(tmp_path):
    """The bpx array is additive, exactly like yaws was: a bank embedded before
    it existed must not be re-embedded because a number joined the tuple."""
    p = tmp_path / 'face_cache.npz'
    np.savez_compressed(
        str(p), paths=np.array(['x.png']), states=np.array(['too_small']),
        dets=np.array([0.9], dtype='float32'),
        bfracs=np.array([0.01], dtype='float32'),
        embs=np.zeros((1, 4), dtype='float32'))
    loaded = fei._load_cache(str(p))
    px = fei._cache_px(loaded['x.png'])
    assert px != px                              # NaN — "not measured"
    assert loaded['x.png'][0] == 'too_small'     # and the stored verdict is kept

    # It round-trips once re-saved, so nobody pays for the migration twice.
    fei._save_cache(str(p), loaded)
    again = fei._load_cache(str(p))
    assert fei._cache_px(again['x.png']) != fei._cache_px(again['x.png'])
    assert again['x.png'][0] == 'too_small'


def test_a_measured_pixel_size_survives_a_save_reload(tmp_path):
    p = tmp_path / 'face_cache.npz'
    fei._save_cache(str(p), _cache('scorable', px=123.5))
    assert fei._cache_px(fei._load_cache(str(p))['x.png']) == pytest.approx(123.5)


def test_the_transfer_lane_still_reads_a_cache_that_has_the_new_array(tmp_path):
    """The other reader of this file accepts a KNOWN set of arrays and silently
    drops the whole cache on anything else — so a new array is a way to make
    face metadata stop travelling between banks without a single error."""
    from app.services import bank_transfer_metadata as transfer

    p = tmp_path / 'face_cache.npz'
    entry = ('scorable', 0.9, 0.2, np.zeros(512, dtype='float32'), 4.0,
             '1:2', b'\1' * 32, 180.0)
    fei._save_cache(str(p), {'x.png': entry})
    index = transfer.load_runtime_cache_index(None, str(p))
    assert 'face' in index.get('x.png', {})
    payload, _sig, _digest = index['x.png']['face']
    assert payload['state'] == 'scorable'
    assert payload['bbox_frac'] == pytest.approx(0.2)


# --- what a re-run does, and does not, re-detect -----------------------------

def test_an_ordinary_rerun_re_detects_nothing(tmp_path, monkeypatch):
    """The honest update path: a bank scanned under the old gate keeps every
    cached verdict on a re-run — no surprise hours of re-detection — and the new
    floor applies to images added or edited from now on."""
    todo = _run_todo(tmp_path, monkeypatch, _cache('too_small'), {})
    assert todo == []


def test_the_opt_in_regate_re_detects_the_legacy_too_small(tmp_path, monkeypatch):
    """Opt-in, because the pixel size of an old 'too_small' is NOT recoverable:
    bbox_frac alone cannot be back-solved (the image dimensions are not in the
    cache), so the only honest answer is to look at the image again."""
    todo = _run_todo(tmp_path, monkeypatch, _cache('too_small'),
                     {'regate_too_small': True})
    assert todo == ['x.png']


def test_the_regate_leaves_every_other_legacy_verdict_alone(tmp_path, monkeypatch):
    """The floor exists to ADD faces to their person, never to demote a face that
    already clusters — and 'no_face' is a detection answer the size gate has no
    opinion about."""
    for state in ('scorable', 'no_face', 'low_det', 'extreme_pose'):
        todo = _run_todo(tmp_path, monkeypatch, _cache(state),
                         {'regate_too_small': True})
        assert todo == [], state


def test_an_entry_already_measured_in_pixels_is_never_re_detected(tmp_path, monkeypatch):
    """A 'too_small' decided BY the pixel floor is a real verdict, not a legacy
    one: asking for the regate twice must not re-run the detector for ever."""
    todo = _run_todo(tmp_path, monkeypatch, _cache('too_small', px=30.0),
                     {'regate_too_small': True})
    assert todo == []


class _Stop(Exception):
    pass


def _run_todo(tmp_path, monkeypatch, cache, extra):
    """The images the REAL run decided to re-detect.

    ``_needs_work`` is a closure inside main(), and re-expressing it here would
    pin a second implementation. So main() is driven for real and cut short on
    the "N image(s), M cached" line it prints right after the split — before any
    model, cv2 or insightface import, so this runs in the plain test
    interpreter.
    """
    import io
    import json

    cache_path = tmp_path / 'face_cache.npz'
    fei._save_cache(str(cache_path), cache)
    # Staleness is a different contract (file identity), pinned elsewhere; here
    # the file simply still is what it was.
    monkeypatch.setattr(fei, '_is_stale', lambda p, e: False)

    seen = []

    def log(message):
        seen.append(message)
        if 'cached' in message:
            raise _Stop()

    monkeypatch.setattr(fei, '_log', log)
    payload = {'images': ['x.png'], 'cache': str(cache_path), **extra}
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    with pytest.raises(_Stop):
        fei.main()
    cached = int(seen[-1].split(',')[1].split()[0])
    return [] if cached else ['x.png']
