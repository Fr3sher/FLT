"""Actual API 1.15 context/registry integration; no package installation."""
from pathlib import Path
from types import SimpleNamespace
import copy
import json
import sys

from flask import Flask
import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'bundled/model_tools')]
from app import config, setup_installer
from app.plugins import environment
from app.plugins.api import PluginContext
from app.plugins.manifest import load_manifest
from app.plugins.package_contract import compatibility_issues
from app.plugins.registry import PluginRecord, PluginRegistry
from lds_model_tools import register, runtime, fp8_quantize


@pytest.fixture
def product(tmp_path, monkeypatch):
    app = Flask(__name__)
    directory = ROOT / 'bundled/model_tools'
    manifest = load_manifest(directory)
    assert manifest.contract['schema_version'] == 2
    assert manifest.requirements == 'requirements-workers.txt'
    registry = PluginRegistry()
    record = PluginRecord(manifest.id, manifest, str(directory), True, state='loaded')
    registry.records[record.id] = record
    assert registry.claim_manifest(manifest) is None
    app.extensions['lds_plugins'] = registry
    monkeypatch.setattr(config, 'data_dir', lambda: tmp_path)
    monkeypatch.setattr(config, 'get', lambda *_: None)
    monkeypatch.setattr(setup_installer, 'plugin_install_busy', lambda _: False)
    ctx = PluginContext(app, registry, manifest, tmp_path / 'plugin-data/model_tools')
    register(ctx)
    return app, ctx, record


def test_actual_context_exposes_missing_engine_and_owned_action_without_installing(product, tmp_path):
    app, ctx, record = product
    result = app.test_client().get('/api/tools/model-runtime').get_json()
    assert result['ok'] and not result['ready']
    assert result['python'] is None
    assert result['environment']['can_install']
    assert result['environment']['action'] == 'plugin_environment:model_tools'
    assert app.extensions['lds_plugins'].probes['model_tools'][0] == 'model_tools'
    assert not list(tmp_path.iterdir()), 'reading runtime state must not create an environment'
    record.enabled = False
    assert not ctx.plugin_environment()['can_install']


def test_product_requires_api_1_15_but_allows_a_python_3_14_host(product):
    _, _, record = product
    host = {'lds_version': '2026.9.9', 'python_version': '3.14.2',
            'system': 'windows', 'machine': 'AMD64', 'dependencies': {}}
    assert compatibility_issues(record.manifest.contract, api_version='1.15', **host) == []
    issues = compatibility_issues(record.manifest.contract, api_version='1.14', **host)
    assert len(issues) == 1 and issues[0]['field'] == 'compatibility.api'


def test_actual_context_lease_spans_probe_and_worker_and_releases_after_failure(product, monkeypatch):
    app, ctx, _ = product
    python = 'C:/t/isolated-model-tools/python.exe'
    monkeypatch.setattr(environment, 'summary', lambda *_: {
        'ready': True, 'can_install': True, 'action': 'plugin_environment:model_tools', 'reason': ''})
    monkeypatch.setattr(environment, 'interpreter', lambda _: python)
    monkeypatch.setattr(environment, '_verify_interpreter', lambda *_: None)

    def probe(argv, **_kwargs):
        assert environment.running('model_tools')
        assert not ctx.plugin_environment()['can_install']
        return SimpleNamespace(returncode=0, stdout=json.dumps({'torch': True, 'torch_version': 'test'}))

    def broken_popen(*_args, **_kwargs):
        assert environment.running('model_tools')
        assert not ctx.plugin_environment()['can_install']
        raise OSError('test worker startup failure')

    monkeypatch.setattr(runtime.subprocess, 'run', probe)
    monkeypatch.setattr(fp8_quantize.subprocess, 'Popen', broken_popen)
    with app.app_context():
        assert runtime.status()['ready']
        assert not environment.running('model_tools')
        with pytest.raises(fp8_quantize.QuantizeError, match='could not be started'):
            fp8_quantize.run_worker(python, 'source', 'destination')
        assert not environment.running('model_tools')
        assert ctx.plugin_environment()['can_install']


@pytest.mark.parametrize('condition', ['ready', 'off', 'pending', 'replaced', 'removed', 'installing'])
def test_override_uses_real_context_without_a_managed_environment_and_rechecks_cached_probe(product, monkeypatch, condition):
    app, ctx, record = product
    python = 'C:/t/explicit-worker/python.exe'
    monkeypatch.setattr(runtime, 'explicit_python', lambda: python)
    monkeypatch.setattr(environment, 'interpreter', lambda *_: pytest.fail('Override requested a managed interpreter.'))
    calls = []
    def run(argv, **kwargs):
        assert environment.running(record.id)
        assert argv[:2] == [python, '-I']
        assert kwargs['env']['PYTHONNOUSERSITE'] == '1'
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'torch': True, 'torch_version': 'test-cpu'}))
    monkeypatch.setattr(runtime.subprocess, 'run', run)
    with app.app_context():
        assert runtime.interpreter()['ready']
        assert not environment.running(record.id)
        if condition == 'off':
            record.enabled = False
        elif condition == 'pending':
            record.pending_restart = True
        elif condition == 'replaced':
            record.manifest = copy.copy(record.manifest)
        elif condition == 'removed':
            del app.extensions['lds_plugins'].records[record.id]
        elif condition == 'installing':
            monkeypatch.setattr(setup_installer, 'plugin_install_busy', lambda _: True)
        assert runtime.interpreter()['ready'] is (condition == 'ready')
        assert len(calls) == 1, 'The second call checks admission without a second Torch subprocess.'
        if condition == 'ready':
            with runtime.use_worker(python):
                assert environment.running(record.id)
        else:
            with pytest.raises(ValueError):
                with runtime.use_worker(python):
                    pytest.fail('Unavailable override started work.')
        assert not environment.running(record.id)


@pytest.mark.parametrize('serializes', [True, False])
def test_real_probe_requires_tensor_serialization_not_only_torch_arithmetic(product, monkeypatch, serializes):
    app, _, _ = product
    monkeypatch.setattr(runtime, 'explicit_python', lambda: sys.executable)
    original_run = runtime.subprocess.run
    prefix = (
        'import sys\nfrom types import SimpleNamespace\n'
        'class Value:\n'
        ' def __add__(self, value): return self\n'
        ' def item(self): return 2\n'
        ' def numpy(self):\n'
        + ('  return SimpleNamespace(tobytes=lambda: b"1234")\n' if serializes else
           '  raise RuntimeError("NumPy is unavailable")\n')
        + 'sys.modules["torch"]=SimpleNamespace(ones=lambda *a,**k: Value(), '
        '__version__="synthetic-cpu",version=SimpleNamespace(cuda=None))\n')
    def actual_run(argv, **kwargs):
        assert environment.running('model_tools')
        return original_run([*argv[:-1], prefix + argv[-1]], **kwargs)
    monkeypatch.setattr(runtime.subprocess, 'run', actual_run)
    with app.app_context():
        assert runtime.interpreter()['ready'] is serializes
    assert not environment.running('model_tools')
    requirements = (ROOT / 'bundled/model_tools/requirements-workers.txt').read_text(encoding='utf-8')
    assert 'numpy>=1.26,<3' in requirements.splitlines()
