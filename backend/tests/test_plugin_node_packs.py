"""Declared node recipes are validated before imports and executed by Setup only."""
from copy import deepcopy
import hashlib
import json
import zipfile

import pytest

from app.plugins.manifest import ManifestError, parse_manifest
from tests.test_public_node_contract import make_app, write_plugin
from tests.test_comfyui_node_install import wheel_bytes


def manifest():
    return {'id': 'sample.nodes', 'name': 'Node example', 'version': '1.0.0', 'api': 1,
            'schema_version': 2, 'publisher': {'id': 'sample', 'name': 'Sample'},
            'python_package': 'lds_example_nodes_v120',
            'compatibility': {'lds': '>=2026.1', 'api': '>=1.20,<2', 'python': '>=3.10',
                              'os': ['windows', 'linux', 'darwin'], 'arch': ['x86_64', 'arm64']},
            'owns': {'install_actions': ['sample_nodes']},
            'permissions': ['comfyui', 'filesystem'],
            'node_packs': [{'pack': 'Example nodes', 'url': 'https://example.invalid/nodes',
                            'search': 'Example', 'classes': ['ExampleNode'], 'installation': {
                                'action': 'sample_nodes', 'id': 'sample.nodes', 'version': '1.0.0',
                                'folder': 'sample_nodes', 'url': 'https://example.invalid/nodes-1.zip',
                                'sha256': 'a' * 64, 'requirements': ['example-wheel==1.2.3'],
                                'archive_prefix': 'nodes-1.0.0'}}]}


def test_installation_is_retained_without_aliasing_the_input_or_public_summary(tmp_path):
    data = manifest()
    original = deepcopy(data)
    parsed = parse_manifest(data, tmp_path)
    assert parsed.summary()['node_packs'] == original['node_packs']
    data['node_packs'][0]['installation']['requirements'].append('other==2')
    assert parsed.node_packs[0]['installation']['requirements'] == ['example-wheel==1.2.3']
    parsed.summary()['node_packs'][0]['installation']['requirements'].append('other==3')
    assert parsed.node_packs[0]['installation']['requirements'] == ['example-wheel==1.2.3']


@pytest.mark.parametrize('field,value', [
    ('action', 'unowned'), ('action', 'https://example.invalid/run'), ('id', '../escape'),
    ('folder', '../escape'), ('url', 'http://example.invalid/nodes.zip'),
    ('url', 'https://user:password@example.invalid/nodes.zip'), ('sha256', 'missing'),
    ('requirements', ['something>=1']), ('requirements', ['something==1.*']),
    ('requirements', ['--target=/outside']), ('requirements', ['something @ https://example.invalid/a.whl']),
    ('requirements', ['something==1', 'Something==2']), ('requirements', 'something==1'),
    ('archive_prefix', '../escape'), ('command', 'python -c anything'),
])
def test_invalid_installation_is_refused_before_plugin_import(tmp_path, field, value):
    data = manifest()
    data['node_packs'][0]['installation'][field] = value
    with pytest.raises(ManifestError, match='node_packs'):
        parse_manifest(data, tmp_path)


@pytest.mark.parametrize('api', ['>=1', '>=1.19,<2', '!=1.19', '<2', '>1.19', '>=1.20rc1'])
def test_older_host_floor_is_not_allowed_to_ignore_the_installation(tmp_path, api):
    data = manifest()
    data['compatibility']['api'] = api
    with pytest.raises(ManifestError, match='1.20'):
        parse_manifest(data, tmp_path)


@pytest.mark.parametrize('permissions', [[], ['filesystem'], ['comfyui']])
def test_node_installation_requires_both_permissions(tmp_path, permissions):
    data = manifest()
    data['permissions'] = permissions
    with pytest.raises(ManifestError, match='permissions'):
        parse_manifest(data, tmp_path)


@pytest.mark.parametrize('key', ['action', 'id', 'folder'])
def test_duplicate_recipe_identity_is_refused(tmp_path, key):
    data = manifest()
    other = deepcopy(data['node_packs'][0])
    other['installation'].update(action='other_nodes', id='other.nodes', folder='other_nodes')
    other['installation'][key] = data['node_packs'][0]['installation'][key]
    data['owns']['install_actions'].append('other_nodes')
    data['node_packs'].append(other)
    with pytest.raises(ManifestError, match='duplicate'):
        parse_manifest(data, tmp_path)


@pytest.mark.parametrize('classes', [[], 'ExampleNode', ['ExampleNode', 'ExampleNode'], ['Bad\nNode'], [5]])
def test_installed_node_classes_are_required_and_valid(tmp_path, classes):
    data = manifest()
    data['node_packs'][0]['classes'] = classes
    with pytest.raises(ManifestError, match='node_packs'):
        parse_manifest(data, tmp_path)


def test_legacy_node_inventory_remains_valid_without_installation_or_new_floor(tmp_path):
    data = {'id': 'sample.legacy', 'api': 1, 'name': 'Legacy', 'version': '1.0.0',
            'node_packs': [{'pack': 'Legacy pack', 'url': 'https://example.invalid/legacy',
                            'classes': ['RIFE VFI']}]}
    result = parse_manifest(data, tmp_path)
    assert result.node_packs == ({'pack': 'Legacy pack', 'url': 'https://example.invalid/legacy',
                                 'classes': ['RIFE VFI'], 'search': ''},)


