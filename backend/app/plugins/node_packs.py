"""Manifest-only custom-node recipes and their API 1.20 registration adapter."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from packaging.specifiers import SpecifierSet
from packaging.version import Version

_REQUIRED = {'action', 'id', 'version', 'folder', 'url', 'sha256'}
_FIELDS = _REQUIRED | {'requirements', 'archive_prefix', 'wheelhouse', 'wheels', 'python'}
_ACTION = re.compile(r'[a-z][a-z0-9_.:-]{0,119}\Z')


class NodePackError(ValueError):
    pass


def recipe(pack):
    """Build immutable worker input from the declared recipe, never a request."""
    from .node_recipe import BundledWheel, NodeRecipe
    install = pack['installation']
    return NodeRecipe(id=install['id'], version=install['version'], folder=install['folder'],
                      url=install['url'], sha256=install['sha256'],
                      expected_classes=tuple(pack['classes']),
                      requirements=tuple(install.get('requirements', [])),
                      archive_prefix=install.get('archive_prefix', ''),
                      python=install.get('python', '>=3.10'),
                      wheels=tuple(sorted((BundledWheel(**wheel) for wheel in install.get('wheels', [])),
                                          key=lambda wheel: wheel.filename)))


def wheel_root(pack, directory):
    """Resolve only the manifest's wheelhouse under this plugin's own directory."""
    if not pack['installation'].get('wheels'):
        return None
    from ..services.comfyui_node_install import _safe
    base = _safe(Path(directory).absolute())
    target = _safe(base / pack['installation']['wheelhouse'])
    if not target.is_relative_to(base) or target == base:
        raise NodePackError('node_packs wheelhouse must stay inside its own plugin package.')
    return target


def validate(packs, *, plugin_id, owns, permissions, contract):
    """Validate the extension before importing any plugin code; legacy stays inert."""
    managed = [pack for pack in packs if 'installation' in pack]
    if not managed:
        return
    if not {'comfyui', 'filesystem'} <= set(permissions):
        raise NodePackError('node_packs installation requires comfyui and filesystem permissions.')
    api = SpecifierSet(contract.get('compatibility', {}).get('api', ''))
    if contract.get('schema_version') != 2 or not any(
            item.operator in {'>=', '>', '~=', '=='}
            and Version(item.version.removesuffix('.*')) >= Version('1.20') for item in api):
        raise NodePackError('node_packs installation requires schema_version 2 and a compatibility.api floor of 1.20.')
    seen = {key: set() for key in ('action', 'id', 'folder')}
    from .node_recipe import _validate
    for pack in managed:
        install = pack['installation']
        if (not isinstance(install, dict) or set(install) - _FIELDS or _REQUIRED - set(install)
                or any(not isinstance(install[key], str) or not install[key] for key in _REQUIRED)
                or not isinstance(install.get('archive_prefix', ''), str)
                or not isinstance(install.get('requirements', []), list)
                or any(not isinstance(value, str) for value in install.get('requirements', []))
                or not isinstance(install.get('wheels', []), list)
                or any(not isinstance(wheel, dict) or set(wheel) != {'filename', 'sha256'}
                       or any(not isinstance(value, str) for value in wheel.values())
                       for wheel in install.get('wheels', []))):
            raise NodePackError('node_packs installation must contain a declared action and a complete pinned recipe, without extra fields.')
        if install.get('wheels') or 'wheelhouse' in install:
            from .install import _entry_relpath
            try:
                folder = install.get('wheelhouse')
                if (not install.get('wheels') or not isinstance(folder, str)
                        or _entry_relpath(folder) != folder):
                    raise ValueError
            except ValueError as exc:
                raise NodePackError('node_packs wheels require a safe relative wheelhouse inside the plugin.') from exc
        action = install['action']
        if (not _ACTION.fullmatch(action) or action.startswith('plugin_environment:')
                or action not in owns.get('install_actions', ())):
            raise NodePackError('node_packs installation action must be unique and declared in owns.install_actions.')
        if (not isinstance(pack.get('classes'), list) or not pack['classes']
                or not all(isinstance(value, str) for value in pack['classes'])):
            raise NodePackError('node_packs installation requires a list of expected ComfyUI classes.')
        for key, values in seen.items():
            value = install[key].casefold()
            if value in values:
                raise NodePackError(f'node_packs contains a duplicate installation {key}.')
            values.add(value)
        try:
            _validate(recipe(pack), plugin_id)
        except ValueError as exc:
            raise NodePackError(f'node_packs installation: {exc}') from exc


def register(ctx, action):
    """Resolve one declared action and reuse Setup's supervised run pipeline."""
    validate(ctx._manifest.node_packs, plugin_id=ctx.id, owns=ctx._manifest.owns,
             permissions=ctx._manifest.permissions, contract=ctx._manifest.contract)
    declared = [pack for pack in ctx._manifest.node_packs
                if pack.get('installation', {}).get('action') == action]
    if len(declared) != 1:
        raise NodePackError('register_node_pack must name one installation declared in node_packs.')
    if action in ctx._registry.install_actions or action in ctx._registry.model_downloads:
        raise NodePackError('The node-pack installation action is already registered.')
    from ..services import comfyui_node_install as engine
    pack = deepcopy(declared[0])
    frozen = recipe(pack)
    owner = ctx.id
    provenance = wheel_root(pack, ctx._manifest.dir)
    arguments = {'wheel_root': provenance} if provenance is not None else {}

    def preflight():
        return engine.plan(frozen, owner=owner, **arguments)

    def run(log):
        planned = preflight()
        result = engine.prepare(frozen, owner=owner, plan_id=planned['plan_id'], log=log, **arguments)
        if not isinstance(result, dict) or result.get('state') != 'prepared' or result.get('restart_required') is not True:
            raise engine.NodeInstallError('The custom-node preparation did not confirm a prepared result.')
        log('Node files prepared; restart_required=true. Restart ComfyUI, then verify that its node classes loaded.')
        return 0

    ctx.register_install_action(action, label=f"Prepare ComfyUI nodes: {pack['pack']}", run=run)
    ctx._registry.install_actions[action]['node_pack'] = pack
    ctx._registry.install_actions[action]['node_preflight'] = preflight
