"""Failed plugin entry points leave no active in-memory contributions at boot."""
from copy import deepcopy
import json
import sys
import textwrap

from flask import Blueprint, Flask
from flask_wtf.csrf import CSRFProtect
import pytest

from app import config as cfg
from app.engines import registry as engines
from app.plugins import registry as plugin_registry
from app.plugins.api import ConfigView
from app.plugins.loader import load_plugins



def write_plugin(root, pid, *, package=None, code=None, **over):
    """Only neutral temporary products; no application factory or product fixtures."""
    directory = root / pid
    directory.mkdir(parents=True)
    manifest = {'id': pid, 'name': pid, 'version': '1.0.0', 'api': 1,
                'requires': [], 'owns': {}, **over}
    if package:
        manifest['python_package'] = package
    (directory / 'plugin.json').write_text(json.dumps(manifest), encoding='utf-8')
    if package:
        folder = directory / package
        folder.mkdir()
        (folder / '__init__.py').write_text(textwrap.dedent(code), encoding='utf-8')
    return directory


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / '.env'))
    monkeypatch.setenv('LDS_PLUGIN_DISTRIBUTION', 'store')
    monkeypatch.setenv('LDS_PLUGINS_DIR', str(tmp_path / 'plugins'))
    monkeypatch.setenv('LDS_EXTENSIONS_DIR', str(tmp_path / 'legacy'))
    monkeypatch.setenv('LDS_EXTENSIONS', '0')
    monkeypatch.delenv('LDS_PLUGINS', raising=False)
    monkeypatch.setattr(cfg, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.setattr(cfg, 'DEFAULTS', deepcopy(cfg.DEFAULTS))
    monkeypatch.setattr(cfg, '_cache', None)
    monkeypatch.setattr(engines, '_specs', {})
    monkeypatch.setattr(plugin_registry, '_ACTIVE', None)
    monkeypatch.setattr('requests.sessions.Session.request',
                        lambda *_a, **_k: pytest.fail('Unexpected network request'))
    original_path = list(sys.path)
    app = Flask(__name__)
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SECRET_KEY='test-only')
    csrf = CSRFProtect(app)
    yield app, csrf, tmp_path
    sys.path[:] = original_path
    for name in list(sys.modules):
        if name.startswith('lds_registration_'):
            sys.modules.pop(name, None)


GOOD = '''
    from flask import Blueprint
    def register(ctx):
        bp = Blueprint(ctx.id.replace('.', '_'), __name__)
        bp.add_url_rule('/ping', 'ping', lambda: {'ready': ctx.id})
        ctx.register_blueprint(bp)
        ctx.register_config_defaults({'nested': {'kept': True}})
        ctx.register_engine(id=ctx.id + '_engine', label=ctx.id, kind='local', order=1)
        ctx.register_probe(ctx.id + '_ready', lambda: True)
'''


PARTIAL = '''
    from flask import Blueprint
    from app import config as cfg
    def register(ctx):
        bp = Blueprint('partial', __name__)
        bp.add_url_rule('/ping', 'ping', lambda: {'partial': True})
        ctx.register_blueprint(bp)
        ctx.app.extensions['csrf'].exempt(bp)
        ctx.app.config['PARTIAL_CONFIG'] = {'nested': [True]}
        ctx.app.extensions['partial_extension'] = True
        ctx.app.extensions['existing_values']['nested'].append('partial')
        ctx.app.jinja_env.filters['partial_filter'] = str
        ctx.app.jinja_env.globals['partial_global'] = True
        @ctx.app.cli.command('partial-command')
        def command():
            pass
        ctx.app.before_request(lambda: None)
        ctx.app.register_error_handler(404, lambda _: ({'partial': True}, 200))
        ctx.register_config_defaults({'nested': {'attempt': True}, 'attempt': True})
        ctx.register_engine(id='partial_engine', label='Partial', kind='local', order=2)
        ctx.register_probe('partial_ready', lambda: True)
        ctx.register_boot_hook(lambda app: None)
        ctx.register_worker('partial', lambda app: None)
        ctx.register_hook('caption.stamp', lambda value, image: value)
        ctx.register_request_limit('partial.ping', 123)
        # Exercise a cache populated with the failed defaults and engine catalog.
        cfg.load_config()
        raise RuntimeError('Registration failed after contributions')
'''


