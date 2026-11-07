"""New first-party products do not invalidate the catalog used by older hosts."""
import json
from dataclasses import replace

import pytest
from tuf.api.metadata import Metadata, MetaFile, Snapshot, TargetFile, Timestamp

from app.plugins.store.catalog import parse_catalog
from app.plugins.store.client import StoreError, StoreSession
from test_public_store_tuf import catalog, operator, publish, repository  # noqa: F401


def _add_signed_catalog(public, keys, data):
    name = 'catalog-v2-extra.json'
    content = json.dumps(data).encode()
    info = TargetFile.from_data(name, content, ['sha256'])
    path = public / 'targets' / (info.hashes['sha256'] + '.' + name)
    path.write_bytes(content)
    targets = Metadata.from_file(str(public / 'metadata/targets.json'))
    targets.signed.targets[name] = info
    targets.signed.version += 1
    version = targets.signed.version
    targets.sign(operator._current_key(public, keys, 'targets'))
    snapshot = Metadata(Snapshot(version=version, expires=operator._expiry(7),
                                 meta={'targets.json': MetaFile.from_data(version, targets.to_bytes(), ['sha256'])}))
    snapshot.sign(operator._current_key(public, keys, 'snapshot'))
    timestamp = Metadata(Timestamp(version=version, expires=operator._expiry(1),
                                   snapshot_meta=MetaFile.from_data(version, snapshot.to_bytes(), ['sha256'])))
    timestamp.sign(operator._current_key(public, keys, 'timestamp'))
    for role, value in [('targets', targets), ('snapshot', snapshot), ('timestamp', timestamp)]:
        for filename in (f'{version}.{role}.json', f'{role}.json'):
            (public / 'metadata' / filename).write_bytes(value.to_bytes())
    return path


def test_old_and_new_hosts_read_their_own_authorized_catalogs(repository):
    public, keys, old = repository
    publish(public, keys)
    extra = catalog()
    extra['products'][0]['id'] = 'qwen_dataset'
    extra['products'][0]['releases'][0]['manifest']['id'] = 'qwen_dataset'
    _add_signed_catalog(public, keys, extra)
    with StoreSession(old) as session:
        assert set(parse_catalog(session.catalog(), old)) == {'camera_angles'}
    current = replace(old, official_ids=old.official_ids | {'qwen_dataset'},
                      additional_catalog_targets=('catalog-v2-extra.json',))
    with StoreSession(current) as session:
        assert set(parse_catalog(session.catalog(), current)) == {'camera_angles', 'qwen_dataset'}


@pytest.mark.parametrize('failure', ['tampered', 'unsigned', 'duplicate'])
def test_additional_catalog_cannot_bypass_signatures_or_product_validation(repository, failure):
    public, keys, config = repository
    publish(public, keys)
    extra = catalog() if failure == 'duplicate' else {'schema_version': 1, 'products': []}
    path = _add_signed_catalog(public, keys, extra)
    if failure == 'tampered':
        path.write_bytes(b'{}')
    target = 'catalog-unsigned.json' if failure == 'unsigned' else 'catalog-v2-extra.json'
    config = replace(config, additional_catalog_targets=(target,))
    with StoreSession(config) as session, pytest.raises(StoreError):
        parse_catalog(session.catalog(), config)


@pytest.mark.parametrize('value', ['catalog.json', ['../catalog.json'], ['https://example.org/catalog.json'],
                                  ['catalog-v2-extra.json', 'catalog-v2-extra.json']])
def test_additional_catalog_targets_are_local_operator_configuration(repository, value):
    with pytest.raises(StoreError):
        replace(repository[2], additional_catalog_targets=value)