def test_managed_recipe_accepts_real_comfy_class_names_and_optional_defaults(tmp_path):
    from app.plugins.node_packs import recipe
    data = manifest()
    pack = data['node_packs'][0]
    pack['classes'] = ['RIFE VFI']
    pack['installation']['folder'] = 'ComfyUI_Frame_Interpolation'
    del pack['installation']['requirements']
    del pack['installation']['archive_prefix']
    parsed = parse_manifest(data, tmp_path)
    frozen = recipe(parsed.node_packs[0])
    assert frozen.expected_classes == ('RIFE VFI',)
    assert frozen.folder == 'ComfyUI_Frame_Interpolation'
    assert frozen.requirements == () and frozen.archive_prefix == ''


def _node_app(tmp_path, monkeypatch, code='def register(ctx):\n    ctx.register_node_pack("sample_nodes")\n'):
    data = manifest()
    data['python_package'] += '_' + hashlib.sha256(code.encode()).hexdigest()[:8]
    write_plugin(tmp_path / 'data' / 'plugins', data['id'], package=data['python_package'], code=code,
                 **{key: value for key, value in data.items() if key not in ('id', 'python_package')})
    return make_app(tmp_path, monkeypatch)


def test_registration_maps_the_exact_declared_recipe_without_preparing_at_boot(tmp_path, monkeypatch):
    from app.services import comfyui_node_install as engine
    plans, installs = [], []
    monkeypatch.setattr(engine, 'plan', lambda recipe, **kw: plans.append((recipe, kw)) or {'plan_id': 'frozen-plan'})
    monkeypatch.setattr(engine, 'prepare', lambda recipe, **kw: installs.append((recipe, kw)) or {
        'state': 'prepared', 'restart_required': True})
    app = _node_app(tmp_path, monkeypatch)
    record = app.extensions['lds_plugins'].records['sample.nodes']
    assert record.state == 'loaded', record.error
    assert plans == installs == []
    spec = app.extensions['lds_plugins'].install_actions['sample_nodes']
    assert spec['node_pack'] == manifest()['node_packs'][0]
    logs = []
    assert spec['run'](log=logs.append) == 0
    recipe, owner = plans[0]
    assert owner == {'owner': 'sample.nodes'}
    assert recipe.url == manifest()['node_packs'][0]['installation']['url']
    assert recipe.expected_classes == ('ExampleNode',)
    assert recipe.requirements == ('example-wheel==1.2.3',)
    assert installs[0][0] == recipe
    assert installs[0][1]['plan_id'] == 'frozen-plan'
    assert 'prepared' in ' '.join(logs).lower() and 'restart_required' in ' '.join(logs)


@pytest.mark.parametrize('code', [
    'def register(ctx):\n    ctx.register_node_pack("not_declared")\n',
    'def register(ctx):\n    ctx.register_node_pack("sample_nodes", url="https://example.invalid/override")\n',
    'def register(ctx):\n    ctx.register_node_pack("sample_nodes")\n    ctx.register_node_pack("sample_nodes")\n',
    'def register(ctx):\n    ctx.register_install_action("sample_nodes", label="Old action", run=lambda log: 0)\n    ctx.register_node_pack("sample_nodes")\n',
    'def register(ctx):\n    ctx.register_node_pack("sample_nodes")\n    ctx.register_install_action("sample_nodes", label="Replacement", run=lambda log: 0)\n',
    'def register(ctx):\n    ctx.register_node_pack("sample_nodes")\n    ctx.register_model_download("sample_nodes", url="https://example.invalid/model", dest=("models", "x"), min_free_gb=0, min_bytes=1)\n',
])
def test_context_cannot_override_or_duplicate_the_declared_recipe(tmp_path, monkeypatch, code):
    app = _node_app(tmp_path, monkeypatch, code)
    assert app.extensions['lds_plugins'].records['sample.nodes'].state == 'error'




@pytest.mark.parametrize('result', [None, {'state': 'prepared'}, {'state': 'loaded', 'restart_required': True}])
def test_worker_requires_an_explicit_prepared_and_restart_required_receipt(tmp_path, monkeypatch, result):
    from app.services import comfyui_node_install as engine
    monkeypatch.setattr(engine, 'plan', lambda *a, **kw: {'plan_id': 'frozen-plan'})
    monkeypatch.setattr(engine, 'prepare', lambda *a, **kw: result)
    app = _node_app(tmp_path, monkeypatch)
    spec = app.extensions['lds_plugins'].install_actions['sample_nodes']
    with pytest.raises(engine.NodeInstallError, match='prepared result'):
        spec['run'](log=lambda line: None)


