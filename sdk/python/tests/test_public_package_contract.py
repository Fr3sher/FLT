"""Public checkout adapter and parity with install-time wheel checks."""
import hashlib
import json

import pytest

import test_plugin_package_cli as package_tests
from lds_package import PackageError, pack, validate
from lds_package import common
from lds_package.source import HostSource

host = package_tests.host
source = package_tests.source
change_manifest = package_tests.change_manifest


def test_derived_sdk_version_does_not_import_the_application(host):
    (host / 'backend/lds_sdk/__init__.py').write_text(
        "from app.plugins.api import LDS_PLUGIN_API_MAJOR as API_MAJOR, LDS_PLUGIN_API_MINOR as API_MINOR\n"
        "VERSION = f'{API_MAJOR}.{API_MINOR}'\n__all__ = ['VERSION', 'API_MAJOR', 'API_MINOR']\n"
        "raise AssertionError('SDK source must not execute')\n", encoding='utf-8')
    (host / 'backend/app/plugins/api.py').write_text(
        "LDS_PLUGIN_API_MAJOR = 1\nLDS_PLUGIN_API_MINOR = 20\n"
        "raise AssertionError('API source must not execute')\n", encoding='utf-8')
    adapter = HostSource(host)
    try:
        assert adapter.sdk_version == '1.20'
    finally:
        adapter.close()


def _declare_wheel(source):
    data = b'qualified-wheel-bytes'
    name = 'assets/wheels/example_helper-1.0-py3-none-any.whl'
    path = source / name
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    manifest = json.loads((source / 'plugin.json').read_text())
    manifest['compatibility']['api'] = '>=1.20,<2'
    manifest.update(permissions=['comfyui', 'filesystem'], owns={'install_actions': ['example_nodes']},
                    node_packs=[{'pack': 'Example', 'url': 'https://example.invalid/nodes',
                                 'classes': ['ExampleNode'], 'installation': {
                                     'action': 'example_nodes', 'id': 'example.nodes', 'version': '1.0',
                                     'folder': 'example_nodes', 'url': 'https://example.invalid/nodes.zip',
                                     'sha256': 'a' * 64, 'wheelhouse': 'assets/wheels', 'wheels': [{
                                         'filename': path.name, 'sha256': hashlib.sha256(data).hexdigest()}]}}])
    change_manifest(source, **manifest)
    return name, path, data


@pytest.mark.parametrize('condition', ['missing', 'changed', 'too_large'])
def test_invalid_declared_wheel_never_produces_an_archive(source, host, tmp_path,
                                                        monkeypatch, condition):
    _, path, _ = _declare_wheel(source)
    if condition == 'missing':
        path.unlink()
    elif condition == 'changed':
        path.write_bytes(b'other bytes')
    else:
        monkeypatch.setattr(common, 'MAX_NODE_WHEEL_BYTES', 1, raising=False)
    archive = tmp_path / 'plugin.zip'
    with pytest.raises(PackageError, match='declared node wheel'):
        pack(source, archive, lds_source=host)
    assert not archive.exists()


def test_authoring_stays_out_and_the_declared_wheel_stays_exact(source, host):
    name, _, data = _declare_wheel(source)
    authoring = source / 'authoring'
    authoring.mkdir()
    (authoring / 'build.py').write_text("raise AssertionError('author tools never execute')\n")
    result = validate(source, lds_source=host)
    assert 'authoring' in result.excluded
    assert not any(path.startswith('authoring/') for path in result.files)
    assert result.files[name] == data


@pytest.mark.parametrize('exports', [
    "__all__ = ['visible', '_compat']",
    "_EXPORTS = {'visible': ('app.public', 'visible'), '_compat': ('app.public', '_compat')}\n"
    "__all__ = list(_EXPORTS)",
])
def test_explicit_sdk_exports_are_static_and_keep_undeclared_names_private(source, host, exports):
    (host / 'backend/lds_sdk/adapter.py').write_text(
        exports + "\nraise AssertionError('SDK code must never run')\n", encoding='utf-8')
    entry = source / 'example_camera/__init__.py'
    entry.write_text('from lds_sdk.adapter import visible, _compat\n', encoding='utf-8')
    assert validate(source, lds_source=host).manifest['id'] == 'example.camera'
    entry.write_text('from lds_sdk.adapter import hidden\n', encoding='utf-8')
    with pytest.raises(PackageError, match='non-public SDK'):
        validate(source, lds_source=host)


def test_filelock_requires_an_unconditional_host_requirement(source, host):
    (source / 'example_camera/__init__.py').write_text('from filelock import FileLock\n', encoding='utf-8')
    with pytest.raises(PackageError, match='not guaranteed'):
        validate(source, lds_source=host)
    path = host / 'backend/requirements.txt'
    original = path.read_text(encoding='utf-8')
    path.write_text(original + 'filelock==3.32.5\n', encoding='utf-8')
    assert validate(source, lds_source=host).dependencies['host_dependencies'] == {'filelock': '==3.32.5'}
    path.write_text(original + 'filelock==3.32.5; sys_platform == "win32"\n', encoding='utf-8')
    with pytest.raises(PackageError, match='not guaranteed'):
        validate(source, lds_source=host)


def test_public_sdk_submodules_allow_namespace_imports_without_granting_hidden_names(source, host):
    namespace = host / 'backend/lds_sdk/adapters'
    namespace.mkdir()
    (namespace / '__init__.py').write_text('"""Public namespace."""\n', encoding='utf-8')
    (namespace / 'camera.py').write_text("__all__ = ['probe']\n", encoding='utf-8')
    entry = source / 'example_camera/__init__.py'
    entry.write_text('from lds_sdk.adapters import camera\ncamera.probe()\n', encoding='utf-8')
    assert validate(source, lds_source=host).manifest['id'] == 'example.camera'
    entry.write_text('from lds_sdk.adapters import hidden\n', encoding='utf-8')
    with pytest.raises(PackageError, match='non-public SDK'):
        validate(source, lds_source=host)