@pytest.mark.parametrize('preexisting', [False, True])
def test_modern_failure_restores_scopes_defaults_and_engines_before_next_plugin(host, preexisting):
    app, csrf, root = host
    app.extensions['existing_values'] = {'nested': ['kept']}
    existing_bp = Blueprint('existing', __name__)
    existing_bp.add_url_rule('/existing', 'ping', lambda: {'kept': True})
    app.register_blueprint(existing_bp)
    csrf.exempt(existing_bp)
    old_hooks = list(app.before_request_funcs.get(None, []))
    defaults_identity, engine_registry_identity = cfg.DEFAULTS, engines._specs
    previous = None
    if preexisting:
        cfg.register_plugin_defaults('sample.beta', {'nested': {'kept': ['original']}})
        previous = engines.register(engines.EngineSpec(
            id='partial_engine', label='Previous', kind='local', order=2,
            plugin='sample.beta', generate=lambda: 'original', extra={'kept': True}))
    cfg.load_config()
    write_plugin(root / 'plugins', 'sample.alpha', package='lds_registration_alpha', code=GOOD,
                 owns={'engines': ['sample.alpha_engine'], 'probes': ['sample.alpha_ready']})
    write_plugin(root / 'plugins', 'sample.beta', package='lds_registration_beta', code=PARTIAL,
                 owns={'engines': ['partial_engine'], 'probes': ['partial_ready']})
    # Check rollback before the loader's final force=True cache refresh can mask a leak.
    observer = textwrap.dedent('''
        original_register = register
        def register(ctx):
            from app import config as cfg
            from app.engines import registry as engines
            from app.plugins.api import ConfigView
            assert ConfigView('sample.beta').own('attempt') is None
            assert 'attempt' not in cfg.DEFAULTS['plugins'].get('sample.beta', {})
            spec = engines.get('partial_engine')
            assert spec is None or spec.label == 'Previous'
            assert not ctx._registry.boot_hooks and not ctx._registry.workers
            assert not ctx._registry.request_limits and not ctx._registry.hooks
            ctx.app.extensions['alpha_engine'] = engines.get('sample.alpha_engine')
            original_register(ctx)
    ''')
    write_plugin(root / 'plugins', 'sample.gamma', package='lds_registration_gamma',
                 code=textwrap.dedent(GOOD) + observer,
                 owns={'engines': ['sample.gamma_engine'], 'probes': ['sample.gamma_ready']})

    loaded = load_plugins(app, csrf)

    assert loaded.records['sample.beta'].state == 'error'
    assert 'Registration failed after contributions' in loaded.records['sample.beta'].error
    client = app.test_client()
    assert client.get('/api/plugins/sample.beta/ping').status_code == 404
    assert client.get('/existing').get_json() == {'kept': True}
    for pid in ('sample.alpha', 'sample.gamma'):
        assert loaded.records[pid].state == 'loaded', loaded.records[pid].error
        assert client.get(f'/api/plugins/{pid}/ping').get_json() == {'ready': pid}
        assert ConfigView(pid).own('nested.kept') is True
        assert loaded.probes[pid + '_ready'][1]() is True
    assert engines.get('sample.alpha_engine') is app.extensions['alpha_engine']
    assert engines.get('partial_engine') is previous
    assert cfg.DEFAULTS is defaults_identity and engines._specs is engine_registry_identity
    assert ConfigView('sample.beta').own('attempt') is None
    assert ConfigView('sample.beta').own('nested.kept') == (['original'] if preexisting else None)
    if not preexisting:
        assert 'sample.beta' not in cfg.DEFAULTS['plugins']
    assert 'partial_ready' not in loaded.probes
    assert loaded.boot_hooks == [] and loaded.workers == []
    assert loaded.hooks == {} and loaded.request_limits == {}
    assert 'partial' not in app.blueprints
    assert 'PARTIAL_CONFIG' not in app.config
    assert 'partial_extension' not in app.extensions
    assert app.extensions['existing_values'] == {'nested': ['kept']}
    assert 'partial_filter' not in app.jinja_env.filters
    assert 'partial_global' not in app.jinja_env.globals
    assert 'partial-command' not in app.cli.commands
    assert app.before_request_funcs[None][:len(old_hooks)] == old_hooks
    assert not any(bp.name == 'partial' for bp in csrf._exempt_blueprints)
    assert existing_bp in csrf._exempt_blueprints


