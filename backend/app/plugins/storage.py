"""Keep plugin state outside code and prepare code changes for the next boot.

The running process never replaces its own packages. A durable intent points to
an extracted package; startup moves the previous package aside before publishing
the new one. The intent and the old package are retained on failure. This is a
filesystem recovery boundary, not a plugin database migration/rollback system.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from .. import config as cfg
from .install import ArchiveError, extract_plugin_zip
from .manifest import EXTERNAL_ID, ManifestError, load_manifest
from . import official


class StorageError(ValueError):
    pass


def managed_path(root: Path, *parts: str) -> Path:
    """An app-selected root is allowed; redirects below it are never managed."""
    root = root.resolve()
    target = root.joinpath(*parts)
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise StorageError('A plugin path must stay inside its managed folder.') from exc
    current = root
    for part in relative.parts:
        if part in ('', '.', '..'):
            raise StorageError('A plugin path must stay inside its managed folder.')
        current = current / part
        if current.is_symlink() or current.resolve() != current:
            raise StorageError('A linked plugin path cannot be managed by LDS.')
    return target


def data_dir(plugin_id: str) -> Path:
    return managed_path(cfg.data_dir(), 'plugin-data', plugin_id)


def _id(plugin_id):
    if not isinstance(plugin_id, str) or not (EXTERNAL_ID.fullmatch(plugin_id) or official.is_official_id(plugin_id)):
        raise StorageError('Invalid external plugin id.')


def _intent_path(root, plugin_id):
    _id(plugin_id)
    return managed_path(root, '.pending', plugin_id + '.json')


def _operation_dir(root, operation):
    if operation.get('transaction_id'):
        from .transactions import _folder
        _id(operation.get('id'))
        return managed_path(_folder(root, operation['transaction_id']), 'items', operation['id'])
    token = operation.get('token', '')
    if not isinstance(token, str) or len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
        raise StorageError('Invalid pending plugin operation.')
    return managed_path(root, '.pending', token)


def _write_bytes(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.write-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_json(path, value):
    _write_bytes(path, json.dumps(value).encode('utf-8'))


def _legacy_pending(root: Path) -> tuple[dict, list]:
    operations, errors = {}, []
    try:
        folder = managed_path(root, '.pending')
    except StorageError:
        return operations, [{'id': 'plugins', 'error': 'The pending plugin folder is linked; no changes can be applied.'}]
    if not folder.is_dir():
        return operations, errors
    for path in sorted(folder.glob('*.json')):
        try:
            plugin_id = path.stem
            path = _intent_path(root, plugin_id)
            operation = json.loads(path.read_text(encoding='utf-8'))
            if (not isinstance(operation, dict) or operation.get('id') != plugin_id
                    or operation.get('action') not in ('install', 'update', 'remove')
                    or type(operation.get('desired_enabled')) is not bool):
                raise StorageError('Invalid pending plugin operation.')
            _operation_dir(root, operation)
            operations[plugin_id] = operation
        except (OSError, ValueError, TypeError) as exc:
            errors.append({'id': path.stem, 'error': f'Cannot read pending operation: {type(exc).__name__}.'})
    return operations, errors


def pending(root: Path) -> tuple[dict, list]:
    from . import transactions
    operations, errors = _legacy_pending(root)
    grouped, group_errors = transactions.pending(root)
    if operations and grouped:
        errors.append({'id': 'plugins', 'error': 'Legacy and grouped pending changes require recovery before application.'})
    operations.update(grouped)
    return operations, errors + group_errors


def prepare_batch(root, items, *, preflight=None):
    from .transactions import prepare_batch as prepare
    return prepare(root, items, preflight=preflight)


def transaction_history(root):
    from .transactions import history
    return history(root)


def prepare_install(root, archive, manifest, prefix, *, replacing, desired_enabled, provenance=None, preflight=None):
    from .transactions import active, admission
    if manifest.contract.get('schema_version', 1) >= 2:
        if manifest.official and not provenance:
            raise StorageError('An official plugin needs verified installation provenance.')
        prepare_batch(root, [{'archive': archive, 'manifest': manifest, 'prefix': prefix,
                             'replacing': replacing, 'desired_enabled': desired_enabled, 'provenance': provenance}],
                      preflight=preflight)
        return pending(root)[0][manifest.id]
    with admission(root):
        if active(root) is not None:
            raise StorageError('Apply or recover the pending plugin transaction before preparing another change.')
        if preflight is not None:
            preflight()
        return _prepare_legacy_install(root, archive, manifest, prefix, replacing=replacing,
                                       desired_enabled=desired_enabled, provenance=provenance)


def _prepare_legacy_install(root, archive, manifest, prefix, *, replacing, desired_enabled, provenance=None):
    operation = {'id': manifest.id, 'token': uuid.uuid4().hex,
                 'action': 'update' if replacing else 'install',
                 'desired_enabled': bool(desired_enabled), 'manifest': manifest.summary()}
    if manifest.official:
        operation['provenance'] = provenance
    intent = _intent_path(root, manifest.id)
    if intent.exists():
        raise StorageError('Apply the pending change for this plugin before changing its package again.')
    folder = _operation_dir(root, operation)
    package = managed_path(folder, 'package')
    try:
        extract_plugin_zip(archive, package, prefix)
        if manifest.official and not official.valid_provenance(provenance, manifest.id, package):
            raise StorageError('An official plugin needs verified installation provenance.')
        # Data belongs to ctx.data_dir. A package cannot seed or replace it by
        # slipping a data folder into an upgrade archive.
        if (package / 'data').exists():
            raise ArchiveError('A plugin archive must not include a data folder; use ctx.data_dir at runtime.')
        _write_json(intent, operation)
    except Exception:
        # This is our uncommitted extraction only, never an installed package.
        if folder.exists():
            shutil.rmtree(managed_path(root, '.pending', operation['token']))
        raise
    return operation


def prepare_remove(root, plugin_id, *, keep_data):
    from .transactions import active, admission, _installed
    manifest = _installed(root, plugin_id)
    if manifest is not None and manifest.contract.get('schema_version', 1) >= 2:
        prepare_batch(root, [{'manifest': manifest, 'action': 'remove', 'keep_data': keep_data, 'desired_enabled': False}])
        return pending(root)[0][plugin_id]
    with admission(root):
        if active(root) is not None:
            raise StorageError('Apply or recover the pending plugin transaction before preparing another change.')
        return _prepare_legacy_remove(root, plugin_id, keep_data=keep_data)


def _prepare_legacy_remove(root, plugin_id, *, keep_data):
    intent = _intent_path(root, plugin_id)
    if intent.exists():
        raise StorageError('Apply the pending change for this plugin before removing it.')
    operation = {'id': plugin_id, 'token': uuid.uuid4().hex, 'action': 'remove',
                 'desired_enabled': False, 'keep_data': bool(keep_data)}
    _write_json(intent, operation)
    return operation


def set_pending_enabled(root, operation, enabled):
    if operation.get('transaction_id'):
        from .transactions import set_enabled
        return set_enabled(root, operation['transaction_id'], operation['id'], enabled)
    if operation['action'] == 'remove':
        raise StorageError('Apply the pending removal before reinstalling this plugin.')
    operation = {**operation, 'desired_enabled': bool(enabled)}
    _write_json(_intent_path(root, operation['id']), operation)


def migrate_data(root, plugin_id):
    """Adopt old data once, never replace an existing persistent directory.

    An older .data-kept archive is adopted only when no current data exists.
    Collisions are retained in place, including archives from the old installer.
    Code changes retain the whole old package, so those collisions survive too.
    """
    destination = data_dir(plugin_id)
    if destination.exists():
        if not destination.is_dir():
            raise StorageError('The persistent plugin data path is occupied by a file.')
        return destination
    live = managed_path(root, plugin_id, 'data')
    archived = managed_path(root, plugin_id + '.data-kept')
    source = live if live.exists() else archived
    if not source.exists():
        return destination
    if not source.is_dir():
        raise StorageError('The previous plugin data path is not a directory.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        source.rename(destination)
    except OSError as exc:
        if exc.errno != 18:  # EXDEV: an external plugin root may be on another drive.
            raise
        # Copy to a private sibling first. Preserve the original copy: a failed
        # copy cannot turn it into a partially removed tree. Symlinks stay links.
        temporary = managed_path(cfg.data_dir(), 'plugin-data', '.migrate-' + uuid.uuid4().hex)
        try:
            shutil.copytree(source, temporary, symlinks=True)
            temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    return destination


def _apply_one(root, operation):
    plugin_id = operation['id']
    folder = _operation_dir(root, operation)
    package = managed_path(folder, 'package')
    previous = managed_path(folder, 'previous')
    installed = managed_path(root, plugin_id)
    intent = _intent_path(root, plugin_id)
    action = operation['action']
    data = migrate_data(root, plugin_id)
    folder.mkdir(parents=True, exist_ok=True)
    if action != 'remove':
        # If the package has already moved, a crash happened after publication.
        # Finish the saved preference and receipt instead of moving it again.
        published = not package.exists() and installed.exists()
        candidate = installed if published else package
        provenance = operation.get('provenance')
        authorized = official.valid_provenance(provenance, plugin_id, candidate)
        manifest = load_manifest(candidate, official=authorized)
        if manifest.id != plugin_id or manifest.version != operation['manifest']['version'] or manifest.bundled:
            raise StorageError('The pending package does not match its accepted manifest.')
        if not published:
            if installed.exists():
                if previous.exists():
                    raise StorageError('Both current and recovery packages exist; no package was overwritten.')
                installed.rename(previous)
            try:
                package.rename(installed)
            except OSError:
                if previous.exists() and not installed.exists():
                    previous.rename(installed)
                raise
        if manifest.official:
            official.record_install(plugin_id, installed, provenance)
        cfg.save_config({'plugins': {'enabled': {plugin_id: operation['desired_enabled']}}})
    else:
        if installed.exists():
            if previous.exists():
                raise StorageError('Both current and recovery packages exist; no package was overwritten.')
            installed.rename(previous)
        if not operation.get('keep_data', True) and data.exists():
            # Explicit deletion is applied only after the old process stopped.
            shutil.rmtree(data_dir(plugin_id))
        cfg.save_config({'plugins': {'enabled': {plugin_id: None}}})
        official.forget_install(plugin_id)
    # Keep the prior package as recovery material. Retention/automatic rollback
    # after plugin registration and schema migration belong to the next phase.
    intent.unlink()


def apply_pending(root, app=None):
    operations, errors = pending(root)
    if errors:
        return errors
    grouped = [op for op in operations.values() if op.get('transaction_id')]
    if grouped:
        boot = app.extensions.get('lds_plugin_boot_transaction') if app is not None else None
        if boot is None:
            return [{'id': op['id'], 'error': 'The grouped transaction requires transactional startup support.'}
                    for op in grouped]
        boot.apply()
        return []
    for plugin_id, operation in operations.items():
        try:
            _apply_one(root, operation)
        except (OSError, ValueError, KeyError, ManifestError) as exc:
            # Do not expose machine paths or continue importing half-published
            # code. The loader marks this record unavailable for this boot.
            errors.append({'id': plugin_id, 'error': f'Could not apply plugin change ({type(exc).__name__}). '
                           'Its files and pending operation are retained; retry after resolving the storage error.'})
    return errors
