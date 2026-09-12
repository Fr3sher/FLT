"""Projection guard checks and an explicit activation blocker inherited from main."""
import json
from pathlib import Path
import socket
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('label', ['lds-1\n', 'lds-1x', 'lds-١٢', 'lds-１２', 'lds-quantize-1', 'prefix-lds-1', '', None])
def test_training_labels_require_the_whole_ascii_name(app, label):
    from lds_cloud_training import cloud_training as ct
    assert not ct._is_training_label(label)
    assert ct._is_training_label('lds-123')


def test_public_orphan_sweep_preserves_unrecorded_pods(app, monkeypatch):
    """A training-shaped label alone grants no right to delete the pod."""
    from lds_cloud_training import cloud_training as ct
    monkeypatch.setenv('VAST_API_KEY', 'fixture-account-key')
    destroyed = []
    monkeypatch.setattr(ct.vast_client, 'list_instances', lambda: [
        {'instance_id': 'other-installation-pod', 'label': 'lds-123'},
        {'instance_id': 'other-product-pod', 'label': 'lds-quantize-123'},
        {'instance_id': 'newline-pod', 'label': 'lds-123\n'},
        {'instance_id': 'unicode-pod', 'label': 'lds-١٢٣'},
    ])
    monkeypatch.setattr(ct.vast_client, 'destroy_instance', lambda instance_id: destroyed.append(instance_id) or True)
    with app.app_context():
        assert ct.CloudTrainingRun.query.count() == 0
    assert ct.reconcile_orphans(app) == 0
    assert destroyed == []


def test_key_changes_apply_to_the_next_request_and_errors_are_scrubbed(app, monkeypatch):
    from lds_cloud_training import vast_client as vc
    calls = []

    class Reply:
        status_code = 200

        def json(self):
            return {'instances': []}

    def request(method, url, **kwargs):
        calls.append(kwargs['headers']['Authorization'])
        return Reply()

    monkeypatch.setattr(vc.requests.Session, 'request', lambda _s, *a, **k: request(*a, **k))
    monkeypatch.setenv('VAST_API_KEY', 'fixture-a')
    vc.list_instances()
    monkeypatch.setenv('VAST_API_KEY', 'fixture-b')
    vc.list_instances()
    assert calls == ['Bearer fixture-a', 'Bearer fixture-b']
    assert 'fixture-b' not in vc._scrub('rejected fixture-b')


def test_video_api_keeps_training_entrypoints_without_rendering_rentals(app):
    from lds_cloud_training import public_api_v1 as api
    assert callable(api.launch_cloud_video_training)
    assert callable(api.continue_cloud_video_run)
    assert callable(api.retry_cloud_video_run)
    assert not hasattr(api, 'live_rent')
    assert not hasattr(api, 'reference_operation')


def test_disable_blocker_never_probes_or_terminates_a_provider(app, monkeypatch):
    from lds_cloud_training import _disable_blockers, cloud_training as ct
    monkeypatch.setattr(ct.vast_client, 'list_instances', lambda: pytest.fail('disable must not probe cloud'))
    monkeypatch.setattr(ct.vast_client, 'destroy_instance', lambda *args: pytest.fail('disable must not delete cloud'))
    with app.app_context():
        assert _disable_blockers('unrelated', ['existing']) == ['existing']
        assert _disable_blockers('cloud_training', []) == []
        run = ct.CloudTrainingRun(dataset_id=1, status='error_pod_kept',
                                  train_params=json.dumps({'training_mode': 'full_transformer'}))
        ct.db.session.add(run)
        ct.db.session.commit()
        assert 'kept cloud training pod' in _disable_blockers('cloud_training', [])[0]


def test_offline_tripwire_blocks_real_socket_connections():
    with pytest.raises(AssertionError, match='Cloud projection tests'):
        socket.create_connection(('127.0.0.1', 443))


def test_registration_exposes_only_the_training_product_and_defers_workers(app):
    from lds_cloud_training import register
    probes, hooks, workers, boots = {}, {}, {}, []
    context = SimpleNamespace(
        register_blueprint=app.register_blueprint,
        register_probe=lambda key, fn: probes.update({key: fn}),
        register_hook=lambda key, fn: hooks.update({key: fn}),
        register_boot_hook=boots.append,
        register_worker=lambda key, fn: workers.update({key: fn}),
    )
    register(context)
    assert set(probes) == {'cloud_training', 'vast'}
    assert set(hooks) == {'plugin.disable_blockers'}
    assert set(workers) == {'cloud-boot-recover'}
    assert len(boots) == 1
    assert probes['cloud_training']() is False
    assert probes['vast']()['ok'] is False
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert '/api/dataset/train/cloud/stop' in routes
    assert '/api/dataset/train/cloud/continue' in routes
    assert not any('/live' in route or '/reference' in route for route in routes)


def test_manifest_has_no_private_preferences_workers_or_new_models():
    from app.plugins.manifest import load_manifest
    import lds_cloud_training
    root = Path(__file__).resolve().parents[1]
    manifest = load_manifest(root)
    data = json.loads((root / 'plugin.json').read_text(encoding='utf-8'))
    package = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    assert manifest.id == 'cloud_training'
    assert data['version'] == package['version'] == lds_cloud_training.__version__
    assert data['models'] == []
    assert data['owns']['install_actions'] == []
    assert data['owns']['probes'] == ['cloud_training', 'vast']
    assert not any(key in data['owns']['help_topics'] for key in (
        'cloud.automatic_retries', 'cloud.max_network_cost_per_gb', 'cloud.live.max_price_per_hour'))
    assert not (root / 'lds_cloud_training' / 'models.py').exists()
    assert not (root / 'lds_cloud_training' / 'resources').exists()
