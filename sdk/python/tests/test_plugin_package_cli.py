"""Publisher-facing failures and byte-for-byte package proofs; no app boots."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types
import uuid
import zipfile

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'sdk/python'))

from lds_package import PackageError, pack, validate  # noqa: E402
from lds_package import common, core  # noqa: E402
from lds_package.cli import main  # noqa: E402


@pytest.fixture
def installed_contracts():
    """Read the host's pure archive/parser contracts without importing app."""
    namespace = '_lds_package_test_' + uuid.uuid4().hex
    package = types.ModuleType(namespace)
    package.__path__ = [str(REPO / 'backend/app')]
    sys.modules[namespace] = package
    sys.modules[namespace + '.config'] = types.ModuleType(namespace + '.config')
    try:
        yield (importlib.import_module(namespace + '.plugins.install'),
               importlib.import_module(namespace + '.plugins.environment'))
    finally:
        for name in tuple(sys.modules):
            if name == namespace or name.startswith(namespace + '.'):
                del sys.modules[name]


@pytest.fixture
def host(tmp_path):
    root = tmp_path / 'host'
    plugins = root / 'backend/app/plugins'
    plugins.mkdir(parents=True)
    for name in ('manifest.py', 'package_contract.py', 'node_packs.py', 'node_recipe.py', 'install.py'):
        shutil.copyfile(REPO / 'backend/app/plugins' / name, plugins / name)
    (plugins / 'official.py').write_text("OFFICIAL_IDS = frozenset({'camera_angles'})\n", encoding='utf-8')
    (root / 'backend/app/version.py').write_text("APP_VERSION = '2030.01.07'\n", encoding='utf-8')
    sdk = root / 'backend/lds_sdk'
    sdk.mkdir()
    (sdk / '__init__.py').write_text("VERSION = '1.5'\n__all__ = ['VERSION']\n", encoding='utf-8')
    (sdk / 'config.py').write_text("__all__ = ['get']\n", encoding='utf-8')
    (root / 'backend/requirements.txt').write_text(
        'Flask==3.1.3\nPillow==12.3.0\nrequests>=2.32\npackaging==26.0\nhuggingface-hub>=0.24\n', encoding='utf-8')
    return root


@pytest.fixture
def source(tmp_path):
    root = tmp_path / 'plugin'
    root.mkdir()
    manifest = {'id': 'example.camera', 'name': 'Camera', 'version': '1.0.0', 'api': 1,
                'python_package': 'example_camera', 'schema_version': 2, 'bundled': False,
                'publisher': {'id': 'example', 'name': 'Example'},
                'compatibility': {'lds': '>=2026.1', 'api': '>=1.5,<2', 'python': '>=3.10,<4',
                                  'os': ['windows', 'linux', 'darwin'], 'arch': ['x86_64', 'arm64']},
                'requires': [], 'frontend_styles': [], 'data_schema': 1}
    write_manifest(root, manifest)
    (root / 'example_camera').mkdir()
    (root / 'example_camera/__init__.py').write_text('from lds_sdk.config import get\n', encoding='utf-8')
    return root


def write_manifest(source, manifest):
    (source / 'plugin.json').write_text(json.dumps(manifest), encoding='utf-8')


def change_manifest(source, **changes):
    data = json.loads((source / 'plugin.json').read_text(encoding='utf-8'))
    data.update(changes)
    write_manifest(source, data)


def python(source, code):
    (source / 'example_camera/__init__.py').write_text(code, encoding='utf-8')


@pytest.fixture
def js_tools():
    folder = Path(os.environ.get('LDS_PLUGIN_JS_TOOLS', REPO / 'sdk/python'))
    if not shutil.which('node') or not (folder / 'node_modules/acorn/package.json').is_file():
        pytest.skip('Install sdk/python development dependencies or set LDS_PLUGIN_JS_TOOLS')
    return folder


def frontend(source, code):
    folder = source / 'frontend'
    folder.mkdir(exist_ok=True)
    (folder / 'index.js').write_text(code, encoding='utf-8')
    (folder / 'styles.css').write_text('.camera { color: #abc; }\n', encoding='utf-8')
    change_manifest(source, frontend='frontend/index.js', frontend_styles=['frontend/styles.css'])


def test_reproducible_archive_after_source_metadata_changes(source, host, tmp_path):
    first = pack(source, tmp_path / 'a.zip', lds_source=host)
    for file in source.rglob('*'):
        if file.is_file():
            os.utime(file, (1_000_000, 1_000_000))
    second = pack(source, tmp_path / 'b.zip', lds_source=host)
    assert first['sha256'] == second['sha256']
    with zipfile.ZipFile(tmp_path / 'a.zip') as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        assert all(info.compress_type == zipfile.ZIP_STORED for info in archive.infolist())
        assert all(info.external_attr >> 16 == 0o100644 for info in archive.infolist())
    python(source, 'from lds_sdk.config import get\nVALUE = 2\n')
    assert pack(source, tmp_path / 'c.zip', lds_source=host)['sha256'] != first['sha256']


