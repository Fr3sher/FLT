"""Production factory with temporary public data and forbidden external I/O."""
from collections import defaultdict
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from app import config as cfg, create_app
from app.engines import registry as engines
from app.extensions import db
from app.plugins import registry

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = tuple(sorted(path.parent.name for path in (ROOT / 'bundled').glob('*/plugin.json')))


@pytest.fixture
def factory(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('Factory qualification forbids external I/O and real workers')
    for target in ('socket.socket.connect', 'socket.socket.connect_ex', 'socket.create_connection',
                   'threading.Thread.start', 'subprocess.Popen', 'subprocess.run',
                   'requests.sessions.Session.request'):
        monkeypatch.setattr(target, blocked)
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / '.env'))
    monkeypatch.setenv('LDS_EXTENSIONS_DIR', str(tmp_path / 'legacy'))
    monkeypatch.setenv('LDS_PLUGINS_DIR', str(tmp_path / 'external'))
    monkeypatch.setenv('LDS_EXTENSIONS', '0')
    monkeypatch.delenv('LDS_PLUGINS', raising=False)
    monkeypatch.delenv('LDS_BUNDLED_DIR', raising=False)
    monkeypatch.setenv('LDS_PLUGIN_DISTRIBUTION', 'store')
    monkeypatch.setattr(cfg, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.setattr(cfg, 'DEFAULTS', deepcopy(cfg.DEFAULTS))
    monkeypatch.setattr(cfg, '_cache', None)
    monkeypatch.setattr(engines, '_specs', {})
    monkeypatch.setattr(registry, '_ACTIVE', None)
    for key in cfg.SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)
    apps = []
    original_path = list(sys.path)

    def make(enabled=None):
        if enabled is not None:
            monkeypatch.setenv('LDS_BUNDLED_DIR', str(ROOT / 'bundled'))
            (tmp_path / 'config.json').write_text(json.dumps({'plugins': {'enabled': {
                pid: pid in enabled for pid in PRODUCTS}}}), encoding='utf-8')
            cfg._cache = None
        app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
                          'WTF_CSRF_ENABLED': False, 'SECRET_KEY': 'factory-fixture'})
        apps.append(app)
        return app
    yield make
    for app in apps:
        with app.app_context():
            db.session.remove()
            db.drop_all()
    sys.path[:] = original_path


def test_store_factory_starts_with_zero_plugins(factory):
    app = factory()
    assert app.extensions['lds_plugins'].records == {}
    assert app.test_client().get('/api/plugins', follow_redirects=True).status_code == 200
    assert len(db.metadata.tables) == 28


@pytest.mark.parametrize('pid', PRODUCTS)
def test_true_factory_each_product_alone(factory, pid):
    app = factory({pid})
    records = app.extensions['lds_plugins'].records
    assert records[pid].state == 'loaded', records[pid].error
    assert all(r.state == 'disabled' for key, r in records.items() if key != pid)
    assert len(db.metadata.tables) == 28


def test_true_factory_products_have_no_duplicate_url_method(factory):
    app = factory(PRODUCTS)
    assert {pid: r.error for pid, r in app.extensions['lds_plugins'].records.items()
            if r.state != 'loaded'} == {}
    owners = defaultdict(list)
    for rule in app.url_map.iter_rules():
        for method in rule.methods - {'HEAD', 'OPTIONS'}:
            owners[method, rule.rule].append(rule.endpoint)
    assert {str(key): value for key, value in owners.items() if len(value) > 1} == {}


@pytest.mark.parametrize('url', ['/api/system/stats', '/api/video-studio/options',
    '/api/train/canvas/positions', '/api/camera/catalog', '/api/seedvr2/models',
    '/api/settings/chatgpt-oauth/poll', '/api/civitai/status', '/api/cloud/quantize/status',
    '/api/dataset/train/cloud/status', '/api/tools/lora-merge/status',
    '/api/dataset/1/publish-hf/status'])
def test_store_has_no_transferred_product_urls(factory, url):
    app = factory()
    assert app.test_client().get(url).status_code == 404


