"""🔖 Watermarks on shots — the SigLIP2 detector, pointed at the ambassador frame.

The detector itself is the image lane's and is tested there. What is under test
here is the seam this pass adds, and every one of these decisions was a way to
get it wrong:

  * ONE frame per shot, and it is the ambassador — the frame the metrics pass
    already picked as the sharpest sanely-exposed one, not the first frame,
    which is whatever the cut happened to land on;
  * the frame is extracted BIGGER than the embed pass's 256 px, because a corner
    logo is exactly the detail a thumbnail destroys;
  * a shot the detector could not judge is 'unreadable' — never 'clean';
  * the detector failing to LOAD costs the pass, not the bank: the clips it
    already judged keep their verdicts;
  * the verdict merges into metrics_json, it does not replace it.

Both heavy seams (frame extraction, the detector child) are monkeypatched, so
this file runs with no PyAV, no torch and no weights on disk.
"""
import json

from app.services import video_watermark as wm


# --- which frame gets looked at ----------------------------------------------------

def test_the_frame_looked_at_is_the_ambassador_the_metrics_pass_chose():
    """Not the middle, and not the first. The metrics pass already measured every
    frame and named the sharpest sanely-exposed one; re-deciding here would look
    at a frame nothing vouches for."""
    assert wm.ambassador_time(10.0, 20.0, {'metrics_state': 'ok',
                                           'sharpest_frame_s': 17.5}) == 17.5


def test_an_unmeasured_shot_falls_back_to_its_middle():
    assert wm.ambassador_time(10.0, 20.0, None) == 15.0


def test_an_ambassador_outside_the_bounds_is_refused():
    """A timestamp outside the clip belongs to bounds that have since been
    re-cut. Clamping it would invent a measurement; the middle is the honest
    fallback, the same rule video_clip_search.frame_times keeps."""
    assert wm.ambassador_time(10.0, 20.0, {'metrics_state': 'ok',
                                           'sharpest_frame_s': 44.0}) == 15.0


def test_the_frame_is_extracted_larger_than_an_embedding_thumbnail():
    """A watermark is a few dozen pixels in a corner. At the embed pass's 256 px
    long side it is gone before the classifier sees it — the two passes want two
    different sizes from the same decode seam, on purpose."""
    from app.services import video_clip_search
    assert wm.FRAME_LONG_SIDE > video_clip_search.EMBED_LONG_SIDE


# --- the pass ----------------------------------------------------------------------

def test_each_shot_gets_its_score_stored(app, monkeypatch):
    bank_id, ids = _bank_with_clips(app, 2)
    _fake_frames(monkeypatch)
    _fake_detector(monkeypatch, {
        f'clip_{ids[0]}.jpg': ('detected', 0.91),
        f'clip_{ids[1]}.jpg': ('none', 0.04),
    })

    with app.app_context():
        out = wm.run_watermark(bank_id)

    assert out['scanned'] == 2
    stored = _summaries(app, bank_id)
    assert stored[ids[0]]['watermark_score'] == 0.91
    assert stored[ids[0]]['watermark_state'] == 'ok'
    assert stored[ids[1]]['watermark_score'] == 0.04
    assert stored[ids[1]]['watermark_state'] == 'ok'


def test_a_shot_the_detector_could_not_judge_is_unreadable_never_clean(app, monkeypatch):
    """The ternary contract. A score of 0 for a frame nobody could read would be
    the app asserting the shot is clean."""
    bank_id, ids = _bank_with_clips(app, 2)
    _fake_frames(monkeypatch)
    _fake_detector(monkeypatch, {
        f'clip_{ids[0]}.jpg': ('error', None),
        f'clip_{ids[1]}.jpg': ('none', 0.02),
    })

    with app.app_context():
        out = wm.run_watermark(bank_id)

    stored = _summaries(app, bank_id)
    assert stored[ids[0]]['watermark_state'] == 'unreadable'
    assert stored[ids[0]]['watermark_score'] is None
    assert out['unreadable'] == 1


def test_a_shot_whose_frame_cannot_be_decoded_costs_that_shot(app, monkeypatch):
    """A bank is scanned in bulk; one broken segment among hundreds must leave
    the other verdicts standing."""
    bank_id, ids = _bank_with_clips(app, 2)
    calls = {'n': 0}

    def flaky(src_path, times, dest_dir, stem, long_side=None):
        calls['n'] += 1
        if calls['n'] == 1:
            raise OSError('bitstream error')
        return _written(times, dest_dir, stem)
    monkeypatch.setattr(wm, '_write_frames', flaky)
    _fake_detector(monkeypatch, {f'clip_{ids[1]}.jpg': ('detected', 0.8)})

    with app.app_context():
        out = wm.run_watermark(bank_id)

    stored = _summaries(app, bank_id)
    assert stored[ids[0]]['watermark_state'] == 'unreadable'
    assert stored[ids[1]]['watermark_score'] == 0.8
    assert out['scanned'] == 1


