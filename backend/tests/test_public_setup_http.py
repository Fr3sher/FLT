"""Real installer HTTP admission with neutral plugins and no worker/network I/O."""
from types import SimpleNamespace

import pytest

from app import capabilities, config as cfg, setup_installer as installer
from app.plugins import storage
from app.plugins.loader import load_plugins
from tests.test_public_plugin_foundation import host, write  # noqa: F401


@pytest.fixture
def setup_host(host, monkeypatch):
    app, csrf, root = host
    write(host, owns={'install_actions': ['sample_tools', 'sample_model'],
                      'install_groups': ['sample_group']}, code='''
        def register(ctx):
            ctx.register_install_action('sample_tools', label='Sample tools', run=lambda log: 0)
            ctx.register_install_action('sample_model', label='Sample model', run=lambda log: 0)
            ctx.register_install_group('sample_group', ['sample_tools', 'sample_model'],
                                       missing_key='sample_missing')
    ''')
    write(host, 'sample.other', owns={'install_actions': ['other_tools']}, code='''
        def register(ctx):
            ctx.register_install_action('other_tools', label='Other tools', run=lambda log: 0)
    ''')
    registry = load_plugins(app, csrf)
    assert all(record.state == 'loaded' for record in registry.records.values())
    from app.plugins.routes import bp as plugins_bp
    from app.routes.setup import bp as setup_bp
    app.register_blueprint(plugins_bp)
    app.register_blueprint(setup_bp)
    monkeypatch.setattr(installer, '_runs', {})
    calls = []
    monkeypatch.setattr(installer, 'start', lambda action: calls.append(action) or {
        'state': 'running', 'log': [], 'returncode': None})
    monkeypatch.setattr(capabilities, 'probe', lambda **kw: {'comfyui': {
        'dir_valid': True, 'sample_missing': ['sample_tools', 'sample_model']}})
    return SimpleNamespace(app=app, client=app.test_client(), registry=registry,
                           calls=calls, root=root)


def test_selected_batch_returns_its_exact_server_plan(setup_host):
    response = setup_host.client.post('/api/plugins/sample.feature/preparation',
                                     json={'actions': ['sample_model', 'sample_tools']})
    assert response.status_code == 200, response.json
    assert response.json['plan'] == setup_host.calls == ['sample_model', 'sample_tools']
    assert set(response.json['statuses']) == set(setup_host.calls)


@pytest.mark.parametrize('body', [
    {}, [], None, {'actions': []}, {'actions': 'sample_tools'},
    {'actions': ['sample_tools', 'sample_tools']}, {'actions': ['sample_tools', {}]},
    {'actions': ['sample_tools', 'other_tools']}, {'actions': ['sample_tools', 'klein_model']},
    {'actions': ['sample_tools'], 'command': 'ignored'},
])
def test_invalid_or_foreign_selection_never_admits_a_partial_batch(setup_host, body):
    response = setup_host.client.post('/api/plugins/sample.feature/preparation', json=body)
    assert response.status_code == 400
    assert setup_host.calls == []


@pytest.mark.parametrize('change', ['pending', 'off', 'unloaded', 'different_registry'])
def test_only_the_installed_loaded_and_current_owner_can_prepare(setup_host, monkeypatch, change):
    if change == 'pending':
        monkeypatch.setattr(storage, 'pending', lambda root: ({'sample.feature': {}}, []))
    elif change == 'off':
        cfg.save_config({'plugins': {'enabled': {'sample.feature': False}}})
    elif change == 'unloaded':
        setup_host.registry.records['sample.feature'].state = 'error'
    else:
        monkeypatch.setattr(installer, '_plugin_registry', lambda: None)
    response = setup_host.client.post('/api/plugins/sample.feature/preparation',
                                     json={'actions': ['sample_tools']})
    assert response.status_code == 409
    assert setup_host.calls == []