def test_modern_import_failure_rolls_back_contributions(host):
    app, csrf, root = host
    write_plugin(root / 'plugins', 'sample.import_error', package='lds_registration_import_error', code='''
        from flask import current_app
        from app import config as cfg
        from app.engines import registry as engines
        from app.plugins.registry import active
        current_app.add_url_rule('/api/import-partial', 'import_partial', lambda: {'partial': True})
        cfg.register_plugin_defaults('sample.import_error', {'partial': True})
        engines.register(engines.EngineSpec(id='import_partial', label='Partial', kind='local', order=1))
        active().add_probe('sample.import_error', 'import_partial', lambda: True)
        cfg.load_config()
        raise RuntimeError('Package import failed after contributions')
    ''')
    with app.app_context():
        loaded = load_plugins(app, csrf)
    assert loaded.records['sample.import_error'].state == 'error'
    assert 'Package import failed after contributions' in loaded.records['sample.import_error'].error
    assert app.test_client().get('/api/import-partial').status_code == 404
    assert 'sample.import_error' not in cfg.DEFAULTS['plugins']
    assert ConfigView('sample.import_error').own('partial') is None
    assert engines.get('import_partial') is None
    assert 'import_partial' not in loaded.probes
    assert loaded.owner_of('probes', 'import_partial') is None


def test_legacy_failure_restores_defaults_and_engine_replacements(host, monkeypatch):
    app, csrf, root = host
    monkeypatch.setenv('LDS_EXTENSIONS', '1')
    cfg.register_plugin_defaults('legacy.lds_registration_legacy', {'kept': True})
    previous = engines.register(engines.EngineSpec(
        id='legacy_engine', label='Previous', kind='local', order=1))
    directory = root / 'legacy' / 'lds_registration_legacy'
    directory.mkdir(parents=True)
    (directory / '__init__.py').write_text(textwrap.dedent('''
        from app import config as cfg
        from app.engines import registry as engines
        def register(app, csrf):
            app.add_url_rule('/api/legacy-partial', 'legacy_partial', lambda: {'partial': True})
            cfg.register_plugin_defaults('legacy.lds_registration_legacy', {'attempt': True})
            engines.register(engines.EngineSpec(
                id='legacy_engine', label='Partial', kind='local', order=1), replace=True)
            cfg.load_config()
            raise RuntimeError('Legacy registration failed after contributions')
    '''), encoding='utf-8')
    loaded = load_plugins(app, csrf)
    record = loaded.records['legacy.lds_registration_legacy']
    assert record.state == 'error'
    assert 'Legacy registration failed after contributions' in record.error
    assert app.test_client().get('/api/legacy-partial').status_code == 404
    assert engines.get('legacy_engine') is previous
    assert cfg.DEFAULTS['plugins']['legacy.lds_registration_legacy'] == {'kept': True}
    assert ConfigView('legacy.lds_registration_legacy').own('attempt') is None
    assert app.config['EXTENSIONS_MANIFEST'] == []
