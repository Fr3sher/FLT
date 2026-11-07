"""One-cycle adapter for local ``register(app, csrf)`` extension packages.

Discovery never imports code. A generated manifest joins normal enablement and
ordering; only an admitted record invokes the old entry point. This is trusted
local Python, like every plugin, not a sandbox.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from .api import LDS_PLUGIN_API_MAJOR
from .manifest import EXTERNAL_ID, PluginManifest
from .package_contract import validate_contract
from .registry import PluginRecord
from .registration import registration_transaction

log = logging.getLogger(__name__)
DEPRECATION = ('Legacy extension support is deprecated for one release cycle. '
               'Add plugin.json and migrate register(app, csrf) to register(ctx); '
               'install the converted plugin in data/plugins/.')


def legacy_dir() -> Path:
    override = os.environ.get('LDS_EXTENSIONS_DIR')
    return Path(override) if override else Path(__file__).resolve().parents[2] / 'extensions'


def legacy_id(name: str) -> str:
    candidate = f'legacy.{name}'
    if EXTERNAL_ID.fullmatch(candidate):
        return candidate
    # Old Python names were not limited to plugin-id spelling. Do not fold
    # two package names together when adapting uppercase or long names.
    digest = hashlib.sha256(name.encode('utf-8')).hexdigest()[:20]
    return f'legacy.pkg_{digest}'


def _metadata(path: Path) -> dict:
    values = {}
    try:
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id in ('__version__', 'FRONTEND_ENTRY'):
                    try:
                        value = ast.literal_eval(node.value)
                        values[target.id] = value if isinstance(value, str) else None
                    except (ValueError, TypeError):
                        pass  # Computed metadata is read only after an authorized import.
    except (OSError, UnicodeError, SyntaxError):
        pass  # The enabled import reports its normal paste-safe error.
    return values


def discover_legacy(registry) -> None:
    if os.environ.get('LDS_EXTENSIONS') == '0':
        return
    root = legacy_dir()
    if not root.is_dir():
        return
    installed_paths = {Path(record.dir).resolve() for record in registry.records.values()}
    # A damaged conversion still occupies its modern identity. Falling back
    # here would execute the old package precisely when its replacement broke.
    rejected_ids = {item.get(key) for item in (*registry.invalid, *registry.misplaced)
                    for key in ('id', 'dir')}
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not (path / '__init__.py').is_file():
            continue
        name, pid = path.name, legacy_id(path.name)
        if pid in registry.records or pid in rejected_ids or path.resolve() in installed_paths:
            log.warning('legacy extension %r ignored: its converted plugin is installed', name)
            continue
        metadata = _metadata(path / '__init__.py')
        manifest = PluginManifest(
            id=pid, bundled=False, name=name, version=metadata.get('__version__') or '0.0.0',
            api=LDS_PLUGIN_API_MAJOR, dir=path, python_package=name, description=DEPRECATION,
            contract=validate_contract({}))
        registry.records[pid] = PluginRecord(
            id=pid, manifest=manifest, dir=str(path), bundled=False,
            frontend_url=metadata.get('FRONTEND_ENTRY'),
            legacy={'name': name, 'version': metadata.get('__version__'),
                    'frontend_entry': metadata.get('FRONTEND_ENTRY')})
        log.warning('legacy extension %r: %s', name, DEPRECATION)


def _import_package(record):
    name = record.legacy['name']
    source = Path(record.dir) / '__init__.py'
    existing = sys.modules.get(name)
    if existing is not None:
        origin = getattr(existing, '__file__', None)
        if not origin or Path(origin).resolve() != source.resolve():
            raise ImportError(f'package {name!r} is already imported from another location')
        return existing
    # Import the discovered file, never an unrelated same-name module earlier
    # on sys.path. Keep the old name for its relative and absolute imports.
    base = str(source.parent.parent)
    if base not in sys.path:
        sys.path.append(base)
    spec = importlib.util.spec_from_file_location(name, source,
                                                submodule_search_locations=[str(source.parent)])
    if spec is None or spec.loader is None:
        raise ImportError(f'cannot load legacy package {name!r}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def register_legacy(app, csrf, registry, record) -> None:
    with registration_transaction(app, csrf, registry):
        module = _import_package(record)
        register = getattr(module, 'register', None)
        if not callable(register):
            raise AttributeError(f'{record.legacy["name"]} defines no register(app, csrf)')
        register(app, csrf)
        version = getattr(module, '__version__', None)
        frontend = getattr(module, 'FRONTEND_ENTRY', None)
        record.legacy.update(version=version if isinstance(version, str) else None,
                             frontend_entry=frontend if isinstance(frontend, str) else None)
        record.manifest = replace(record.manifest, version=record.legacy['version'] or '0.0.0')
        record.frontend_url = record.legacy['frontend_entry']


def legacy_manifest(registry) -> list:
    if registry is None:
        return []
    return [dict(record.legacy) for record in registry.records.values()
            if record.legacy is not None and record.enabled and record.state == 'loaded']
