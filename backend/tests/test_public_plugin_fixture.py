"""The backend harness must exercise real owners and keep empty boots empty."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

from public_plugin_fixture import (
    PRODUCTS, ROOT, install_hf_gate_guard, isolated_plugin_runtime, marked_plugins,
)


def test_collection_bootstrap_does_not_import_products_or_host_models():
    code = '''
import json, sys
from public_plugin_fixture import PRODUCTS, BUNDLED, bootstrap_public_packages
before = set(sys.modules)
bootstrap_public_packages()
print(json.dumps({"imports": sorted(set(sys.modules) - before),
                  "paths": all(str(BUNDLED / pid) in sys.path for pid in PRODUCTS),
                  "models": "app.models" in sys.modules}))
'''
    environment = os.environ.copy()
    environment['PYTHONPATH'] = str(ROOT / 'backend' / 'tests')
    result = subprocess.run([sys.executable, '-X', 'utf8', '-c', code], env=environment,
                            check=True, capture_output=True, text=True, encoding='utf-8')
    assert json.loads(result.stdout) == {'imports': [], 'paths': True, 'models': False}


def test_unmarked_app_keeps_store_empty(app):
    from app.engines import registry
    assert app.extensions['lds_plugins'].records == {}
    assert set(registry.ids()) == {'klein', 'krea'}
    assert app.test_client().get('/api/video-bank').status_code == 404


@pytest.mark.plugins('video', 'canvas')
def test_marker_loads_only_requested_real_owners(app):
    records = app.extensions['lds_plugins'].records
    assert set(records) == set(PRODUCTS)
    assert {pid for pid, record in records.items() if record.state == 'loaded'} == {'video', 'canvas'}
    assert all(record.state == 'disabled' for pid, record in records.items()
               if pid not in {'video', 'canvas'})
    assert app.test_client().get('/api/train/canvas/positions').status_code == 200
    assert app.test_client().get('/api/system/stats').status_code == 404


@pytest.mark.plugins('video')
class TestClosestMarker:
    @pytest.mark.plugins()
    def test_empty_marker_overrides_class_activation(self, app):
        assert app.extensions['lds_plugins'].records == {}


def test_factory_discards_inherited_discovery_and_kill_switch(plugin_app_factory, tmp_path, monkeypatch):
    for key in ('LDS_BUNDLED_DIR', 'LDS_PLUGINS_DIR', 'LDS_EXTENSIONS_DIR'):
        monkeypatch.setenv(key, str(tmp_path / 'foreign'))
    monkeypatch.setenv('LDS_PLUGIN_DISTRIBUTION', 'development')
    monkeypatch.setenv('LDS_PLUGINS', '0')
    app = plugin_app_factory(enabled=('canvas',))
    assert app.extensions['lds_plugins'].records['canvas'].state == 'loaded'
    assert app.extensions['lds_plugins'].dirs['external'] == str(tmp_path / 'no-external-plugins')


def test_second_factory_boot_has_no_previous_engines_or_config(plugin_app_factory):
    from app import config
    from app.engines import registry
    first = plugin_app_factory(enabled=('api_engines',))
    assert first.extensions['lds_plugins'].records['api_engines'].state == 'loaded'
    assert 'chatgpt' in registry.ids()
    config.save_config({'canvas': {'external_loras': [{'filename': 'test-only.safetensors'}]}})
    second = plugin_app_factory()
    assert second.extensions['lds_plugins'].records == {}
    assert set(registry.ids()) == {'klein', 'krea'}
    assert config.get('canvas.external_loras') == []


def test_second_factory_boot_has_no_previous_product_defaults(plugin_app_factory, monkeypatch):
    from app import config
    import lds_canvas

    real_register = lds_canvas.register

    def register(ctx):
        real_register(ctx)
        ctx.register_config_defaults({'fixture_setting': 'first boot'})

    monkeypatch.setattr(lds_canvas, 'register', register)
    plugin_app_factory(enabled=('canvas',))
    assert config.get('plugins.canvas.fixture_setting') == 'first boot'
    plugin_app_factory()
    assert config.get('plugins.canvas.fixture_setting') is None


def test_factory_reports_loader_failure_instead_of_serving_a_partial_app(plugin_app_factory, monkeypatch):
    import lds_canvas
    monkeypatch.setattr(lds_canvas, 'register', lambda _ctx: (_ for _ in ()).throw(ValueError('fixture failure')))
    with pytest.raises(AssertionError, match='canvas.*fixture failure'):
        plugin_app_factory(enabled=('canvas',))


@pytest.mark.parametrize('selection', [('not_a_product',), 'video', (None,)])
def test_factory_rejects_bad_selection_before_boot(plugin_app_factory, selection):
    with pytest.raises(ValueError):
        plugin_app_factory(enabled=selection)


def test_factory_never_starts_production_workers(plugin_app_factory):
    with pytest.raises(ValueError, match='production workers'):
        plugin_app_factory(config_object={'TESTING': False})


def test_marker_rejects_keyword_typo():
    node = SimpleNamespace(get_closest_marker=lambda _name: pytest.mark.plugins(video=True))
    with pytest.raises(ValueError, match='without keyword'):
        marked_plugins(node)


def test_runtime_isolation_resets_without_removing_imported_mappings(plugin_app_factory):
    from app import config, capabilities
    from app.engines import registry as engines
    from app.plugins import registry
    plugin_app_factory(enabled=('video', 'api_engines'))
    from lds_video.models import VideoBank
    old_registry, old_specs, old_defaults = registry.active(), engines._specs, config.DEFAULTS
    old_path = list(sys.path)
    capabilities._cache = {'stale': True}
    capabilities._import_cache['fixture'] = (0, True)
    with isolated_plugin_runtime():
        assert registry.active() is None and engines.ids() == ()
        assert config._cache is None and capabilities._cache is None
        assert capabilities._import_cache == {}
        config.DEFAULTS['plugins']['test-only'] = {}
        sys.path.append('test-only-path')
        assert sys.modules['lds_video.models'].VideoBank is VideoBank
    assert registry.active() is old_registry and engines._specs is old_specs
    assert config.DEFAULTS is old_defaults and 'test-only' not in config.DEFAULTS['plugins']
    assert sys.path == old_path
    assert sys.modules['lds_video.models'].VideoBank is VideoBank


@pytest.mark.plugins('cloud_training')
def test_hf_guard_covers_both_real_cloud_implementations(app, monkeypatch):
    from app.services import cloud_training as historical
    from lds_cloud_training import cloud_training as product
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open',
                        lambda *a, **k: pytest.fail('The HF gate reached real transport'))
    for module in (historical, product):
        assert module._assert_official_base_reachable('fixture/model', 'fake-token') is None


@pytest.mark.hf_gate
@pytest.mark.plugins('cloud_training')
def test_hf_gate_opt_in_keeps_refusal_logic_for_both_owners(app, monkeypatch):
    from app.services import cloud_training as historical
    from lds_cloud_training import cloud_training as product
    calls = []

    def refused(request, **kwargs):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 403, 'fixture refusal', None, None)

    monkeypatch.setattr(urllib.request, 'urlopen', refused)
    for module in (historical, product):
        with pytest.raises(ValueError, match='Hugging Face refuses access'):
            module._assert_official_base_reachable('fixture/model', 'fake-token')
    assert len(calls) == 2


@pytest.mark.hf_gate
def test_hf_guard_delegates_other_transports_and_handles_late_imports(monkeypatch):
    calls = []
    sentinel = object()
    monkeypatch.setattr(urllib.request, 'urlopen',
                        lambda request, **kwargs: calls.append(request) or sentinel)
    install_hf_gate_guard(monkeypatch)
    assert urllib.request.urlopen('https://example.invalid/api/models/fixture/tree/main') is sentinel
    assert urllib.request.urlopen('https://huggingface.co/api/models/fixture') is sentinel
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(urllib.request.Request('https://huggingface.co/api/models/fixture/tree/main'))
    assert len(calls) == 2


def test_first_boot_retains_existing_tmp_path_contract(app, tmp_path):
    from app import config
    assert config.data_dir() == tmp_path / 'data'
    assert config.ENV_PATH == tmp_path / '.env'
    assert Path(app.instance_path).is_absolute()
