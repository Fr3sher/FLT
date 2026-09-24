"""Real disable HTTP and registered filters, with only temporary local work state."""
import pytest

from test_public_backend_mount import factory  # noqa: F401
from app.extensions import db
from app.models import CloudTrainingRun, SystemState


def _client(app):
    app.config['WTF_CSRF_ENABLED'] = True
    client = app.test_client()
    token = client.get('/api/csrf-token').json['csrf_token']
    return client, {'X-CSRFToken': token}


def _product(client, pid):
    return next(row for row in client.get('/api/plugins/').json['plugins'] if row['id'] == pid)


@pytest.mark.parametrize('enabled', [{'cloud_training'}, {'cloud_training', 'live'}])
def test_idle_cloud_disable_is_accepted_with_real_registered_filters(factory, enabled):
    app = factory(enabled)
    client, headers = _client(app)
    assert _product(client, 'cloud_training')['state'] == 'loaded'
    response = client.post('/api/plugins/cloud_training/disable', json={}, headers=headers)
    assert response.status_code == 200, response.json
    assert response.json['enabled'] is False
    assert _product(client, 'cloud_training')['pending_action'] == 'disable'


@pytest.mark.parametrize('work, phrase', [
    ('training', 'active cloud training runs'),
    ('error_pod_kept', 'kept cloud training pod'),
    ('quantizing', 'cloud quantization to finish'),
    ('rental', 'cloud quantization rental'),
    ('delivery', 'FP8 model delivery'),
    ('quantize_lock', 'cloud quantization to finish'),
    ('delivery_lock', 'FP8 model delivery'),
])
def test_busy_cloud_disable_preserves_work_and_reports_a_complete_reason(factory, work, phrase):
    app = factory({'cloud_training', 'live'})
    from lds_cloud_training import cloud_quantize as quantize, fp8_local_delivery as delivery

    client, headers = _client(app)
    held_lock = None
    with app.app_context():
        if work in ('training', 'error_pod_kept'):
            db.session.add(CloudTrainingRun(dataset_id=1, status=work, train_params='{}'))
            db.session.commit()
        elif work == 'quantizing':
            quantize.queue_manager._set_system_state('cloud_quantize', {'status': 'running'}, ttl_seconds=None)
        elif work == 'rental':
            db.session.add(SystemState(key='cloud_quantize_rental', value='damaged-local-receipt'))
            db.session.commit()
        elif work == 'delivery':
            delivery.queue_manager._set_system_state('fp8_local_delivery', {'status': 'downloading'}, ttl_seconds=None)
        else:
            held_lock = quantize._lock if work == 'quantize_lock' else delivery._lock
            assert held_lock.acquire(blocking=False)
    try:
        response = client.post('/api/plugins/cloud_training/disable', json={}, headers=headers)
        assert response.status_code == 409, response.json
        assert len(response.json['blockers']) == 1
        assert phrase in response.json['error']
        assert response.json['blockers'] == [response.json['error']]
        assert _product(client, 'cloud_training')['pending_action'] is None
        with app.app_context():
            if work in ('training', 'error_pod_kept'):
                assert CloudTrainingRun.query.one().status == work
            elif work == 'rental':
                assert db.session.get(SystemState, 'cloud_quantize_rental').value == 'damaged-local-receipt'
    finally:
        if held_lock is not None:
            held_lock.release()


def test_cloud_work_does_not_block_disabling_an_idle_unrelated_owner(factory):
    app = factory({'cloud_training', 'live'})
    client, headers = _client(app)
    with app.app_context():
        db.session.add(CloudTrainingRun(dataset_id=1, status='training', train_params='{}'))
        db.session.commit()
    response = client.post('/api/plugins/live/disable', json={}, headers=headers)
    assert response.status_code == 200, response.json
    assert _product(client, 'live')['pending_action'] == 'disable'
    assert _product(client, 'cloud_training')['pending_action'] is None