def test_authoring_helpers_stay_out_of_the_installable_package(source, host, tmp_path):
    authoring = source / 'authoring'
    authoring.mkdir()
    (authoring / 'build.py').write_text('import importlib.metadata\n', encoding='utf-8')
    result = pack(source, tmp_path / 'authoring.ldsplugin', lds_source=host)
    assert 'authoring' in result['excluded']
    with zipfile.ZipFile(tmp_path / 'authoring.ldsplugin') as archive:
        assert not any(name.startswith('authoring/') for name in archive.namelist())
    python(source, 'from authoring.build import run\n')
    with pytest.raises(PackageError):
        validate(source, lds_source=host)


def test_official_conversion_is_explicit_and_uses_host_versions(source, host, tmp_path):
    change_manifest(source, id='camera_angles', bundled=True, schema_version=1)
    data = json.loads((source / 'plugin.json').read_text())
    del data['publisher']
    write_manifest(source, data)
    with pytest.raises(PackageError, match='explicit --official-lds'):
        validate(source, lds_source=host)
    result = pack(source, tmp_path / 'camera.zip', lds_source=host, official_lds=True)
    assert result['manifest']['bundled'] is False
    assert result['manifest']['schema_version'] == 2
    assert result['manifest']['publisher'] == {'id': 'lds', 'name': 'LDS'}
    assert result['manifest']['compatibility']['lds'] == '>=2030.1.7'
    assert result['manifest']['compatibility']['api'] == '<2,>=1.5'
    assert not any(key in result['manifest'] for key in ('official', 'provenance', 'receipt', 'dir'))
    assert json.loads((source / 'plugin.json').read_text())['bundled'] is True


def test_official_unknown_id_rejected(source, host):
    with pytest.raises(PackageError, match='registry'):
        validate(source, lds_source=host, official_lds=True)


def optional_source(source):
    change_manifest(source, id='camera_angles', publisher={'id': 'lds', 'name': 'LDS'}, in_process_requirements=True,
                    owns={'install_actions': ['camera_extras']})
    (source / 'extras.txt').write_text('tiny-extra>=1,<2\n', encoding='utf-8')
    (source / 'lds-package.json').write_text(json.dumps({'optional_host_dependencies': {
        'tiny_extra': {'distribution': 'tiny-extra', 'requirements': 'extras.txt',
                       'setup_action': 'camera_extras'}}}), encoding='utf-8')


@pytest.mark.parametrize('code', [
    'def run():\n    import tiny_extra\n',
    'try:\n    import tiny_extra\nexcept ImportError:\n    tiny_extra = None\n',
])
def test_official_optional_dependency_can_be_absent_at_boot(source, host, code):
    optional_source(source)
    python(source, code)
    result = validate(source, lds_source=host, official_lds=True)
    assert result.dependencies['optional_host_dependencies']['tiny_extra']['setup_action'] == 'camera_extras'
    assert 'tiny-extra' not in result.manifest['host_dependencies']


@pytest.mark.parametrize('code', [
    'import tiny_extra\n',
    'try:\n    import tiny_extra\nexcept ValueError:\n    pass\n',
    'try:\n    pass\nexcept ImportError:\n    import tiny_extra\n',
    'class AtBoot:\n    import tiny_extra\n',
])
def test_optional_dependency_cannot_be_required_at_boot(source, host, code):
    optional_source(source)
    python(source, code)
    with pytest.raises(PackageError, match='optional host import'):
        validate(source, lds_source=host, official_lds=True)


@pytest.mark.parametrize('change', ['absent_file', 'unowned_action', 'unversioned', 'url', 'third_party'])
def test_optional_dependency_requires_reviewed_complete_setup(source, host, change):
    optional_source(source)
    python(source, 'def run():\n    import tiny_extra\n')
    if change == 'absent_file':
        (source / 'extras.txt').unlink()
    elif change == 'unowned_action':
        change_manifest(source, owns={})
    elif change == 'unversioned':
        (source / 'extras.txt').write_text('tiny-extra\n')
    elif change == 'url':
        (source / 'extras.txt').write_text('tiny-extra @ https://example.invalid/a.whl\n')
    else:
        change_manifest(source, id='example.camera', publisher={'id': 'example', 'name': 'Example'}, in_process_requirements=False)
    with pytest.raises(PackageError):
        validate(source, lds_source=host, official_lds=change != 'third_party')