def test_a_detector_that_cannot_load_keeps_what_it_already_judged(app, monkeypatch):
    """DetectorUnavailable is not "no watermarks". It is the one failure the
    caller has to tell apart from a clean bank, because they lead to opposite
    decisions — and the clips judged before it must not be thrown away."""
    from app.services import watermark_detector
    bank_id, ids = _bank_with_clips(app, 2)
    _fake_frames(monkeypatch)

    def dying(paths, **kw):
        raise watermark_detector.DetectorUnavailable('models could not load')
    monkeypatch.setattr(wm, '_scan_frames', dying)

    with app.app_context():
        out = wm.run_watermark(bank_id)

    assert out['scanned'] == 0
    assert out['error']
    assert _summaries(app, bank_id)[ids[0]] == {}


def test_the_verdict_merges_into_the_measurements_it_did_not_write(app, monkeypatch):
    bank_id, ids = _bank_with_clips(app, 1)
    _measured(app, {ids[0]: 42.0})
    _fake_frames(monkeypatch)
    _fake_detector(monkeypatch, {f'clip_{ids[0]}.jpg': ('detected', 0.77)})

    with app.app_context():
        wm.run_watermark(bank_id)

    stored = _summaries(app, bank_id)[ids[0]]
    assert stored['sharpness_p90'] == 42.0
    assert stored['metrics_state'] == 'ok'
    assert stored['watermark_score'] == 0.77


def test_a_second_run_skips_what_is_already_scanned_unless_asked(app, monkeypatch):
    """The resume contract every pass in this lane keeps: a re-run pays only for
    what the first run had not reached."""
    bank_id, ids = _bank_with_clips(app, 2)
    _fake_frames(monkeypatch)
    _fake_detector(monkeypatch, {
        f'clip_{ids[0]}.jpg': ('none', 0.01),
        f'clip_{ids[1]}.jpg': ('none', 0.02),
    })
    with app.app_context():
        wm.run_watermark(bank_id)
        assert wm.run_watermark(bank_id)['scanned'] == 0
        assert wm.run_watermark(bank_id, rescan=True)['scanned'] == 2


def test_the_pass_never_changes_a_triage_decision(app, monkeypatch):
    bank_id, ids = _bank_with_clips(app, 1)
    _fake_frames(monkeypatch)
    _fake_detector(monkeypatch, {f'clip_{ids[0]}.jpg': ('detected', 0.99)})

    with app.app_context():
        from app.models import VideoClip
        wm.run_watermark(bank_id)
        assert db_status(VideoClip, ids[0]) == 'pending'


def db_status(model, clip_id):
    from app.extensions import db
    return db.session.get(model, clip_id).status


# --- helpers ------------------------------------------------------------------------

def _bank_with_clips(app, n):
    from app.extensions import db
    from app.models import VideoBank, VideoClip, VideoSource
    with app.app_context():
        bank = VideoBank(name='b', source_path='/srv/rushes')
        db.session.add(bank)
        db.session.flush()
        src = VideoSource(bank_id=bank.id, relpath='a.mp4', duration_s=60.0,
                          fps_native=25.0, probe_state='ok')
        db.session.add(src)
        db.session.flush()
        ids = []
        for i in range(n):
            clip = VideoClip(bank_id=bank.id, source_id=src.id,
                             start_s=float(i * 10), end_s=float(i * 10 + 5))
            db.session.add(clip)
            db.session.flush()
            ids.append(clip.id)
        db.session.commit()
        return bank.id, ids


def _written(times, dest_dir, stem):
    import os
    out = []
    os.makedirs(dest_dir, exist_ok=True)
    for label, t in times:
        path = os.path.join(dest_dir, f'{stem}.jpg')
        with open(path, 'wb') as fh:
            fh.write(b'not really a jpeg')
        out.append((label, t, path))
    return out


def _fake_frames(monkeypatch):
    """The decode seam, stubbed — nothing here needs PyAV."""
    monkeypatch.setattr(wm, '_write_frames',
                        lambda src, times, dest, stem, long_side=None:
                        _written(times, dest, stem))


def _fake_detector(monkeypatch, by_name):
    """The detector child, stubbed. Keyed on the frame's FILENAME because that is
    what the real generator echoes back, and attaching one clip's verdict to
    another clip's row is the single worst thing this pass could do."""
    import os

    def scan(paths, **kw):
        for p in paths:
            state, score = by_name.get(os.path.basename(p), ('error', None))
            yield (p, state, score, [], None if state != 'error' else 'boom')
    monkeypatch.setattr(wm, '_scan_frames', scan)


def _measured(app, sharpness_by_id):
    from app.extensions import db
    from app.models import VideoClip
    with app.app_context():
        for cid, sharp in sharpness_by_id.items():
            db.session.get(VideoClip, cid).metrics_json = json.dumps(
                {'metrics_state': 'ok', 'sharpness_p90': sharp})
        db.session.commit()


def _summaries(app, bank_id):
    from app.models import VideoClip
    with app.app_context():
        rows = VideoClip.query.filter_by(bank_id=bank_id).all()
        return {r.id: (json.loads(r.metrics_json) if r.metrics_json else {})
                for r in rows}