def test_sdk_and_host_versions_match_the_new_public_method():
    import lds_sdk
    from app.plugins.api import LDS_PLUGIN_API_MINOR, PUBLIC_NAMES, PluginContext
    assert LDS_PLUGIN_API_MINOR == lds_sdk.API_MINOR >= 20
    assert lds_sdk.VERSION == f'1.{LDS_PLUGIN_API_MINOR}'
    assert 'register_node_pack' in PUBLIC_NAMES and callable(PluginContext.register_node_pack)




def with_wheel():
    data = manifest()
    body = wheel_bytes('example-helper', '1.2.3')
    data['node_packs'][0]['installation'].update(wheelhouse='assets/wheels', wheels=[{
        'filename': 'example_helper-1.2.3-py3-none-any.whl', 'sha256': hashlib.sha256(body).hexdigest()}])
    return data, body


@pytest.mark.parametrize('field,value', [
    ('wheelhouse', '../outside'), ('wheelhouse', 'C:/outside'), ('wheelhouse', '.'),
    ('wheelhouse', 'assets\\wheels'), ('wheelhouse', ''), ('wheels', 'arbitrary'),
    ('wheels', [{'filename': '../outside.whl', 'sha256': 'a' * 64}]),
    ('wheels', [{'filename': 'example_helper-1.2.3-py3-none-any.whl', 'sha256': 'bad'}]),
    ('wheels', [{'path': 'arbitrary.whl', 'sha256': 'a' * 64}]),
])
def test_manifest_wheel_provenance_is_explicit_and_relative(tmp_path, field, value):
    data, _ = with_wheel()
    data['node_packs'][0]['installation'][field] = value
    with pytest.raises(ManifestError, match='node_packs'):
        parse_manifest(data, tmp_path)


def test_duplicate_wheel_distribution_and_missing_wheelhouse_are_refused(tmp_path):
    data, _ = with_wheel()
    install = data['node_packs'][0]['installation']
    install['wheels'].append({'filename': 'Example_Helper-2.0-py3-none-any.whl', 'sha256': 'b' * 64})
    with pytest.raises(ManifestError):
        parse_manifest(data, tmp_path)
    install['wheels'].pop()
    del install['wheelhouse']
    with pytest.raises(ManifestError, match='wheelhouse'):
        parse_manifest(data, tmp_path)


def test_facade_supplies_its_own_package_provenance_and_freezes_the_recipe(tmp_path, monkeypatch):
    from app.services import comfyui_node_install as engine
    data, body = with_wheel()
    code = 'def register(ctx):\n    ctx.register_node_pack("sample_nodes")\n'
    folder = write_plugin(tmp_path / 'data' / 'plugins', data['id'], package=data['python_package'], code=code,
                          **{key: value for key, value in data.items() if key not in ('id', 'python_package')})
    root = folder
    wheelhouse = root / 'assets/wheels'
    wheelhouse.mkdir(parents=True)
    (wheelhouse / data['node_packs'][0]['installation']['wheels'][0]['filename']).write_bytes(body)
    calls = []
    monkeypatch.setattr(engine, 'plan', lambda recipe, **kw: calls.append(('plan', recipe, kw)) or {'plan_id': 'x'})
    monkeypatch.setattr(engine, 'prepare', lambda recipe, **kw: calls.append(('prepare', recipe, kw)) or {
        'state': 'prepared', 'restart_required': True})
    app = make_app(tmp_path, monkeypatch)
    spec = app.extensions['lds_plugins'].install_actions['sample_nodes']
    assert calls == []
    assert spec['node_preflight']() == {'plan_id': 'x'}
    assert len(calls) == 1 and calls[0][0] == 'plan'
    spec['run'](log=lambda line: None)
    assert calls[0][1] == calls[1][1] == calls[2][1]
    assert calls[0][2] == calls[1][2] == {'owner': data['id'], 'wheel_root': wheelhouse}
    assert calls[2][2]['wheel_root'] == wheelhouse and calls[2][2]['owner'] == data['id']
    assert calls[0][1].wheels[0].filename == data['node_packs'][0]['installation']['wheels'][0]['filename']
    assert str(root) not in repr(calls[0][1])


@pytest.mark.parametrize('prefix', ['', 'package/', 'package\\'])
@pytest.mark.parametrize('condition', ['valid', 'missing', 'hash'])
def test_plugin_archive_must_carry_the_exact_declared_wheel(tmp_path, prefix, condition):
    from app.plugins.install import ArchiveError, inspect_plugin_zip
    data, body = with_wheel()
    path = tmp_path / 'plugin.zip'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(prefix + 'plugin.json', json.dumps(data))
        archive.writestr(prefix + data['python_package'] + '/__init__.py', 'def register(ctx): pass')
        if condition != 'missing':
            archive.writestr(prefix + 'assets/wheels/' + data['node_packs'][0]['installation']['wheels'][0]['filename'],
                             body if condition == 'valid' else b'changed')
    if condition == 'valid':
        parsed, result_prefix = inspect_plugin_zip(path)
        assert result_prefix == prefix.replace('\\', '/') and parsed.node_packs[0]['installation']['wheels']
    else:
        with pytest.raises(ArchiveError, match='wheel'):
            inspect_plugin_zip(path)
