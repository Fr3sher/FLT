"""No real worker: drive terminalization and nested callbacks synchronously."""
from types import SimpleNamespace

import pytest

from test_public_backend_mount import factory  # noqa: F401
from app import job_queue as queue
from app.extensions import db
from app.models import ImageGenerationQueue


def test_terminal_result_still_reserves_restart_until_dispatch_returns(factory, monkeypatch):
    app = factory()
    monkeypatch.setattr('app.services.vision_keepalive.ensure_released_for_comfy', lambda: True)
    monkeypatch.setattr(queue, '_submit', lambda *_: 'fake-prompt')
    monkeypatch.setattr(queue, '_poll_outputs', lambda *_: ('fake.png', False))
    observed = []
    def finalized(job, *_):
        assert job.status == 'completed'
        observed.append(queue.queue_execution_busy())
        assert queue.GPU_ARBITER_LOCK.acquire(blocking=False)
        queue.GPU_ARBITER_LOCK.release()
        from app.plugins.restart import _Gate, _lock_and_check_work, RestartBlocked
        gate = _Gate()
        gate.freeze()
        try:
            with pytest.raises(RestartBlocked, match='still being finalized'):
                _lock_and_check_work(gate, app.extensions['lds_plugins'])
        finally:
            gate.release()
    monkeypatch.setattr(queue, '_dispatch_completion', finalized)
    with app.app_context():
        queue.queue_manager.add_job(workflow_data={'fake': {}})
        assert queue.queue_manager.process_one()
        assert observed == [True]
        assert not queue.queue_execution_busy()


def test_dispatch_exception_releases_execution_reservation(factory, monkeypatch):
    app = factory()
    monkeypatch.setattr('app.services.vision_keepalive.ensure_released_for_comfy', lambda: True)
    monkeypatch.setattr(queue, '_submit', lambda *_: 'fake-prompt')
    monkeypatch.setattr(queue, '_poll_outputs', lambda *_: ('fake.png', False))
    monkeypatch.setattr(queue, '_dispatch_completion', lambda *_: (_ for _ in ()).throw(RuntimeError('fixture')))
    with app.app_context():
        queue.queue_manager.add_job(workflow_data={'fake': {}})
        with pytest.raises(RuntimeError, match='fixture'):
            queue.queue_manager.process_one()
    assert not queue.queue_execution_busy()


def test_owned_completion_dispatches_once_and_off_preserves_result(factory, monkeypatch):
    app = factory({'video'})
    registry = app.extensions['lds_plugins']
    calls = []
    registry.job_handlers['is_video_test'] = ('video', lambda *args, **kw: calls.append((args, kw, queue.queue_execution_busy())))
    monkeypatch.setattr(queue, '_drop_staged_inputs', lambda *_: None)
    job = SimpleNamespace(status='completed', job_id='fixture', error_message=None,
                          job_metadata='{"is_video_test": true}')
    with app.app_context():
        queue._dispatch_completion(job, 'fixture.mp4', False)
        assert len(calls) == 1 and calls[0][2]
        registry.records['video'].enabled = False
        queue._dispatch_completion(job, 'fixture.mp4', False)
        assert len(calls) == 1
        assert ImageGenerationQueue.query.count() == 0
        db.session.rollback()
    assert not queue.queue_execution_busy()


def test_off_owned_pending_job_is_preserved_and_does_not_block_core(factory, monkeypatch):
    app = factory()
    monkeypatch.setattr('app.services.vision_keepalive.ensure_released_for_comfy', lambda: True)
    monkeypatch.setattr(queue, '_submit', lambda *_: 'fake-prompt')
    monkeypatch.setattr(queue, '_poll_outputs', lambda *_: ('fake.png', False))
    monkeypatch.setattr(queue, '_dispatch_completion', lambda *_: None)
    with app.app_context():
        owned = queue.queue_manager.add_job(workflow_data={'fake': {}}, metadata={'is_video_test': True}, priority=20)
        core = queue.queue_manager.add_job(workflow_data={'fake': {}}, priority=10)
        assert queue.queue_manager.process_one()
        assert ImageGenerationQueue.query.filter_by(job_id=owned).one().status == 'pending'
        assert ImageGenerationQueue.query.filter_by(job_id=core).one().status == 'completed'
        assert not queue.queue_manager.process_one()