@pytest.mark.parametrize('method', ['register_data_migration', 'register_health_check'])
def test_transaction_callbacks_require_api_minor_declaration(source, host, method):
    python(source, f'def register(ctx):\n    ctx.{method}(1, 2, lambda ctx: True)\n')
    with pytest.raises(PackageError, match='requires compatibility.api >=1.6'):
        validate(source, lds_source=host)
    data = json.loads((source / 'plugin.json').read_text())
    data['compatibility']['api'] = '>=1.6,<2'
    write_manifest(source, data)
    validate(source, lds_source=host)


@pytest.mark.parametrize('api', ['>=1.4,!=1.5,<2', '<1.5', '>1.5,<2', '>=1.5.1,<2'])
def test_migration_cannot_advertise_an_api_below_its_real_minimum(source, host, api):
    python(source, 'def register(ctx):\n    ctx.register_data_migration(1, 2, lambda ctx: None)\n')
    data = json.loads((source / 'plugin.json').read_text())
    data['compatibility']['api'] = api
    write_manifest(source, data)
    with pytest.raises(PackageError, match='requires compatibility.api >=1.6'):
        validate(source, lds_source=host)


@pytest.mark.parametrize('api', ['>=1.6,<2', '~=1.6', '==1.6', '==1.6.*', '>1.6,<2'])
def test_migration_accepts_equivalent_explicit_minimum_ranges(source, host, api):
    python(source, 'def register(ctx):\n    ctx.register_health_check("ready", lambda ctx: True)\n')
    data = json.loads((source / 'plugin.json').read_text())
    data['compatibility']['api'] = api
    write_manifest(source, data)
    validate(source, lds_source=host)


def test_regular_compile_and_model_eval_methods_are_not_python_execution(source, host):
    python(source, "import re\nPATTERN = re.compile(r'word')\ndef inference(model):\n    model.eval()\n")
    validate(source, lds_source=host)


@pytest.mark.parametrize('changes', [
    {'schema_version': True}, {'schema_version': 1}, {'bundled': 'false'},
    {'in_process_requirements': 1}, {'api': True}, {'id': 'short_id'},
    {'version': 'not a version'}, {'permissions': ['admin:anything']},
    {'owns': {'unknown': []}}, {'provenance': {'publisher': 'lds'}},
])
def test_invalid_manifest_never_creates_output(source, host, tmp_path, changes):
    change_manifest(source, **changes)
    output = tmp_path / 'bad.zip'
    with pytest.raises(PackageError):
        pack(source, output, lds_source=host)
    assert not output.exists()
    assert not list(tmp_path.glob('.lds-package-*'))


def test_duplicate_json_field_rejected(source, host):
    (source / 'plugin.json').write_text('{"id":"aa.bb","id":"cc.dd"}')
    with pytest.raises(PackageError, match='duplicate JSON field'):
        validate(source, lds_source=host)


@pytest.mark.parametrize('relative', ['CON.txt', 'file%20name.txt', 'dir/PRN.css', 'file.', 'file ', 'wrong\\path'])
def test_portable_name_profile(relative):
    with pytest.raises(PackageError, match='Non-portable'):
        common.portable(relative)


def test_secret_environment_cache_tests_and_data_are_excluded(source, host):
    for folder in ('data', 'node_modules', 'tests', '.git', '.venv', '__pycache__'):
        (source / folder).mkdir()
        (source / folder / 'private.txt').write_text('do not distribute')
    for name in ('.env', 'token.txt', 'secret.pem', 'model.safetensors'):
        (source / name).write_text('do not distribute')
    result = validate(source, lds_source=host)
    assert set(result.files) == {'plugin.json', 'example_camera/__init__.py'}
    assert len(result.excluded) == 10


def test_embedded_private_key_rejected_without_disclosing_it(source, host):
    secret = '-----BEGIN ' + 'PRIVATE KEY-----'
    (source / 'credentials.txt').write_text(secret)
    with pytest.raises(PackageError, match='Credential') as error:
        validate(source, lds_source=host)
    assert secret not in str(error.value)


def test_hard_link_rejected(source, host, tmp_path):
    outside = tmp_path / 'outside.txt'
    outside.write_text('outside')
    os.link(outside, source / 'linked.txt')
    with pytest.raises(PackageError, match='Links'):
        validate(source, lds_source=host)