def test_selected_node_preflight_failure_prevents_all_model_admissions(setup_host):
    def conflict():
        raise ValueError('A dependency conflicts with this ComfyUI.')
    setup_host.registry.install_actions['sample_tools']['node_preflight'] = conflict
    response = setup_host.client.post('/api/plugins/sample.feature/preparation',
                                     json={'actions': ['sample_model', 'sample_tools']})
    assert response.status_code == 400
    assert 'conflicts' in response.json['error']
    assert setup_host.calls == []


def test_group_preflight_failure_is_a_readable_http_error(setup_host):
    def conflict():
        raise ValueError('A dependency conflicts with this ComfyUI.')
    setup_host.registry.install_actions['sample_tools']['node_preflight'] = conflict
    response = setup_host.client.post('/api/setup/install-group/sample_group')
    assert response.status_code == 400
    assert 'conflicts' in response.json['error']
    assert setup_host.calls == []


@pytest.mark.parametrize('path', [
    '/api/plugins/sample.feature/preparation',
    '/api/setup/install/sample_tools',
    '/api/setup/install/sample_tools/cancel',
    '/api/setup/install-group/sample_group',
])
def test_plugin_administration_cannot_be_bypassed_through_setup(setup_host, path):
    response = setup_host.client.post(path, json={'actions': ['sample_tools']},
                                     environ_overrides={'REMOTE_ADDR': '192.0.2.2'})
    assert response.status_code == 403, response.json
    assert response.json['code'] == 'plugin_admin_required'
    assert setup_host.calls == []


def test_core_batch_rejects_a_plugin_selection_before_probing_or_starting(setup_host, monkeypatch):
    monkeypatch.setattr(capabilities, 'probe', lambda **kw: pytest.fail('Must refuse before probing'))
    response = setup_host.client.post('/api/setup/install-all', json={'actions': ['sample_tools']})
    assert response.status_code == 400
    assert setup_host.calls == []


def test_registered_override_cannot_enter_the_unattended_core_batch(setup_host, monkeypatch):
    setup_host.registry.install_actions['masks'] = {
        **setup_host.registry.install_actions['sample_tools'], 'label': 'Owner mask override'}
    monkeypatch.setattr(installer, '_INSTALL_ALL_ORDER', ('masks',))
    assert installer.start_all({'masks': False})['plan'] == []
    assert setup_host.calls == []


def test_core_group_cannot_bypass_admin_for_a_plugin_owned_member(setup_host, monkeypatch):
    monkeypatch.setitem(installer._INSTALL_GROUPS, 'sample_core_group', ('sample_tools',))
    response = setup_host.client.post('/api/setup/install-group/sample_core_group',
                                     environ_overrides={'REMOTE_ADDR': '192.0.2.2'})
    assert response.status_code == 403
    assert setup_host.calls == []


def test_local_explicit_plugin_action_and_catalog_remain_available(setup_host):
    response = setup_host.client.post('/api/setup/install/sample_tools')
    assert response.status_code == 200
    assert setup_host.calls == ['sample_tools']
    actions = setup_host.client.get('/api/setup/actions').json['actions']
    assert actions['sample_tools']['plugin'] == 'sample.feature'


def test_inflight_member_is_reused_and_owner_stays_busy(setup_host, monkeypatch):
    installer._runs['sample_tools'] = installer._new_run()
    def start(action):
        if action == 'sample_tools':
            raise installer.AlreadyRunning(action)
        setup_host.calls.append(action)
        return {'state': 'running'}
    monkeypatch.setattr(installer, 'start', start)
    response = setup_host.client.post('/api/plugins/sample.feature/preparation',
                                     json={'actions': ['sample_tools', 'sample_model']})
    assert response.status_code == 200
    assert setup_host.calls == ['sample_model']
    assert installer.plugin_install_busy('sample.feature')
    assert setup_host.client.post('/api/plugins/sample.feature/disable').status_code == 409
    installer._runs['sample_tools']['state'] = 'success'
    assert not installer.plugin_install_busy('sample.feature')
