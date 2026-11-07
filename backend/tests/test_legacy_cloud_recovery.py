"""A V1 rental survives V2's empty Store without admitting replacement pods."""
from types import SimpleNamespace

import pytest

from public_cloud_test_io import no_cloud_provider_io  # noqa: F401

pytestmark = pytest.mark.plugins()


@pytest.fixture
def recovery(app, monkeypatch):
    from app.services import cloud_training as cloud
    from app.services import legacy_cloud_recovery as bridge

    calls = []
    monkeypatch.setattr(cloud, 'start_supervisor', lambda host: calls.append(('supervisor', host)))
    monkeypatch.setattr(cloud, 'boot_recover', lambda host: calls.append(('recover', host)))

    class InlineThread:
        def __init__(self, *, target, args, **kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(bridge, 'threading', SimpleNamespace(Thread=InlineThread))
    return bridge, cloud, calls


def add_run(app, status, instance='700'):
    from app.extensions import db
    from app.models import CloudTrainingRun

    with app.app_context():
        row = CloudTrainingRun(dataset_id=1, status=status, vast_instance_id=instance,
                               vast_label='lds-1', job_name='legacy')
        db.session.add(row)
        db.session.commit()
        return row.id


@pytest.mark.parametrize('status', ['training', 'error_pod_kept'])
def test_existing_rental_is_supervised_without_enabling_features(app, recovery, status):
    bridge, _, calls = recovery
    add_run(app, status)
    registry = app.extensions['lds_plugins']
    routes = set(str(rule) for rule in app.url_map.iter_rules())
    assert bridge.start(app) is True
    assert [kind for kind, _ in calls] == ['supervisor', 'recover']
    assert bridge.start(app) is False  # A repeated startup never duplicates recovery.
    assert len(calls) == 2
    assert registry.records == {}
    assert set(str(rule) for rule in app.url_map.iter_rules()) == routes
    with app.app_context():
        from app.auth_policy import plugin_available
        assert not plugin_available('cloud_training')
        assert bridge.recovery_only()


def test_clean_install_has_no_cloud_workers(app, recovery):
    bridge, _, calls = recovery
    assert bridge.start(app) is False
    assert calls == []
    with app.app_context():
        assert not bridge.recovery_only()


@pytest.mark.parametrize('status', ['done', 'error', 'stopped'])
def test_failed_termination_of_terminal_rental_is_reconciled(app, recovery, monkeypatch, status):
    bridge, cloud, calls = recovery
    from app.extensions import db
    from app.models import CloudTrainingRun

    run_id = add_run(app, 'training')
    monkeypatch.setenv('VAST_API_KEY', 'test-only-key')
    destroyed = []

    def destroy(instance):
        destroyed.append(instance)
        return len(destroyed) > 1  # The original termination fails; recovery succeeds.

    monkeypatch.setattr(cloud.vast_client, 'destroy_instance', destroy)
    monkeypatch.setattr(cloud.vast_client, 'list_instances',
                        lambda: [{'instance_id': '700', 'label': f'lds-{run_id}'}])
    with app.app_context():
        row = db.session.get(CloudTrainingRun, run_id)
        assert cloud._finish(row, status) is False
        assert row.status == status
        assert row.vast_instance_id == '700'

    assert bridge.start(app) is True
    assert [kind for kind, _ in calls] == ['supervisor', 'recover']
    assert cloud.reconcile_orphans(app) == 1
    assert destroyed == ['700', '700']
    with app.app_context():
        with pytest.raises(RuntimeError, match='before renting another pod'):
            cloud._provision(SimpleNamespace())


def test_historical_intent_recovers_pod_without_persisted_instance_id(app, recovery, monkeypatch):
    bridge, cloud, _ = recovery
    run_id = add_run(app, 'error', instance=None)
    monkeypatch.setenv('VAST_API_KEY', 'test-only-key')
    monkeypatch.setattr(cloud.vast_client, 'list_instances',
                        lambda: [{'instance_id': '700', 'label': f'lds-{run_id}'}])
    destroyed = []
    monkeypatch.setattr(cloud.vast_client, 'destroy_instance',
                        lambda instance: destroyed.append(instance) or True)
    assert bridge.start(app) is True
    assert cloud.reconcile_orphans(app) == 1
    assert destroyed == ['700']


@pytest.mark.parametrize('state,recovery_active', [('loaded', False), ('disabled', True)])
def test_plugin_owned_recovery_is_not_duplicated(app, recovery, state, recovery_active):
    bridge, _, calls = recovery
    add_run(app, 'training')
    app.extensions['lds_plugins'].records['cloud_training'] = SimpleNamespace(
        state=state, recovery_active=recovery_active)
    assert bridge.start(app) is False
    assert calls == []


def test_disabled_plugin_still_recovers_existing_rental(app, recovery):
    bridge, _, calls = recovery
    add_run(app, 'error_pod_kept')
    app.extensions['lds_plugins'].records['cloud_training'] = SimpleNamespace(
        state='disabled', recovery_active=False)
    assert bridge.start(app) is True
    assert len(calls) == 2


def test_recovery_never_admits_an_automatic_replacement(app, recovery, monkeypatch):
    bridge, cloud, _ = recovery
    add_run(app, 'error_pod_kept')
    bridge.start(app)
    monkeypatch.setattr(cloud, '_is_retryable_pod_failure',
                        lambda *_: pytest.fail('Recovery must stop before retry admission'))
    with app.app_context():
        assert cloud._maybe_auto_retry(SimpleNamespace(status='error', vast_instance_id='700'),
                                       'connection refused') is None
        with pytest.raises(RuntimeError, match='before renting another pod'):
            cloud._provision(SimpleNamespace())


def test_recovery_monitor_cannot_provision_a_missing_pod(app, recovery, monkeypatch):
    bridge, cloud, _ = recovery
    run_id = add_run(app, 'preparing', instance=None)
    bridge.start(app)
    monkeypatch.setattr(cloud, '_prepare_staging',
                        lambda *_: pytest.fail('Recovery must stop before preparing a new rental'))
    monkeypatch.setattr(cloud, '_provision',
                        lambda *_: pytest.fail('Recovery must never provision a pod'))
    cloud._monitor(app, run_id)
    from app.extensions import db
    from app.models import CloudTrainingRun
    with app.app_context():
        row = db.session.get(CloudTrainingRun, run_id)
        assert row.status == 'error'
        assert row.vast_instance_id is None


def test_real_boot_recovery_resumes_existing_pod_without_pending_rentals(app, monkeypatch):
    from app.services import cloud_training as cloud
    from app.services import legacy_cloud_recovery as bridge

    run_id = add_run(app, 'training')
    resumed = []
    monkeypatch.setenv('VAST_API_KEY', 'test-only-key')
    monkeypatch.setattr(cloud, 'start_supervisor', lambda _host: None)
    monkeypatch.setattr(cloud, 'reconcile_orphans', lambda _host: 0)
    monkeypatch.setattr(cloud, '_start_monitor_for_app',
                        lambda _host, row_id: resumed.append(row_id))
    monkeypatch.setattr(cloud, '_recover_pending_auto_retries',
                        lambda: pytest.fail('Pending retries may rent; do not resume them'))

    class InlineThread:
        def __init__(self, *, target, args, **kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr(bridge, 'threading', SimpleNamespace(Thread=InlineThread))
    assert bridge.start(app) is True
    assert resumed == [run_id]
