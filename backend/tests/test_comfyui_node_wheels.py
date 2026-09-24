"""Author-qualified wheels: synthetic packages only, no downloads or Python mutation."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

import pytest

from app.services import comfyui_node_install as nodes
from tests.test_comfyui_node_install import sandbox, wheel_bytes, pip_installs  # noqa: F401


def supplied(state, root, monkeypatch, *, name='example-helper', version='1.2.3', body=None):
    root.mkdir(parents=True)
    filename = f'{name.replace("-", "_")}-{version}-py3-none-any.whl'
    body = wheel_bytes(name, version) if body is None else body
    (root / filename).write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    recipe = replace(state.recipe, requirements=(f'{name}=={version}',),
                     wheels=(nodes.BundledWheel(filename, digest),))
    run = nodes._run

    def resolve(executable, args):
        if '--dry-run' in args:
            constraints = Path(args[args.index('--constraint') + 1]).read_text()
            line = next(line for line in constraints.splitlines() if line.startswith(name + ' @ '))
            state.reports = [{'metadata': {'name': name, 'version': version}, 'download_info': {
                'url': line.split(' @ ', 1)[1], 'archive_info': {'hashes': {'sha256': digest}}}}]
        return run(executable, args)

    monkeypatch.setattr(nodes, '_run', resolve)
    return recipe


def execute(recipe, root, owner='example.one'):
    plan = nodes.plan(recipe, owner=owner, wheel_root=root)
    return nodes.prepare(recipe, owner=owner, wheel_root=root, plan_id=plan['plan_id'])


def test_bundled_wheel_is_resolved_then_installed_from_verified_staging_only(sandbox, tmp_path, monkeypatch):
    root = tmp_path / 'plugin' / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch)
    assert execute(recipe, root)['state'] == 'prepared'
    assert len(sandbox.gets) == 1 and sandbox.gets[0][0] == recipe.url
    assert 'example-helper @ file:///' in sandbox.constraints
    assert str(root) not in sandbox.constraints and root.as_uri() not in sandbox.locked
    assert '--no-index' in pip_installs(sandbox)[0] and '--require-hashes' in pip_installs(sandbox)[0]
    assert sandbox.installed['torch'] == '2.8.0+cu128'


def test_local_version_wheel_satisfies_the_exact_upstream_version_pin(sandbox, tmp_path, monkeypatch):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch, name='antlr4-python3-runtime', version='4.9.3+lds.1')
    recipe = replace(recipe, requirements=('antlr4-python3-runtime==4.9.3',))
    assert execute(recipe, root)['state'] == 'prepared'


def test_logical_plan_and_shared_receipt_do_not_depend_on_plugin_installation_path(sandbox, tmp_path, monkeypatch):
    first, second = tmp_path / 'first' / 'wheels', tmp_path / 'second' / 'wheels'
    recipe = supplied(sandbox, first, monkeypatch)
    second.mkdir(parents=True)
    for path in first.iterdir():
        (second / path.name).write_bytes(path.read_bytes())
    one = nodes.plan(recipe, owner='example.one', wheel_root=first)
    two = nodes.plan(recipe, owner='example.one', wheel_root=second)
    assert one['plan_id'] == two['plan_id']
    execute(recipe, first)
    assert nodes.plan(recipe, owner='example.two', wheel_root=second)['state'] == 'shared'
    execute(recipe, second, 'example.two')
    receipt = json.loads((sandbox.base / 'custom_nodes' / recipe.folder / nodes.RECEIPT).read_text())
    assert receipt['owners'] == ['example.one', 'example.two']
    assert len(pip_installs(sandbox)) == 1


@pytest.mark.parametrize('change', ['missing', 'hash', 'hardlink', 'root'])
def test_source_provenance_is_checked_before_python_or_network(sandbox, tmp_path, monkeypatch, change):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch)
    path = root / recipe.wheels[0].filename
    if change == 'missing':
        path.unlink()
    elif change == 'hash':
        path.write_bytes(b'changed')
    elif change == 'hardlink':
        (tmp_path / 'linked.whl').hardlink_to(path)
    elif change == 'root':
        root = None
    with pytest.raises(nodes.NodeInstallError):
        nodes.plan(recipe, owner='example.one', wheel_root=root)
    assert sandbox.calls == [] and sandbox.gets == []


@pytest.mark.parametrize('filename', ['../escape.whl', 'C:/escape.whl', 'helper.tar.gz', 'not-a-wheel.whl'])
def test_invalid_wheel_descriptors_refuse_before_provenance_lookup(sandbox, filename):
    recipe = replace(sandbox.recipe, wheels=(nodes.BundledWheel(filename, 'a' * 64),))
    with pytest.raises(nodes.NodeInstallError):
        nodes.plan(recipe, owner='example.one', wheel_root=Path('/unused'))
    assert sandbox.calls == [] and sandbox.gets == []


@pytest.mark.parametrize('body', [
    wheel_bytes('different-name', '1.2.3'),
    wheel_bytes('example-helper', '9.0'),
    wheel_bytes('example-helper', '1.2.3', files={'example_helper-1.2.3.data/scripts/run': 'script'}),
    wheel_bytes('example-helper', '1.2.3', files={'example_helper-1.2.3.data/headers/header.h': 'header'}),
    wheel_bytes('example-helper', '1.2.3', files={'example_helper-1.2.3.dist-info/METADATA':
        'Metadata-Version: 2.1\nName: example-helper\nVersion: 1.2.3\nRequires-Dist: other @ file:///outside.whl\n'}),
])
def test_bundled_metadata_and_unsupported_writes_refuse_before_resolution(sandbox, tmp_path, monkeypatch, body):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch, body=body)
    with pytest.raises(nodes.NodeInstallError, match='wheel'):
        nodes.plan(recipe, owner='example.one', wheel_root=root)
    assert not any('--dry-run' in call for call in sandbox.calls)
    assert sandbox.gets == [] and pip_installs(sandbox) == []


def test_bundled_wheel_cannot_overwrite_existing_gpu_module(sandbox, tmp_path, monkeypatch):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch, body=wheel_bytes('example-helper', '1.2.3',
                      files={'torch/__init__.py': '# replacement'}))
    original = sandbox.python.parent / 'Lib/site-packages/torch/__init__.py'
    original.parent.mkdir(parents=True)
    original.write_text('# existing GPU')
    with pytest.raises(nodes.NodeInstallError, match='overwrite'):
        execute(recipe, root)
    assert original.read_text() == '# existing GPU' and pip_installs(sandbox) == []


def test_bundled_gpu_distribution_is_refused_even_with_valid_hash(sandbox, tmp_path, monkeypatch):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch, name='torch', version='2.9.0')
    with pytest.raises(nodes.NodeInstallError):
        nodes.plan(recipe, owner='example.one', wheel_root=root)
    assert sandbox.calls == [] and sandbox.gets == []


def test_modified_source_during_preparation_refuses_before_pip(sandbox, tmp_path, monkeypatch):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch)
    proposal = nodes.plan(recipe, owner='example.one', wheel_root=root)
    get = nodes.requests.get

    def race(*args, **kwargs):
        response = get(*args, **kwargs)
        (root / recipe.wheels[0].filename).write_bytes(b'changed after planning')
        return response

    monkeypatch.setattr(nodes.requests, 'get', race)
    with pytest.raises(nodes.NodeInstallError, match='SHA-256'):
        nodes.prepare(recipe, owner='example.one', wheel_root=root, plan_id=proposal['plan_id'])
    assert pip_installs(sandbox) == [] and not (sandbox.base / 'custom_nodes').exists()


@pytest.mark.parametrize('change', ['url', 'hash', 'name', 'version'])
def test_report_cannot_select_an_unverified_local_file(sandbox, tmp_path, monkeypatch, change):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch)
    run = nodes._run

    def forged(executable, args):
        result = run(executable, args)
        if '--dry-run' in args:
            report = Path(args[args.index('--report') + 1])
            data = json.loads(report.read_text())
            item = data['install'][0]
            if change == 'url':
                item['download_info']['url'] = (tmp_path / 'unverified.whl').as_uri()
            elif change == 'hash':
                item['download_info']['archive_info']['hashes']['sha256'] = 'f' * 64
            else:
                item['metadata'][change] = 'other' if change == 'name' else '9.0'
            report.write_text(json.dumps(data))
        return result

    monkeypatch.setattr(nodes, '_run', forged)
    with pytest.raises(nodes.NodeInstallError, match='unverifiable'):
        nodes.plan(recipe, owner='example.one', wheel_root=root)
    assert sandbox.gets == [] and pip_installs(sandbox) == []


def test_unused_bundled_wheel_does_not_trigger_dependency_installation(sandbox, tmp_path, monkeypatch):
    root = tmp_path / 'wheels'
    recipe = supplied(sandbox, root, monkeypatch)
    recipe = replace(recipe, requirements=('numpy==2.2.6',))
    assert execute(recipe, root)['state'] == 'prepared'
    assert not any('--dry-run' in call for call in sandbox.calls)
    assert pip_installs(sandbox) == [] and 'example-helper' not in sandbox.installed


def test_real_pip_resolves_a_bundled_transitive_wheel_without_index_or_installation(tmp_path, monkeypatch):
    # A real CPU resolver proves direct constraints and local-version URLs work.
    # Both dependency wheels are synthetic; --no-index forbids any repository lookup.
    root, temporary = tmp_path / 'wheels', tmp_path / 'plan'
    root.mkdir()
    temporary.mkdir()
    wheels = []
    for name, version, requirement in [('lds-wheel-parent', '1.0', 'lds-wheel-child==1.0'),
                                     ('lds-wheel-child', '1.0+lds.1', None)]:
        module = name.replace('-', '_')
        metadata = f'Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n'
        if requirement:
            metadata += f'Requires-Dist: {requirement}\n'
        body = wheel_bytes(name, version, files={f'{module}/__init__.py': '# synthetic',
            f'{module}-{version}.dist-info/METADATA': metadata})
        filename = f'{module}-{version}-py3-none-any.whl'
        (root / filename).write_bytes(body)
        wheels.append(nodes.BundledWheel(filename, hashlib.sha256(body).hexdigest()))
    recipe = nodes.NodeRecipe(id='sample.nodes', version='1', folder='example',
        url='https://example.invalid/nodes.zip', sha256='a' * 64, expected_classes=('Example',),
        requirements=('lds-wheel-parent==1.0',), wheels=tuple(wheels))
    binding = {'install_paths': {name: str(tmp_path / 'target' / name)
                               for name in ('purelib', 'platlib', 'scripts', 'data')}}
    bundled = nodes._bundled_wheels(recipe, root, temporary, binding)
    original = nodes._run

    def isolated(python, args):
        assert '--dry-run' in args
        args = list(args)
        index = args.index('--index-url')
        args[index:index + 2] = ['--no-index']
        return original(python, args)

    monkeypatch.setattr(nodes, '_run', isolated)
    resolved = nodes._dependency_plan(recipe, Path(sys.executable), {}, temporary, bundled)
    assert [(item['name'], item['version']) for item in resolved] == [
        ('lds-wheel-child', '1.0+lds.1'), ('lds-wheel-parent', '1.0')]
    assert all('filename' in item and 'url' not in item for item in resolved)
    assert not (tmp_path / 'target').exists()