def test_symbolic_link_rejected(source, host, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    try:
        (source / 'linked').symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip('Symlink creation is unavailable on this runner')
    with pytest.raises(PackageError, match='Links'):
        validate(source, lds_source=host)


def test_case_collision_rejected(source, host, monkeypatch):
    # Emulate a case-sensitive publisher tree even on the Windows runner.
    original = Path.iterdir
    def entries(path):
        if path == source:
            yield source / 'Readme.txt'
            yield source / 'README.TXT'
        else:
            yield from original(path)
    (source / 'Readme.txt').write_text('one')
    monkeypatch.setattr(Path, 'iterdir', entries)
    with pytest.raises(PackageError, match='Case-insensitive duplicate'):
        validate(source, lds_source=host)


@pytest.mark.parametrize('limit', ['bytes', 'files'])
def test_size_and_count_limits_before_archive(source, host, tmp_path, monkeypatch, limit):
    if limit == 'bytes':
        monkeypatch.setattr(common, 'MAX_BYTES', 5)
    else:
        monkeypatch.setattr(common, 'MAX_FILES', 1)
    with pytest.raises(PackageError, match='limit'):
        pack(source, tmp_path / 'bad.zip', lds_source=host)
    assert not (tmp_path / 'bad.zip').exists()


def test_missing_frontend_and_css_rejected(source, host):
    change_manifest(source, frontend='frontend/index.js')
    with pytest.raises(PackageError, match='absent'):
        validate(source, lds_source=host)
    frontend(source, 'export const answer = 42;')
    (source / 'frontend/styles.css').unlink()
    with pytest.raises(PackageError, match='CSS is absent'):
        validate(source, lds_source=host)


@pytest.mark.parametrize('name', ['frontend/index.js', 'frontend/styles.css'])
def test_empty_declared_asset_is_refused_before_publication(source, host, tmp_path, name):
    frontend(source, 'export const answer = 42;')
    (source / name).write_bytes(b'')
    output = tmp_path / 'empty.zip'
    with pytest.raises(PackageError, match='empty'):
        pack(source, output, lds_source=host)
    assert not output.exists()


def test_normalized_manifest_limit_matches_installer(source, host, tmp_path, installed_contracts):
    installer, _ = installed_contracts
    MAX_MANIFEST_BYTES = installer.MAX_MANIFEST_BYTES
    # A compact input fits, while canonical indentation can exceed the ZIP limit.
    change_manifest(source, description='x' * (MAX_MANIFEST_BYTES - 500))
    assert (source / 'plugin.json').stat().st_size < MAX_MANIFEST_BYTES
    output = tmp_path / 'too-large.zip'
    with pytest.raises(PackageError, match='manifest.*65536'):
        pack(source, output, lds_source=host)
    assert not output.exists()
    change_manifest(source, description='x' * (MAX_MANIFEST_BYTES - 2000))
    pack(source, output, lds_source=host)
    assert installer.inspect_plugin_zip(output)[0].id == 'example.camera'


def test_worker_pep508_requirements_roundtrip_to_setup(source, host, tmp_path, installed_contracts):
    installer, environment = installed_contracts
    (source / 'example_camera/worker.py').write_text('import requests\n')
    (source / 'requirements.txt').write_text('requests (>=2.32,<3)\n')
    change_manifest(source, requirements='requirements.txt')
    (source / 'lds-package.json').write_text(json.dumps({
        'python_scripts': ['example_camera/worker.py'], 'python_dependencies': {'requests': 'requests'}}))
    output = tmp_path / 'worker.zip'
    pack(source, output, lds_source=host)
    assert installer.inspect_plugin_zip(output)[0].requirements == 'requirements.txt'
    from packaging.requirements import Requirement
    assert Requirement(environment._specs(['requests (>=2.32,<3)'])[0]) == Requirement('requests>=2.32,<3')


def test_host_declarations_do_not_install_into_plugin_venv(source, host):
    python(source, 'from flask import Blueprint\nfrom PIL import Image\nimport huggingface_hub\n')
    result = validate(source, lds_source=host)
    assert result.dependencies['host_dependencies'] == {'flask': '==3.1.3', 'pillow': '==12.3.0', 'huggingface-hub': '>=0.24'}
    assert 'requirements' not in result.manifest
    assert result.manifest['host_dependencies'] == result.dependencies['host_dependencies']


@pytest.mark.parametrize('code,match', [
    ('from app import config\n', 'private LDS'),
    ('import app.config as c\n', 'private LDS'),
    ('import importlib as x\nx.import_module("app")\n', 'dynamic module'),
    ('from importlib import import_module as x\nx("app")\n', 'dynamic module'),
    ('import pkgutil\npkgutil.resolve_name("app:config")\n', 'dynamic module'),
    ('load = __import__\nload("app")\n', 'dynamic code'),
    ('getattr(__builtins__, "__im" + "port__")("app")\n', 'dynamic code'),
    ('import sys\nsys.modules["app"]\n', 'runtime import'),
    ('from sys import modules as loaded\n', 'runtime import'),
    ('from lds_sdk.config import _private\n', 'non-public SDK'),
    ('from lds_sdk import config as cfg\ncfg.hidden()\n', 'non-public SDK'),
    ('from lds_sdk import config as cfg\nx = cfg\nx.hidden()\n', 'non-public SDK'),
    ('from lds_sdk import config as cfg\ngetattr(cfg, "hidden")()\n', 'reflective module'),
    ('import not_installed_here\n', 'not guaranteed'),
])
def test_private_dynamic_and_undeclared_python_imports_fail(source, host, code, match):
    python(source, code)
    with pytest.raises(PackageError, match=match):
        validate(source, lds_source=host)


def test_plugin_requirements_cannot_authorize_backend_import(source, host):
    python(source, 'import torch\n')
    (source / 'requirements.txt').write_text('torch>=2,<3\n')
    change_manifest(source, requirements='requirements.txt')
    with pytest.raises(PackageError, match='venv requirements do not extend'):
        validate(source, lds_source=host)


def test_explicit_isolated_script_and_mapping(source, host):
    (source / 'example_camera/inference.py').write_text('import torch\n')
    (source / 'requirements.txt').write_text('torch>=2,<3\n')
    change_manifest(source, requirements='requirements.txt')
    (source / 'lds-package.json').write_text(json.dumps({
        'python_scripts': ['example_camera/inference.py'], 'python_dependencies': {'torch': 'torch'}}))
    result = validate(source, lds_source=host)
    assert result.dependencies['isolated_dependencies'] == {'torch': 'torch'}
    assert 'lds-package.json' not in result.files
    python(source, 'from .inference import run\n')
    with pytest.raises(PackageError, match='cannot import an isolated'):
        validate(source, lds_source=host)
    python(source, 'from example_camera import inference\n')
    with pytest.raises(PackageError, match='cannot import an isolated'):
        validate(source, lds_source=host)


def test_backend_entry_point_cannot_be_declared_isolated(source, host):
    python(source, 'import torch\n')
    (source / 'requirements.txt').write_text('torch>=2,<3\n')
    change_manifest(source, requirements='requirements.txt')
    (source / 'lds-package.json').write_text(json.dumps({
        'python_scripts': ['example_camera/__init__.py'], 'python_dependencies': {'torch': 'torch'}}))
    with pytest.raises(PackageError, match='entry point cannot'):
        validate(source, lds_source=host)


def shared_source(source):
    python(source, 'from .common import answer\n')
    (source / 'example_camera/common.py').write_text('import json\nanswer = 42\n')
    (source / 'example_camera/worker.py').write_text(
        'import os\nimport sys\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n'
        'from common import answer\n')
    (source / 'lds-package.json').write_text(json.dumps({
        'python_scripts': ['example_camera/worker.py'],
        'python_shared_modules': ['example_camera/common.py']}))


def test_shared_stdlib_helper_is_available_to_backend_and_isolated_worker(source, host):
    shared_source(source)
    result = validate(source, lds_source=host)
    assert result.dependencies['python_shared_modules'] == ['example_camera/common.py']
    assert result.dependencies['host_dependencies'] == {}


@pytest.mark.parametrize('code', [
    'from lds_sdk.config import get\n', 'from flask import Flask\n',
    'from .worker import answer\n', 'from . import worker\n',
    'from example_camera import worker\n',
])
def test_shared_helper_cannot_bridge_worker_and_backend_dependencies(source, host, code):
    shared_source(source)
    (source / 'example_camera/common.py').write_text(code)
    with pytest.raises(PackageError, match='shared Python modules'):
        validate(source, lds_source=host)


@pytest.mark.parametrize('bootstrap', [
    'sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))',
    'sys.path.insert(0, "../backend")',
    'sys.path.append(os.path.dirname(os.path.abspath(__file__)))',
    'sys.path.insert(0, os.environ["EXTRA_PATH"])',
])
def test_isolated_bootstrap_cannot_expand_to_host_or_environment(source, host, bootstrap):
    shared_source(source)
    (source / 'example_camera/worker.py').write_text('import os\nimport sys\n' + bootstrap + '\n')
    with pytest.raises(PackageError, match='runtime import'):
        validate(source, lds_source=host)


def test_shared_and_worker_profiles_cannot_overlap(source, host):
    shared_source(source)
    (source / 'lds-package.json').write_text(json.dumps({
        'python_scripts': ['example_camera/common.py'],
        'python_shared_modules': ['example_camera/common.py']}))
    with pytest.raises(PackageError, match='disjoint'):
        validate(source, lds_source=host)


@pytest.mark.parametrize('change', [
    None, 'missing_restore', 'wrong_restore', 'extra_statement', 'outside_helper',
    'undeclared_helper', 'helper_call', 'handler', 'mutate_saved', 'rebind_saved',
    'wrapped_restore', 'partial_restore', 'shadow_saved', 'shadow_sys',
])
def test_scoped_worker_bootstrap_only_restores_declared_shared_imports(source, host, change):
    code = ('import os\nimport sys\n_import_path = list(sys.path)\n'
            'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n'
            'try:\n    from common import answer\nfinally:\n    sys.path[:] = _import_path\n')
    changes = {
        'missing_restore': ('sys.path[:] = _import_path', 'pass'),
        'wrong_restore': ('sys.path[:] = _import_path', 'sys.path[:] = ["../backend"]'),
        'extra_statement': ('finally:', '    answer()\nfinally:'),
        'outside_helper': ('from common import answer', 'from os import getenv'),
        'undeclared_helper': ('from common import answer', 'from other import answer'),
        'helper_call': ('from common import answer', 'answer = 42'),
        'handler': ('finally:', 'except ImportError:\n    pass\nfinally:'),
        'mutate_saved': ('try:', '_import_path.append("../backend")\ntry:'),
        'rebind_saved': ('try:', '_import_path = []\ntry:'),
        'wrapped_restore': ('sys.path[:] = _import_path', 'sys.path[:] = list(_import_path)'),
        'partial_restore': ('sys.path[:] = _import_path', 'sys.path[0:1] = _import_path'),
        'shadow_saved': ('from common import answer', 'from common import answer as _import_path'),
        'shadow_sys': ('from common import answer', 'from common import answer as sys'),
    }
    if change:
        code = code.replace(*changes[change])
    (source / 'example_camera/worker.py').write_text(code)
    (source / 'example_camera/common.py').write_text('answer = 42\n')
    (source / 'lds-package.json').write_text(json.dumps({
        'python_scripts': ['example_camera/worker.py'],
        'python_shared_modules': ['example_camera/common.py']}))
    if change:
        with pytest.raises(PackageError):
            validate(source, lds_source=host)
    else:
        assert validate(source, lds_source=host).dependencies['python_shared_modules'] == ['example_camera/common.py']


def test_backend_cannot_change_import_path_even_with_valid_worker_bootstrap(source, host):
    shared_source(source)
    python(source, 'import os\nimport sys\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n')
    with pytest.raises(PackageError, match='runtime import'):
        validate(source, lds_source=host)


def test_private_script_requirements_are_mandatory(source, host):
    (source / 'inference.py').write_text('import torch\n')
    (source / 'lds-package.json').write_text(json.dumps({
        'python_scripts': ['inference.py'], 'python_dependencies': {'torch': 'torch'}}))
    with pytest.raises(PackageError, match='unconditional in requirements'):
        validate(source, lds_source=host)


@pytest.mark.parametrize('requirement', ['--extra-index-url https://example.invalid', 'torch @ file:///private/torch', '-e .'])
def test_unsafe_requirement_forms_rejected(source, host, requirement):
    (source / 'requirements.txt').write_text(requirement)
    change_manifest(source, requirements='requirements.txt')
    with pytest.raises(PackageError):
        validate(source, lds_source=host)


def test_public_sdk_local_and_stdlib_imports(source, host):
    python(source, 'from lds_sdk import config as cfg\nfrom .helper import answer\nfrom pathlib import Path\ncfg.get("x")\n')
    (source / 'example_camera/helper.py').write_text('import json\nanswer=42\n')
    assert validate(source, lds_source=host).manifest['id'] == 'example.camera'


@pytest.mark.parametrize('code,match', [
    ('import x from "@lds/private/config";', 'Bundle external'),
    ('import("https://example.invalid/a.js");', 'Bundle external'),
    ('const p="./chunk.js"; import(p);', 'Computed dynamic imports'),
    ('import("./" + "chunk.js");', 'Computed dynamic imports'),
    ('import("../../outside.js");', 'outside the package'),
    ('const run=eval; run("1");', 'Dynamic code loading'),
    ('globalThis["eval"]("1");', 'Dynamic code loading'),
    ('const g=globalThis; g["Fun"+"ction"]("return 1")();', 'Computed global'),
    ('new Worker("./chunk.js");', 'Worker entry points'),
    ('document.createElement("script");', 'DOM script'),
    ('setTimeout("console.log(1)", 100);', 'String timers'),
])
def test_javascript_ast_rejects_nonportable_loading(source, host, js_tools, code, match):
    frontend(source, code)
    with pytest.raises(PackageError, match=match):
        validate(source, lds_source=host, js_tools=js_tools)


def test_javascript_static_and_literal_dynamic_chunks(source, host, js_tools):
    frontend(source, 'import "./chunk.js"; export const run=()=>import("./chunk.js");')
    (source / 'frontend/chunk.js').write_text('export const answer = 42;')
    assert validate(source, lds_source=host, js_tools=js_tools).manifest['frontend_styles'] == ['frontend/styles.css']


def worker_source(source):
    frontend(source, 'export function start(url) { return new Worker(url); }')
    (source / 'frontend/worker.js').write_text('self.onmessage = event => self.postMessage(event.data);')
    change_manifest(source, frontend_workers=[{'entry': 'frontend/worker.js', 'loaders': ['frontend/index.js']}])


def test_worker_profile_records_included_entry_and_actual_loader(source, host, js_tools):
    worker_source(source)
    result = validate(source, lds_source=host, js_tools=js_tools)
    assert result.manifest['frontend_workers'][0]['entry'] == 'frontend/worker.js'


@pytest.mark.parametrize('change', ['missing_worker', 'empty_worker', 'unused_loader', 'undeclared_loader',
                                     'worker_import', 'shared_worker', 'worker_eval', 'function_alias'])
def test_worker_profile_does_not_disable_loading_audit(source, host, js_tools, change):
    worker_source(source)
    worker = source / 'frontend/worker.js'
    if change == 'missing_worker':
        worker.unlink()
    elif change == 'empty_worker':
        worker.write_text('')
    elif change == 'unused_loader':
        (source / 'frontend/index.js').write_text('export const noWorker = true;')
    elif change == 'undeclared_loader':
        (source / 'frontend/hidden.js').write_text('new Worker("./worker.js");')
    elif change == 'worker_import':
        worker.write_text('importScripts("https://example.invalid/script.js");')
    elif change == 'shared_worker':
        (source / 'frontend/index.js').write_text('new SharedWorker("./worker.js");')
    elif change == 'function_alias':
        worker.write_text('const constructor = Function; constructor("return 1")();')
    else:
        worker.write_text('new Function("return 1")();')
    with pytest.raises(PackageError):
        validate(source, lds_source=host, js_tools=js_tools)


def test_function_instanceof_check_does_not_execute_source(source, host, js_tools):
    frontend(source, 'export const callable = value => value instanceof Function;')
    validate(source, lds_source=host, js_tools=js_tools)


def test_missing_acorn_is_an_error(source, host, tmp_path):
    frontend(source, 'export const x=1;')
    with pytest.raises(PackageError, match='audit'):
        validate(source, lds_source=host, js_tools=tmp_path)


def test_unlisted_css_and_source_jsx_rejected(source, host, js_tools):
    frontend(source, 'export const x=1;')
    change_manifest(source, frontend_styles=[])
    with pytest.raises(PackageError, match='all built CSS'):
        validate(source, lds_source=host, js_tools=js_tools)
    change_manifest(source, frontend_styles=['frontend/styles.css'])
    (source / 'frontend/App.jsx').write_text('export const App=()=> <div/>;')
    with pytest.raises(PackageError, match='built ESM'):
        validate(source, lds_source=host, js_tools=js_tools)


def test_output_outside_source_and_explicit_overwrite(source, host, tmp_path):
    with pytest.raises(PackageError, match='outside the source'):
        pack(source, source / 'inside.zip', lds_source=host)
    output = tmp_path / 'package.zip'
    output.write_bytes(b'existing')
    with pytest.raises(PackageError, match='already exists'):
        pack(source, output, lds_source=host)
    assert output.read_bytes() == b'existing'
    pack(source, output, lds_source=host, overwrite=True)
    assert zipfile.is_zipfile(output)


def test_publish_race_never_clobbers_existing_file(source, host, tmp_path, monkeypatch):
    output = tmp_path / 'package.zip'
    link = os.link
    def race(old, new):
        Path(new).write_bytes(b'competing writer')
        link(old, new)
    monkeypatch.setattr(os, 'link', race)
    with pytest.raises(FileExistsError):
        pack(source, output, lds_source=host)
    assert output.read_bytes() == b'competing writer'
    assert not list(tmp_path.glob('.lds-package-*'))


def test_partial_archive_is_removed_and_old_output_preserved(source, host, tmp_path, monkeypatch):
    output = tmp_path / 'package.zip'
    output.write_bytes(b'previous')
    def broken(*args, **kwargs):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(zipfile.ZipFile, 'writestr', broken)
    with pytest.raises(OSError, match='synthetic'):
        pack(source, output, lds_source=host, overwrite=True)
    assert output.read_bytes() == b'previous'
    assert not list(tmp_path.glob('.lds-package-*'))


def test_manifest_dir_stripped_and_source_not_executed(source, host, tmp_path):
    change_manifest(source, dir='/author/machine/checkout')
    python(source, 'raise RuntimeError("plugin code must not execute")\n')
    assert 'dir' not in validate(source, lds_source=host).manifest
    result = subprocess.run([sys.executable, str(REPO / 'scripts/plugin_package.py'), 'pack', str(source),
                             '--lds-source', str(host), '--output', str(tmp_path / 'cli.zip')],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['sha256'] == hashlib.sha256((tmp_path / 'cli.zip').read_bytes()).hexdigest()


def test_cli_failure_is_structured_and_nonzero(source, host, capsys):
    python(source, 'import app\n')
    assert main(['validate', str(source), '--lds-source', str(host)]) == 2
    assert json.loads(capsys.readouterr().err)['ok'] is False


def test_cli_unicode_manifest_survives_ascii_windows_pipe(source, host):
    change_manifest(source, name='Camera \u25b8 \U0001f4f7')
    result = subprocess.run([sys.executable, str(REPO / 'scripts/plugin_package.py'), 'validate', str(source),
                             '--lds-source', str(host)], env={**os.environ, 'PYTHONIOENCODING': 'ascii'},
                            capture_output=True, text=True, encoding='ascii', check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['manifest']['name'] == 'Camera \u25b8 \U0001f4f7'


def test_development_namespace_removed_after_validation(source, host):
    before = {name for name in sys.modules if name.startswith('_lds_package_')}
    validate(source, lds_source=host)
    assert {name for name in sys.modules if name.startswith('_lds_package_')} == before


def test_node_recipe_can_be_packaged_with_pure_host_contracts_only(source, host, tmp_path):
    # This authoring host deliberately has no config, services, Flask app or
    # installation worker. Recipe validation must stay usable in that context.
    change_manifest(source, compatibility={'lds': '>=2026.1', 'api': '>=1.20,<2',
                    'python': '>=3.10', 'os': ['windows'], 'arch': ['x86_64']},
                    permissions=['comfyui', 'filesystem'], owns={'install_actions': ['example_nodes']},
                    node_packs=[{'pack': 'Example', 'url': 'https://example.invalid/nodes',
                                 'classes': ['ExampleNode'], 'installation': {
                                     'action': 'example_nodes', 'id': 'example.nodes', 'version': '1.0.0',
                                     'folder': 'example_nodes', 'url': 'https://example.invalid/nodes.zip',
                                     'sha256': 'a' * 64, 'python': '>=3.12'}}])
    result = pack(source, tmp_path / 'node-recipe.ldsplugin', lds_source=host)
    assert result['manifest']['node_packs'][0]['installation']['python'] == '>=3.12'
    data = json.loads((source / 'plugin.json').read_text())
    data['node_packs'][0]['installation']['url'] = 'http://example.invalid/untrusted.zip'
    write_manifest(source, data)
    with pytest.raises(PackageError, match='HTTPS'):
        validate(source, lds_source=host)


def test_validation_snapshots_bytes_before_zip_creation(source, host, tmp_path, monkeypatch):
    original = core._destination
    def change_after_validation(*args):
        python(source, 'import app\n')
        return original(*args)
    monkeypatch.setattr(core, '_destination', change_after_validation)
    pack(source, tmp_path / 'snapshot.zip', lds_source=host)
    with zipfile.ZipFile(tmp_path / 'snapshot.zip') as archive:
        assert b'import app' not in archive.read('example_camera/__init__.py')


@pytest.mark.parametrize('keyword,value', [('companions', '[]'), ('complete', 'lambda: True'),
                                          ('extra_roots', 'lambda: []')])
def test_model_stage_callbacks_require_api_18(source, host, keyword, value):
    python(source, f'def register(ctx):\n    ctx.register_model_download("stage", {keyword}={value})\n')
    data = json.loads((source / 'plugin.json').read_text())
    data['compatibility']['api'] = '>=1.7,<2'
    write_manifest(source, data)
    with pytest.raises(PackageError, match='require compatibility.api >=1.8'):
        validate(source, lds_source=host)
    data['compatibility']['api'] = '>=1.8,<2'
    write_manifest(source, data)
    validate(source, lds_source=host)


def test_restore_providers_require_api_19(source, host):
    python(source, 'def register(ctx):\n    ctx.register_restore_engine("restore", preflight=lambda: None, enqueue=lambda **kw: None, error_response=lambda error: None)\n')
    data = json.loads((source / 'plugin.json').read_text())
    data['compatibility']['api'] = '>=1.8,<2'
    write_manifest(source, data)
    with pytest.raises(PackageError, match='require compatibility.api >=1.9'):
        validate(source, lds_source=host)
    data['compatibility']['api'] = '>=1.9,<2'
    write_manifest(source, data)
    validate(source, lds_source=host)
