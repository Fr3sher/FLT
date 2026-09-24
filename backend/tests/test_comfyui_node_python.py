"""Custom-node Python requirements fail before resolving or changing dependencies."""
from dataclasses import asdict, replace
import json
import zipfile

import pytest

from app.plugins.manifest import ManifestError, parse_manifest
from app.services import comfyui_node_install as nodes
from tests.test_comfyui_node_install import sandbox, prepare, pip_installs  # noqa: F401
from tests.test_plugin_node_packs import manifest


@pytest.mark.parametrize('version,allowed', [([3, 11, 10], False), ([3, 12, 0], True), ([3, 12, 10], True)])
def test_actual_comfy_python_boundary_is_checked_before_resolution(sandbox, monkeypatch, version, allowed):
    sandbox.probe_override['version'] = version
    recipe = replace(sandbox.recipe, python='>=3.12')
    called = []
    monkeypatch.setattr(nodes, '_bundled_wheels', lambda *args, **kwargs: called.append('staging') or {})
    if allowed:
        assert nodes.plan(recipe, owner='example.one')['state'] == 'install'
        assert called == ['staging']
    else:
        with pytest.raises(nodes.NodeInstallError, match=r'Python 3\.11\.10.*Python >=3\.12') as error:
            nodes.plan(recipe, owner='example.one')
        assert str(sandbox.base) not in str(error.value)
        assert called == [] and len(sandbox.calls) == 1
    assert sandbox.gets == [] and pip_installs(sandbox) == []
    assert not (sandbox.base / 'custom_nodes').exists()


@pytest.mark.parametrize('value', ['', ' ', ', ,', '3.12', '>=broken', '>=3.12; os_name=="nt"', 5, None, '>=' + '3' * 119])
def test_invalid_python_declaration_is_rejected_before_target_operations(sandbox, value):
    recipe = replace(sandbox.recipe, python=value)
    with pytest.raises(nodes.NodeInstallError, match='Python version specifier'):
        nodes.plan(recipe, owner='example.one')
    assert sandbox.calls == [] and sandbox.gets == []


def test_runtime_change_after_a_valid_plan_is_refused_before_installation(sandbox):
    recipe = replace(sandbox.recipe, python='>=3.12')
    plan = nodes.plan(recipe, owner='example.one')
    sandbox.probe_override['version'] = [3, 11, 10]
    with pytest.raises(nodes.NodeInstallError, match='requires Python >=3.12'):
        nodes.prepare(recipe, owner='example.one', plan_id=plan['plan_id'])
    assert sandbox.gets == [] and pip_installs(sandbox) == []


def test_legacy_receipt_is_upgraded_only_for_the_unchanged_python_default(sandbox):
    prepare(sandbox)
    marker = sandbox.base / 'custom_nodes' / sandbox.recipe.folder / nodes.RECEIPT
    receipt = json.loads(marker.read_text())
    legacy = asdict(sandbox.recipe)
    legacy.pop('python')
    receipt['recipe_sha256'] = nodes._digest(legacy)
    marker.write_text(json.dumps(receipt))
    assert nodes.plan(sandbox.recipe, owner='example.two')['state'] == 'shared'
    with pytest.raises(nodes.NodeInstallError, match='recipe or its files changed'):
        nodes.plan(replace(sandbox.recipe, python='>=3.12'), owner='example.two')
    assert json.loads(marker.read_text()) == receipt
    prepare(sandbox, owner='example.two')
    updated = json.loads(marker.read_text())
    assert updated['recipe_sha256'] == nodes._digest(asdict(sandbox.recipe))
    assert updated['owners'] == ['example.one', 'example.two']
    assert len(sandbox.gets) == 1 and pip_installs(sandbox) == []


def test_python_compatibility_is_part_of_plan_identity(sandbox):
    plan = nodes.plan(sandbox.recipe, owner='example.one')
    with pytest.raises(nodes.NodeInstallError, match='fresh installation plan'):
        nodes.prepare(replace(sandbox.recipe, python='>=3.12'), owner='example.one', plan_id=plan['plan_id'])
    assert sandbox.gets == [] and pip_installs(sandbox) == []


@pytest.mark.parametrize('value', ['>=3.12', '', ' ', '3.12', None])
def test_manifest_and_archive_admission_validate_the_node_python_field(tmp_path, value):
    from app.plugins.install import ArchiveError, inspect_plugin_zip
    from app.plugins.node_packs import recipe
    data = manifest()
    data['node_packs'][0]['installation']['python'] = value
    archive = tmp_path / 'plugin.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('plugin.json', json.dumps(data))
        output.writestr(data['python_package'] + '/__init__.py', 'def register(ctx): pass')
    if value == '>=3.12':
        parsed = parse_manifest(data, tmp_path)
        assert recipe(parsed.node_packs[0]).python == value
        assert inspect_plugin_zip(archive)[0].node_packs[0]['installation']['python'] == value
    else:
        with pytest.raises(ManifestError, match='Python version specifier'):
            parse_manifest(data, tmp_path)
        with pytest.raises(ArchiveError, match='Python version specifier'):
            inspect_plugin_zip(archive)


def test_recipe_without_python_declaration_keeps_the_default(tmp_path):
    from app.plugins.node_packs import recipe
    parsed = parse_manifest(manifest(), tmp_path)
    assert recipe(parsed.node_packs[0]).python == '>=3.10'
