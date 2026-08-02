"""🗃️ Image bank — an inference pass holds NO database transaction while it waits.

The face and score passes read their rows, hand a path list to a child process,
and only write results back when the child returns. That wait is not short: the
scoring extra ships CPU-only torch on purpose and a big bank measures near an
hour. Keeping the session's transaction open across it is a loaded gun — WAL
gives concurrent readers, never concurrent WRITERS, so one write joining that
transaction ahead of the child takes the single write lock for the whole pass
and every other writer dies on `database is locked` past the 5 s busy_timeout.
Two paid cloud runs were already abandoned that way on 2026-07-26 by a holder
that lasted five seconds.

These tests pin the invariant rather than the symptom: while the pass sits in
the subprocess, another connection to the same database must be able to write.
They need a FILE database (the shared `app` fixture's `:memory:` one cannot be
opened twice) and keep the app's real journal mode, so the lock they measure is
the lock a real install has.
"""
import sqlite3
from unittest.mock import patch

import pytest
from PIL import Image
from sqlalchemy import text


@pytest.fixture()
def file_db(tmp_path, monkeypatch):
    """(app, db_path, workdir) — a real app on a file-backed SQLite database."""
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / '.env'))
    from app import config as cfg
    monkeypatch.setattr(cfg, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.setattr(cfg, '_cache', None)
    from app import create_app
    from app.extensions import db

    application = create_app({'TESTING': True, 'WTF_CSRF_ENABLED': False})
    with application.app_context():
        mode = db.session.execute(text('PRAGMA journal_mode')).scalar()
        db.session.commit()
    # Recorded, not forced: whatever the app configures is what the test measures.
    # WAL is not an escape — it removes reader/writer contention, not the single
    # write lock these tests are about.
    assert str(mode).lower() in ('wal', 'delete'), f'unexpected journal mode {mode!r}'
    return application, str(tmp_path / 'data' / 'studio.db'), tmp_path


def _bank_with_images(workdir, n=2):
    from app.services import image_bank_service as banks
    src = workdir / 'src'
    src.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new('RGB', (800, 800), (10 * i, 90, 160)).save(str(src / f'a{i}.jpg'))
    bank, _added = banks.create_bank('local', 'Dump', str(src))
    return bank.id


def _concurrent_write(db_path):
    """Try a write from ANOTHER connection, as a live request would. Returns None
    on success, else the SQLite error text ('database is locked' when blocked)."""
    con = sqlite3.connect(db_path, timeout=0.5)
    try:
        con.execute("UPDATE image_bank SET name = 'written while inferring'")
        con.commit()
        return None
    except sqlite3.OperationalError as e:
        return str(e)
    finally:
        con.close()


def _writer_verdict_during_inference(file_db, make_job):
    """Run a bank inference pass whose session already carries an uncommitted
    write, and report what a concurrent writer saw from inside the subprocess."""
    from app.extensions import db
    from app.models import ImageBank
    from app.services import image_bank_service as banks

    app, db_path, workdir = file_db
    seen = {}
    with app.app_context():
        bank_id = _bank_with_images(workdir)
        db.session.commit()
        # A write pending on the session when the pass reaches the child. Nothing
        # on today's nominal path does this; the contract is that it would stay
        # harmless if it did, instead of becoming an hour-long global write lock.
        db.session.get(ImageBank, bank_id).name = 'renamed just before inferring'
        db.session.flush()

        def fake_drive(job, python, script, payload, cache_path, progress_re, window):
            seen['error'] = _concurrent_write(db_path)
            return {'ok': True, 'results': {}, 'clusters': {}}, [], 0

        with patch.object(banks, '_drive_infer_subprocess', fake_drive), \
             patch.object(banks.bank_jobs, 'cancelled', lambda job: False), \
             patch.object(banks.bank_jobs, 'progress', lambda job, **kw: None), \
             patch('app.capabilities.bank_scoring_gpu_available', lambda: False), \
             patch.object(banks, '_resolve_face_device', lambda: ('cpu', False)):
            make_job(banks, bank_id)(object())
        assert seen, 'the pass never reached the inference subprocess'
    return seen['error']


def test_the_score_pass_lets_other_writers_through_while_it_infers(file_db):
    error = _writer_verdict_during_inference(
        file_db, lambda banks, bank_id: banks._score_job(bank_id))
    assert error is None, (
        'the scoring pass held a write lock through the inference — a real pass '
        f'would block every other writer for its whole duration ({error})')


def test_the_face_pass_lets_other_writers_through_while_it_infers(file_db):
    error = _writer_verdict_during_inference(
        file_db, lambda banks, bank_id: banks._faces_job(bank_id))
    assert error is None, (
        f'the face pass held a write lock through the inference ({error})')


def test_the_release_helper_really_ends_the_transaction(file_db):
    """The guard on its own: a flush blocks other writers, and the helper frees
    them. Without the first assertion the two tests above could pass for the
    wrong reason (a flush that never locked anything proves nothing)."""
    from app.extensions import db
    from app.models import ImageBank
    from app.services import image_bank_service as banks

    app, db_path, _workdir = file_db
    with app.app_context():
        db.session.add(ImageBank(user_id='local', name='Dump', source_path='x'))
        db.session.flush()
        assert _concurrent_write(db_path), 'a pending write must lock the file'
        banks._release_db_before_inference()
        assert _concurrent_write(db_path) is None
