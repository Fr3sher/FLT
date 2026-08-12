"""Every standalone pass journals its completed run — not just ✂.

The Launch-all report annotates a step "re-run since" from the ``last_passes``
journal, and for as long as only ``semantic_dedup`` wrote its row, a report's
red "👥 Group by person — cancelled before it ran" outlived any number of
successful standalone re-runs. The fix is a completion hook on the job runner
(``bank_jobs.on_complete``), so the rule is one place and every pass kind gets
it; these tests pin down its contract:

* a job that completes cleanly journals under its report-step key;
* an errored or cancelled run journals NOTHING — the step's story has not
  moved on, and whitewashing a report row over a stop at 3% would be a lie;
* kinds that are not report steps (promote, angles, the pipeline itself) and
  the video lane's string keys stay out of the journal;
* ``semantic_dedup`` keeps writing its own richer row (engine, threshold,
  signature) — the generic hook must not overwrite it with a plain one.
"""
import json

import pytest


@pytest.fixture()
def bank(app):
    with app.app_context():
        from app.models import ImageBank, db
        row = ImageBank(user_id='local', name='journal-bank', source_path=r'C:\nowhere')
        db.session.add(row)
        db.session.commit()
        yield row.id


def _journal(app, bank_id):
    with app.app_context():
        from app.models import ImageBank, db
        return json.loads(db.session.get(ImageBank, bank_id).last_passes or '{}')


def _run_job(app, bank_id, kind, fn):
    from app.services import bank_jobs
    return bank_jobs.start(app, bank_id, kind, fn)


def test_a_clean_completion_journals_the_step(app, bank):
    def fn(job):
        from app.services import bank_jobs
        bank_jobs.progress(job, done=3, total=3, detail='done — 3 face group(s)')
    _run_job(app, bank, 'faces', fn)
    row = _journal(app, bank).get('faces')
    assert row and row['at'] > 0
    assert row['detail'] == 'done — 3 face group(s)'


def test_every_report_step_kind_is_covered(app):
    """The map exists so a NEW pass kind fails here instead of silently keeping
    its red report row forever. Frontend STEP_LABEL lists the report's steps."""
    from app.services.image_bank_service import _JOURNALED_JOB_KINDS
    assert set(_JOURNALED_JOB_KINDS) == {
        'scan', 'score', 'faces', 'watermark', 'framing', 'caption',
        'semantic_index'}


def test_an_errored_run_journals_nothing(app, bank):
    def fn(job):
        raise RuntimeError('boom')
    _run_job(app, bank, 'faces', fn)
    assert 'faces' not in _journal(app, bank)


def test_a_cancelled_run_journals_nothing(app, bank):
    def fn(job):
        from app.services import bank_jobs
        bank_jobs.cancel(bank)
        bank_jobs.progress(job, detail='cancelled — 1 so far')
    _run_job(app, bank, 'watermark', fn)
    assert 'watermark' not in _journal(app, bank)


def test_non_report_kinds_stay_out_of_the_journal(app, bank):
    def fn(job):
        from app.services import bank_jobs
        bank_jobs.progress(job, detail='done')
    for kind in ('angles', 'medium', 'pipeline', 'bank_promote'):
        _run_job(app, bank, kind, fn)
    assert _journal(app, bank) == {}


def test_the_video_lane_string_key_never_reaches_the_journal(app):
    """video_bank_service keys jobs on 'video:<id>'; note_pass_run would look
    that up as an image-bank id. The hook must simply skip it, not crash the
    landing of every video pass."""
    def fn(job):
        from app.services import bank_jobs
        bank_jobs.progress(job, detail='done — video pass')
    job = _run_job(app, 'video:999', 'scan', fn)
    assert job['finished'] and job['error'] is None


def test_semantic_dedup_keeps_its_own_richer_row(app, bank):
    """The ✂ row carries engine/threshold/signature that the launch window
    reads back. The generic hook writing a plain {detail} row for the same key
    would erase them the moment the job thread finished."""
    def fn(job):
        from app.services import bank_jobs
        from app.services.image_bank_service import note_pass_run
        note_pass_run(bank, 'semantic_dedup', detail='42 group(s)',
                      counts={'semantic_groups': 42}, engine='clip',
                      threshold=0.9, signature='sig')
        bank_jobs.progress(job, detail='done — 42 semantic near-duplicate group(s)')
    _run_job(app, bank, 'semantic_dedup', fn)
    row = _journal(app, bank)['semantic_dedup']
    assert row['engine'] == 'clip' and row['signature'] == 'sig'
    assert row['counts'] == {'semantic_groups': 42}
