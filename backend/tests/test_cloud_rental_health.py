"""Failed GPU hosts cannot remain paid behind a stale 'Starting job' status."""
import pytest
from app.extensions import db
from test_cloud_training_monitor import ct, FakeRemote, _launch  # noqa: F401
from public_cloud_test_io import no_cloud_provider_io  # noqa: F401

pytestmark = pytest.mark.plugins('cloud_training')


@pytest.mark.parametrize('message', [
    'Error response from daemon: failed to inject CDI devices: unresolvable CDI devices gpu=0',
    'Error response from daemon: driver failed programming external connectivity on endpoint',
])
def test_confirmed_host_startup_failure_releases_without_waiting_for_timeout(
        ct, app, client, monkeypatch, message):
    remote = FakeRemote()
    remote.is_ready = lambda: False
    destroyed = []
    _, run_id = _launch(ct, app, client, monkeypatch, remote, destroyed)
    monkeypatch.setattr(ct, '_maybe_auto_retry', lambda *a: None)
    monkeypatch.setattr(ct.vast_client, 'get_instance', lambda iid, **kw: {
        'instance_id': iid, 'label': remote.rental['label'],
        'actual_status': 'created', 'status_msg': message})
    sleeps = []
    monkeypatch.setattr(ct, '_sleep', lambda _: sleeps.append(1))
    with app.app_context():
        ct._monitor(app, run_id)
        run = db.session.get(ct.CloudTrainingRun, run_id)
        assert run.status == 'error'
        assert 'pod container startup failed' in run.error
        assert len(sleeps) == 1
        assert remote.job_config is None
        assert destroyed == ['777']
        assert '43503' in ct._load_bad_hosts()


def test_cuda_crash_with_stale_running_status_releases_and_retries_once(
        ct, app, client, monkeypatch):
    remote = FakeRemote()
    destroyed = []
    _, run_id = _launch(ct, app, client, monkeypatch, remote, destroyed)
    remote.get_job = lambda _: {'status': 'running', 'step': 0, 'info': 'Starting job...'}
    remote.get_log = lambda _: ('Traceback (most recent call last):\n'
                              'RuntimeErrorRuntimeError: CUDA unknown error - available devices zero.\n')
    retries = []
    monkeypatch.setattr(ct, '_maybe_auto_retry', lambda *args: retries.append(args))
    with app.app_context():
        ct._monitor(app, run_id)
        run = db.session.get(ct.CloudTrainingRun, run_id)
        assert run.status == 'error'
        assert 'pod GPU initialization failed' in run.error
        assert remote.stopped
        assert destroyed == ['777']
        assert len(retries) == 1
        assert '43503' in ct._load_bad_hosts()


@pytest.mark.parametrize('progressing', [False, True])
def test_stale_or_recovered_gpu_error_does_not_kill_a_healthy_job(
        ct, app, client, monkeypatch, progressing):
    remote = FakeRemote(polls_to_complete=4)
    destroyed = []
    _, run_id = _launch(ct, app, client, monkeypatch, remote, destroyed)
    if progressing:
        remote.get_log = lambda _: 'RuntimeError: CUDA unknown error'
    else:
        # The first observation fails, then the next log reports recovery.
        remote.get_log = lambda _: ('RuntimeError: CUDA unknown error' if remote.polls == 1
                                    else 'RuntimeError: CUDA unknown error\nLoading model weights: 60%')
        original = remote.get_job
        def job(job_id):
            value = original(job_id)
            if value['status'] == 'running':
                value['step'] = 0
            return value
        remote.get_job = job
    with app.app_context():
        ct._monitor(app, run_id)
        run = db.session.get(ct.CloudTrainingRun, run_id)
        assert run.status == 'done'
        assert not remote.stopped
        assert ct._load_bad_hosts() == {}


def test_verified_host_is_preferred_within_the_existing_price_window(ct):
    offers = [
        {'offer_id': 1, 'dph_total': .50, 'reliability': 1, 'verified': False},
        {'offer_id': 2, 'dph_total': .54, 'reliability': .99, 'verified': True},
        {'offer_id': 3, 'dph_total': 2, 'reliability': 1, 'verified': True},
    ]
    assert ct._best_of(offers)['offer_id'] == 2


def test_training_search_uses_the_actual_image_cuda_floor(ct, app, client, monkeypatch):
    remote = FakeRemote()
    destroyed = []
    _, run_id = _launch(ct, app, client, monkeypatch, remote, destroyed)
    searches = []
    original = ct.vast_client.search_offers
    def search(**kwargs):
        searches.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(ct.vast_client, 'search_offers', search)
    with app.app_context():
        ct._monitor(app, run_id)
    assert searches[0]['min_cuda'] == 12.9
    assert searches[0]['limit'] == 100
