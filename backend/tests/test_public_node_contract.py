"""Pure authoring imports and neutral API 1.20 registration; no production factory."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile

import pytest

from tests.test_plugin_registration import write_plugin  # noqa: F401 - public fixture


@pytest.fixture(autouse=True)
def no_external_runtime(monkeypatch):
    def refuse(*_args, **_kwargs):
        pytest.fail('Node qualification must not contact an external runtime or start workers.')
    monkeypatch.setattr('socket.socket.connect', refuse)
    monkeypatch.setattr('socket.socket.connect_ex', refuse)
    monkeypatch.setattr('socket.create_connection', refuse)
    monkeypatch.setattr('requests.sessions.Session.request', refuse)
    monkeypatch.setattr('threading.Thread.start', refuse)


def make_app(tmp_path, monkeypatch):
    """Load one fixture package using public infrastructure, never create_app."""
    from flask import Flask
    from flask_wtf.csrf import CSRFProtect
    from app import config as cfg
    from app.engines import registry as engines
    from app.plugins import registry
    from app.plugins.loader import load_plugins

    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / '.env'))
    monkeypatch.setenv('LDS_PLUGIN_DISTRIBUTION', 'store')
    monkeypatch.setenv('LDS_PLUGINS_DIR', str(tmp_path / 'data' / 'plugins'))
    monkeypatch.setenv('LDS_EXTENSIONS', '0')
    monkeypatch.delenv('LDS_PLUGINS', raising=False)
    monkeypatch.setattr(cfg, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.setattr(cfg, 'DEFAULTS', deepcopy(cfg.DEFAULTS))
    monkeypatch.setattr(cfg, '_cache', None)
    monkeypatch.setattr(registry, '_ACTIVE', None)
    monkeypatch.setattr(engines, '_specs', {})
    monkeypatch.setattr(sys, 'path', list(sys.path))
    for name in list(sys.modules):
        if name.startswith('lds_example_nodes_v120'):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr('subprocess.Popen', lambda *_a, **_k: pytest.fail('Unexpected process'))
    app = Flask(__name__)
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SECRET_KEY='test-only')
    csrf = CSRFProtect(app)
    with app.app_context():
        load_plugins(app, csrf)
    return app


def test_prepare_failure_is_propagated_by_the_registered_action(tmp_path, monkeypatch):
    from tests.test_plugin_node_packs import _node_app
    from app.services import comfyui_node_install as engine
    monkeypatch.setattr(engine, 'plan', lambda *a, **kw: {'plan_id': 'fixture-plan'})
    def fail(*args, **kwargs):
        raise engine.NodeInstallError('Dependency conflict; no node prepared.')
    monkeypatch.setattr(engine, 'prepare', fail)
    app = _node_app(tmp_path, monkeypatch)
    spec = app.extensions['lds_plugins'].install_actions['sample_nodes']
    logs = []
    with pytest.raises(engine.NodeInstallError, match='no node prepared'):
        spec['run'](log=logs.append)
    assert logs == []


@pytest.mark.parametrize('kind', ['recipe', 'manifest', 'archive'])
def test_authoring_validation_does_not_import_runtime_configuration(tmp_path, kind):
    from tests.test_plugin_node_packs import with_wheel
    data, body = with_wheel()
    metadata = tmp_path / 'manifest.json'
    metadata.write_text(json.dumps(data), encoding='utf-8')
    package = tmp_path / 'fixture.zip'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('plugin.json', json.dumps(data))
        archive.writestr(data['python_package'] + '/__init__.py', 'raise RuntimeError("must never import")')
        archive.writestr('assets/wheels/' + data['node_packs'][0]['installation']['wheels'][0]['filename'], body)
    script = textwrap.dedent('''
        import importlib.abc, json, pathlib, sys, types
        namespace = types.ModuleType('app')
        namespace.__path__ = [str(pathlib.Path(sys.argv[1]) / 'app')]
        sys.modules['app'] = namespace
        class RefuseRuntime(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, *args):
                blocked = ('app.config', 'app.services', 'app.setup_installer', 'app.plugins.environment')
                if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
                    raise AssertionError('Authoring imported runtime: ' + fullname)
        sys.meta_path.insert(0, RefuseRuntime())
        data = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'))
        kind = sys.argv[4]
        if kind == 'recipe':
            from app.plugins.node_packs import recipe
            from app.plugins.node_recipe import _validate
            _validate(recipe(data['node_packs'][0]), data['id'])
        elif kind == 'manifest':
            from app.plugins.manifest import parse_manifest
            parse_manifest(data, pathlib.Path('.'))
        else:
            from app.plugins.install import inspect_plugin_zip
            inspect_plugin_zip(sys.argv[3])
        print('pure authoring passed')
    ''')
    from app.plugins.environment import subprocess_env
    output, errors = tmp_path / 'stdout.txt', tmp_path / 'stderr.txt'
    # Windows PIPE communication starts reader threads; files keep the worker
    # prohibition intact while this bounded authoring subprocess runs.
    with output.open('w', encoding='utf-8') as stdout, errors.open('w', encoding='utf-8') as stderr:
        result = subprocess.run([sys.executable, '-I', '-c', script,
                                 str(Path(__file__).resolve().parents[1]), str(metadata), str(package), kind],
                                stdout=stdout, stderr=stderr, timeout=30, env=subprocess_env())
    assert result.returncode == 0, errors.read_text(encoding='utf-8')
    assert output.read_text(encoding='utf-8').strip() == 'pure authoring passed'