def test_settings_scopes_hide_fields_and_refuse_cross_owner_writes(factory, monkeypatch):
    app = factory(PRODUCTS)
    monkeypatch.setattr('app.routes.settings._lan_ip', lambda: None)
    monkeypatch.setattr('app.routes.settings._tailscale_ip', lambda: None)
    client = app.test_client()
    core = client.get('/api/settings').json
    assert 'cloud' not in core['config'] and 'canvas' not in core['config_defaults']
    assert 'GEMINI_API_KEY' not in core['secrets']
    api = client.get('/api/settings?plugin=api_engines').json
    assert set(api['config']) <= {'engines', 'plugins'}
    assert set(api['secrets']) == {'GEMINI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY'}
    assert client.put('/api/settings', json={'config': {'cloud': {'max_price_per_hour': 999}}}).status_code == 400
    assert client.put('/api/settings?plugin=api_engines', json={'config': {'server': {'port': 1}}}).status_code == 400
    assert client.put('/api/settings?plugin=api_engines', json={'secrets': {'GEMINI_API_KEY': 'fake-fixture'}}).status_code == 200
    assert client.delete('/api/settings/secret/GEMINI_API_KEY').status_code == 400
    assert client.delete('/api/settings/secret/GEMINI_API_KEY?plugin=api_engines').status_code == 200
    assert not cfg.secret('GEMINI_API_KEY')
    assert client.put('/api/settings', json={'config': {'plugins': {'enabled': {'cloud_training': True}}}}).status_code == 400


def test_off_provider_tests_are_refused_before_callbacks(factory):
    app = factory(set())
    for owner, target in (('cloud_training', 'vast'), ('api_engines', 'openai'),
                          ('cloud_training', 'hf_cloud'), ('civitai_publish', 'civitai')):
        assert app.test_client().post(f'/api/settings/test/{target}?plugin={owner}').status_code == 409


def test_registered_capability_cache_changes_with_owner_state(factory, monkeypatch):
    from app import capabilities
    app = factory({'cloud_training'})
    registry = app.extensions['lds_plugins']
    calls = []
    registry.probes = {'cloud_training': ('cloud_training', lambda: calls.append('probe') or True)}
    monkeypatch.setattr(capabilities, '_cache', None)
    monkeypatch.setattr(capabilities, '_probe_uncached', lambda: {'engines': {'klein': False}, 'training_visible': False})
    with app.app_context():
        assert capabilities.probe()['cloud_training'] is True
        assert capabilities.probe()['cloud_training'] is True
        assert calls == ['probe']
        cfg.save_config({'plugins': {'enabled': {'cloud_training': False}}})
        assert 'cloud_training' not in capabilities.probe()
        assert calls == ['probe']


def test_plugin_http_callbacks_remain_behind_auth_csrf_and_pending_disable(factory):
    app = factory({'canvas'})
    client = app.test_client()
    cfg.save_config({'server': {'require_token': True, 'access_token': 'fake-fixture-token'}})
    assert client.get('/api/train/canvas/positions', environ_overrides={'REMOTE_ADDR': '192.0.2.8'}).status_code in (401, 403)
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.put('/api/train/canvas/external-loras', json={'loras': []}).status_code == 400
    app.config['WTF_CSRF_ENABLED'] = False
    cfg.save_config({'plugins': {'enabled': {'canvas': False}}})
    assert client.get('/api/train/canvas/positions').status_code == 409


def test_boot_workers_have_one_owner_without_starting_real_workers(factory, monkeypatch):
    import app as host
    from app.job_queue import queue_manager
    app = factory({'cloud_training'})
    calls = []
    monkeypatch.setattr(queue_manager, 'start', lambda: calls.append('queue'))
    monkeypatch.setattr('app.services.lora_training.start_training_scheduler', lambda _app: calls.append('local'))
    monkeypatch.setattr('app.plugins.loader.run_boot_hooks', lambda _app: calls.append('plugins'))
    host._start_workers(app)
    assert calls == ['queue', 'local', 'plugins']
    assert [name for _, name, _ in app.extensions['lds_plugins'].workers].count('cloud-boot-recover') == 1
