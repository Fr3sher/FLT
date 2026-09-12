"""Prepare a consented set of verified packages, with no import during download."""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime, timezone

from ... import config as cfg
from .. import official, storage
from ..install import inspect_archive, inspect_plugin_zip
from ..loader import external_dir
from .catalog import parse_catalog, plan_digest, resolve
from .client import StoreError, StoreSession, load_config
from .commerce import CommerceClient, download_release


def installed_manifests(registry):
    return {pid: r.manifest for pid, r in registry.records.items() if r.manifest and r.legacy is None} if registry else {}


def _browse_path(config):
    return storage.managed_path(cfg.data_dir(), 'plugin-store', 'catalogs', config.identity, 'browse.json')


def browse():
    config = load_config()
    try:
        with StoreSession(config) as session:
            raw = session.catalog()
            catalog = parse_catalog(raw, config)
        checked = datetime.now(timezone.utc).isoformat()
        storage._write_json(_browse_path(config), {'catalog': raw, 'checked_at': checked})
        return _browse_payload(catalog, checked, False)
    except StoreError:
        # Display-only offline cache. Every plan and install opens a fresh TUF
        # session and cannot promote these cached display fields into trust.
        try:
            cached = json.loads(_browse_path(config).read_text(encoding='utf-8'))
            return _browse_payload(parse_catalog(cached['catalog'], config), cached['checked_at'], True)
        except (OSError, ValueError, KeyError, TypeError):
            raise StoreError('The store is unavailable and no verified catalog has been cached yet.') from None


def _browse_payload(catalog, checked, offline):
    return {'status': 'offline' if offline else 'ready', 'checked_at': checked,
            'message': 'Showing the last verified catalog. Connect to the store to install or update.' if offline else '',
            'products': [{'id': pid, 'releases': [r.payload() for r in releases]} for pid, releases in catalog.items()]}


def _plan(session, registry, plugin_id, version):
    catalog = parse_catalog(session.catalog(), session.config)
    installed = installed_manifests(registry)
    active = {pid for pid, record in registry.records.items() if record.state == 'loaded'} if registry else set()
    solution = resolve(catalog, plugin_id, installed, version=version, active=active)
    by_id = {r.manifest.id: r for r in solution}
    def closure(roots):
        needed = set(roots)
        while True:
            expanded = needed | {dep for pid in needed for dep in by_id[pid].manifest.requires}
            if expanded == needed:
                return needed
            needed = expanded

    # A replacement kept ON can introduce its own dependencies. Include their
    # activation in consent, while an old owner kept OFF has no such effect.
    # Already-active roots retain their flag rather than becoming dependencies
    # of the requested independent product in the displayed plan.
    needed = closure({plugin_id}) | (closure(active) - active)
    flags = cfg.get('plugins.enabled') or {}
    changes = [r for r in solution if r.target and (
        r.manifest.id not in installed or installed[r.manifest.id].version != r.manifest.version
        or installed[r.manifest.id].bundled)]
    # Even a same-version reinstall comes from a newly authenticated target.
    if not changes:
        changes = [r for r in solution if r.manifest.id == plugin_id and r.target]
    changes += [r for r in solution if r not in changes and r.manifest.id in needed
                and flags.get(r.manifest.id) is False]
    identity = plan_digest(solution, installed, session.config.identity)
    # A concurrent toggle/removal or prepared package invalidates the consent.
    operations, errors = storage.pending(external_dir())
    if operations or errors:
        raise StoreError('Apply or cancel the pending plugin changes before preparing another package set.')
    identity = hashlib.sha256((identity + json.dumps(flags, sort_keys=True)).encode()).hexdigest()
    return changes, identity, needed


def preview_plan(registry, plugin_id, version=None):
    with StoreSession() as session:
        changes, identity, needed = _plan(session, registry, plugin_id, version)
        paid = [r.manifest.id for r in changes if r.target and r.price['kind'] == 'paid']
        acquired, commerce_status = set(), 'not_required'
        if paid:
            try:
                library = CommerceClient().library()
                commerce_status = library['status']
                acquired = {item['plugin_id'] for item in library['items'] if item['status'] == 'active'}
            except StoreError:
                commerce_status = 'unavailable'
        installed = installed_manifests(registry)
        flags = cfg.get('plugins.enabled') or {}
        return {'plan_id': identity, 'requested': plugin_id, 'version': version,
                'packages': [{**r.payload(), 'action': 'install' if r.target else 'enable',
                              'will_enable': r.manifest.id in needed,
                              'previous_version': installed[r.manifest.id].version if r.manifest.id in installed else None,
                              'reason': 'requested' if r.manifest.id == plugin_id else
                                        'dependency' if r.manifest.id in needed else 'compatibility_update',
                              'remains_disabled': r.manifest.id not in needed and flags.get(r.manifest.id) is False,
                              } for r in changes], 'restart_required': True,
                'paid_packages': paid, 'commerce_status': commerce_status,
                'purchase_required': [pid for pid in paid if pid not in acquired]}


def prepare(registry, plugin_id, version, accepted_plan, *, check_change=None):
    if not isinstance(accepted_plan, str) or len(accepted_plan) != 64:
        raise StoreError('Review the installation plan before confirming it.')
    with StoreSession() as session:
        changes, identity, needed = _plan(session, registry, plugin_id, version)
        if identity != accepted_plan:
            raise StoreError('The catalog or installed plugins changed. Review the new installation plan.')
        prepared = []
        for release in changes:
            if check_change:
                check_change(release.manifest.id)
            if not release.target:
                prepared.append({'manifest': release.manifest, 'enable_only': True, 'desired_enabled': True})
                continue
            if release.price['kind'] == 'paid':
                target = session.target_info(release.target)
                # A cached paid archive is not an entitlement. Every acquisition
                # gets a fresh server grant bound to these authenticated bytes.
                path = download_release(release, target, session.target_destination(target))
            else:
                path, target = session.target(release.target)
            m, prefix = inspect_plugin_zip(path, official=release.manifest.id in session.config.official_ids)
            with zipfile.ZipFile(path) as archive:
                _, found_prefix = inspect_archive(archive)
                digest = hashlib.sha256(archive.read(found_prefix + 'plugin.json')).hexdigest()
            if (m.id != release.manifest.id or m.version != release.manifest.version
                    or digest != release.manifest_sha256
                    or m.summary() != release.manifest.summary()):
                raise StoreError('The downloaded package does not match the reviewed catalog manifest.')
            provenance = {'id': m.id, 'publisher': 'lds', 'source': 'verified_store',
                          'manifest_sha256': digest, 'archive_sha256': target.hashes['sha256'],
                          'store': session.config.identity, 'target': release.target}
            if not official.is_official_id(m.id):
                raise StoreError('This publisher is not approved for automatic installation.')
            old = registry.records.get(m.id) if registry else None
            flags = cfg.get('plugins.enabled') or {}
            desired = flags.get(m.id)
            prepared.append({'archive': path, 'manifest': m, 'prefix': prefix,
                             'replacing': bool(old and not old.bundled), 'desired_enabled': True if m.id in needed or desired is None else bool(desired),
                             'provenance': provenance})
        # This is the only mutating boundary. A whole dependency set is one
        # durable transaction; publication is completed while the server is down.
        transaction = storage.prepare_batch(external_dir(), prepared)
        return {'ok': True, 'transaction': transaction['id'],
                'packages': [r.manifest.summary() for r in changes]}
