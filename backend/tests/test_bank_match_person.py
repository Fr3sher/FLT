"""🎯 Keep this person — auto-decide a bank against one reference face.

The pass scores every non-rejected image against a single reference embedding and
auto-decides it: matches → keep, no face / different person → reject. Only
'pending' rows are flipped (a manual decision is never overridden), and the
reference itself is kept. This pins the write-back semantics without running
InsightFace (score_faces is mocked)."""
import pytest
from PIL import Image


def _bank(workdir, n=4):
    from app.services import image_bank_service as banks
    src = workdir / 'src'
    src.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new('RGB', (900, 900), (10 * i, 90, 160)).save(str(src / f'a{i}.jpg'))
    bank, _added = banks.create_bank('local', 'Dump', str(src))
    from app.extensions import db
    db.session.commit()
    return bank.id


def _ids(bank_id):
    from app.models import BankImage
    return [r.id for r in BankImage.query.filter_by(bank_id=bank_id)
            .order_by(BankImage.id.asc()).all()]


def _new_job():
    return {'kind': 'match_person', 'done': 0, 'total': 0, 'error': None,
            'cancelled': False, 'finished': False, 'detail': None,
            'started_at': 0.0, '_touched': 0.0, '_cancel_hook': None,
            'pipeline': None}


@pytest.fixture()
def bank_ctx(app, tmp_path):
    with app.app_context():
        bank_id = _bank(tmp_path)
        yield bank_id, _ids(bank_id)


def _paths(bank_id):
    from app.models import BankImage
    from app.services import image_bank_service as banks
    bank = banks.get_bank('local', bank_id)
    return {r.id: banks.analysis_image_path(bank, r)
            for r in BankImage.query.filter_by(bank_id=bank_id).all()}


def test_match_person_auto_decides_pending_rows(bank_ctx, monkeypatch):
    from app.extensions import db
    from app.models import BankImage
    from app.services import image_bank_service as banks

    bank_id, ids = bank_ctx
    ref_id = ids[0]
    paths = _paths(bank_id)

    def fake_score_faces(refs, images, quality_only=False, lenient=False,
                         timeout=None, on_progress=None):
        # id1 matches the reference, id2 has no face, id3 is a different person.
        results = {}
        for i, p in paths.items():
            if i == ids[1]:
                results[p] = {'state': 'scorable', 'sim': 0.72}
            elif i == ids[2]:
                results[p] = {'state': 'no_face', 'sim': None}
            else:
                results[p] = {'state': 'scorable', 'sim': 0.20}
        return results, None

    monkeypatch.setattr('app.services.face_similarity.score_faces', fake_score_faces)

    job = _new_job()
    banks._match_person_job(bank_id, ref_id, 0.5)(job)
    assert job['error'] is None, job['error']

    rows = {r.id: r for r in BankImage.query.filter_by(bank_id=bank_id).all()}
    assert rows[ref_id].status == 'keep', 'the reference anchor must be kept'
    assert rows[ids[1]].status == 'keep', 'a strong match must be kept'
    assert rows[ids[2]].status == 'reject' and rows[ids[2]].reject_reason == 'no_face'
    assert rows[ids[3]].status == 'reject' and rows[ids[3]].reject_reason == 'different_person'
    assert 'kept' in job['detail'] and 'different person' in job['detail']


def test_match_person_never_flips_a_manual_decision(bank_ctx, monkeypatch):
    from app.extensions import db
    from app.models import BankImage
    from app.services import image_bank_service as banks

    bank_id, ids = bank_ctx
    ref_id = ids[0]
    # The user already rejected ids[1] by hand; the pass must not change it.
    row1 = db.session.get(BankImage, ids[1])
    row1.status, row1.reject_reason = 'reject', 'manual'
    db.session.commit()
    paths = _paths(bank_id)

    def fake_score_faces(refs, images, quality_only=False, lenient=False,
                         timeout=None, on_progress=None):
        return {p: {'state': 'scorable', 'sim': 0.9} for p in paths.values()}, None

    monkeypatch.setattr('app.services.face_similarity.score_faces', fake_score_faces)
    job = _new_job()
    banks._match_person_job(bank_id, ref_id, 0.5)(job)
    assert job['error'] is None, job['error']
    rows = {r.id: r for r in BankImage.query.filter_by(bank_id=bank_id).all()}
    assert rows[ids[1]].status == 'reject' and rows[ids[1]].reject_reason == 'manual', \
        'a manual reject must survive the pass'
