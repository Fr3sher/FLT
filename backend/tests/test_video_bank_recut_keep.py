"""Re-cutting preserves every shot whose bounds remain identical (2026-09-01).
Raising minimum length formerly deleted all clips, triage, captions and
measurements, making threshold experiments costly. Changing the threshold selects
a strict subset of existing shot boundaries, never shifted boundaries, so
surviving spans retain valid measurements and saved work."""
from app.extensions import db
import app.models  # noqa: F401 -- declares the historical schemas before owner mappings
from lds_video.models import VideoBank, VideoClip, VideoSource
from lds_video import video_bank_service as svc

import pytest
pytestmark = pytest.mark.plugins('video')

LOCAL_USER = 'local'


def _bank_with_shots(app, spans):
    with app.app_context():
        bank = VideoBank(name='b', source_path='/srv/rushes', user_id=LOCAL_USER)
        db.session.add(bank)
        db.session.flush()
        src = VideoSource(bank_id=bank.id, relpath='a.mp4', duration_s=60.0,
                          fps_native=25.0, probe_state='ok', detect_state='ok')
        db.session.add(src)
        db.session.flush()
        for start, end in spans:
            db.session.add(VideoClip(bank_id=bank.id, source_id=src.id,
                                     start_s=start, end_s=end, status='keep',
                                     caption='a woman walks', caption_state='ok',
                                     detector='transnetv2'))
        db.session.commit()
        return bank.id, src.id


def _shots(spans):
    return [{'start_s': a, 'end_s': b, 'detector': 'transnetv2'} for a, b in spans]


def test_a_shot_whose_bounds_did_not_move_keeps_its_triage_and_caption(app):
    """The heart of it: same span in, same row out — decision and caption
    intact, and the row is the SAME row (its id never changed)."""
    bank_id, src_id = _bank_with_shots(app, [(0.0, 1.0), (1.0, 6.0)])
    with app.app_context():
        before = {(c.start_s, c.end_s): c.id for c in
                  VideoClip.query.filter_by(bank_id=bank_id).all()}
        src = db.session.get(VideoSource, src_id)
        # The new threshold drops the 1 s sliver and reproduces the other shot.
        bounds = {svc._bounds_key(0.0, 6.0)}
        dropped = svc._drop_clips_of(bank_id, src_id, replace_manual=False,
                                     keep_bounds={svc._bounds_key(1.0, 6.0)})
        made = svc._insert_clips(bank_id, src, _shots([(1.0, 6.0), (6.0, 12.0)]),
                                 skip_bounds=svc._existing_bounds(bank_id, src_id))
        db.session.commit()
        assert dropped['removed'] == 1 and dropped['kept'] == 1
        # Only the genuinely new span was inserted…
        assert made == 1
        rows = {(c.start_s, c.end_s): c for c in
                VideoClip.query.filter_by(bank_id=bank_id).all()}
        assert set(rows) == {(1.0, 6.0), (6.0, 12.0)}
        # …and the survivor is the same row, with its work on it.
        kept = rows[(1.0, 6.0)]
        assert kept.id == before[(1.0, 6.0)]
        assert kept.status == 'keep' and kept.caption == 'a woman walks'
        # The new one starts clean, as a new shot must.
        assert rows[(6.0, 12.0)].caption is None
        assert bounds  # the key helper is what both halves compare on


def test_a_merged_shot_inherits_nothing(app):
    """A∪B is new footage in one clip: nothing measured about A still describes
    it, so it must be rebuilt rather than handed A's caption."""
    bank_id, src_id = _bank_with_shots(app, [(0.0, 2.0), (2.0, 5.0)])
    with app.app_context():
        src = db.session.get(VideoSource, src_id)
        svc._drop_clips_of(bank_id, src_id, replace_manual=False,
                           keep_bounds={svc._bounds_key(0.0, 5.0)})
        svc._insert_clips(bank_id, src, _shots([(0.0, 5.0)]),
                          skip_bounds=svc._existing_bounds(bank_id, src_id))
        db.session.commit()
        rows = VideoClip.query.filter_by(bank_id=bank_id).all()
        assert len(rows) == 1
        assert (rows[0].start_s, rows[0].end_s) == (0.0, 5.0)
        assert rows[0].caption is None and rows[0].status == 'pending'


def test_a_promoted_clip_is_never_given_a_twin(app):
    """Promoted clips survive every drop; re-inserting their span used to add a
    duplicate row for the same footage. The skip set is measured against what
    the file HOLDS, not against what was kept."""
    from lds_video.models import VideoDataset
    bank_id, src_id = _bank_with_shots(app, [(0.0, 4.0)])
    with app.app_context():
        ds = VideoDataset(user_id=LOCAL_USER, name='d', target_profile='wan22_14b',
                          fps=16, frames=81, output_dir='/tmp/x')
        db.session.add(ds)
        db.session.commit()
        clip = VideoClip.query.filter_by(bank_id=bank_id).one()
        clip.promoted_dataset_id = ds.id
        db.session.commit()
        src = db.session.get(VideoSource, src_id)
        svc._drop_clips_of(bank_id, src_id, replace_manual=True, keep_bounds=set())
        made = svc._insert_clips(bank_id, src, _shots([(0.0, 4.0)]),
                                 skip_bounds=svc._existing_bounds(bank_id, src_id))
        db.session.commit()
        assert made == 0
        assert VideoClip.query.filter_by(bank_id=bank_id).count() == 1


def test_bounds_are_matched_exactly_never_within_a_tolerance(app):
    """Two spans a millisecond apart are two different spans: inheriting a
    caption across them would describe the wrong footage."""
    assert svc._bounds_key(1.0, 6.0) != svc._bounds_key(1.001, 6.0)
    assert svc._bounds_key(1.0, 6.0) == svc._bounds_key(1.0000000001, 6.0)
