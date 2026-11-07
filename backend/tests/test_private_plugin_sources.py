"""Private signed updates alongside the public catalog, using disposable servers."""
import hashlib
import io
import json
import threading
import zipfile
from functools import partial
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from flask import Flask
from flask_wtf import CSRFProtect
import pytest

from app import config as cfg
from app.extensions import db
from app.plugins import official, storage
from app.plugins.loader import load_plugins
from app.plugins.manifest import parse_manifest
from app.plugins.store import client, service
from app.plugins.store.catalog import parse_catalog
from app.plugins.store.client import StoreError
from public_store_fixtures import contract
from test_public_store_service import acquisition, publish_package  # noqa: F401
from test_public_store_tuf import QuietHandler, operator, repository  # noqa: F401

PID = 'studio.depth'


def package(version, plugin_id=PID):
    publisher = {'id': 'studio', 'name': 'Studio'} if '.' in plugin_id else {'id': 'lds', 'name': 'LDS'}
    manifest = contract(id=plugin_id, name='Synthetic product', version=version, publisher=publisher)
    raw = json.dumps(manifest).encode()
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w') as archive:
        archive.writestr('plugin.json', raw)
        archive.writestr('ui/index.js', '// synthetic plugin')
        archive.writestr('ui/styles.css', '/* synthetic styles */')
    target = f'{plugin_id}/{version}.ldsplugin'
    release = {'manifest': manifest, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
               'target': target, 'price': {'kind': 'free'}}
    return {'schema_version': 1, 'products': [{'id': plugin_id, 'releases': [release]}]}, {target: content.getvalue()}


@pytest.fixture
def private_source(acquisition):
    public, public_keys, config, root = acquisition
    publish_package(public, public_keys)
    private, keys = root / 'private-catalog', root / 'private-keys'
    operator.initialize(private, keys)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(private)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    folder = cfg.data_dir() / 'plugin-store'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'private-root.json').write_bytes((private / 'bootstrap.root.json').read_bytes())
    source = {'metadata_url': f'http://127.0.0.1:{server.server_port}/metadata/',
              'target_url': f'http://127.0.0.1:{server.server_port}/targets/',
              'root_path': 'private-root.json', 'plugin_ids': [PID]}
    path = folder / 'sources.json'
    path.write_text(json.dumps({'sources': [source]}), encoding='utf-8')
    catalog, artifacts = package('1.0.1')
    operator.publish(private, keys, catalog, artifacts)
    yield SimpleNamespace(root=root, private=private, keys=keys, config=config,
                          source=source, path=path, catalog=catalog)
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def authorize_official_product(source):
    source.source.update(plugin_ids=[PID, 'manga'], official_ids=['manga'])
    source.path.write_text(json.dumps({'sources': [source.source]}), encoding='utf-8')
    artifacts = {}
    # Only neutral fixture bytes: no implementation of these historic products.
    for plugin_id in ('manga', 'creature_battle', 'camera_angles'):
        catalog, archive = package('1.0.1', plugin_id)
        source.catalog['products'].extend(catalog['products'])
        artifacts.update(archive)
    operator.publish(source.private, source.keys, source.catalog, artifacts)


@pytest.mark.parametrize('include_official', [False, True], ids=['external', 'explicit-first-party'])
def test_private_update_uses_normal_transaction_and_keeps_public_catalog(private_source, include_official):
    source = private_source
    plugin_ids = [PID, 'manga'] if include_official else [PID]
    if include_official:
        authorize_official_product(source)
    config = client.load_private_configs()[0]
    assert config.external_ids == frozenset({PID})
    assert config.official_ids == frozenset({'manga'} if include_official else set())
    assert config.scoped_ids == frozenset(plugin_ids)
    assert config.root != source.config.root
    records = SimpleNamespace(records={})
    for plugin_id in plugin_ids:
        old_catalog, old_archives = package('1.0.0', plugin_id)
        folder = source.root / 'installed' / plugin_id
        folder.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(next(iter(old_archives.values())))) as archive:
            archive.extractall(folder)
        manifest = parse_manifest(old_catalog['products'][0]['releases'][0]['manifest'], folder,
                                  official=plugin_id == 'manga')
        if manifest.official:
            official.record_install(plugin_id, folder, {
                'id': plugin_id, 'publisher': 'lds', 'source': 'legacy_migration',
                'manifest_sha256': official.manifest_digest(folder),
            })
        records.records[plugin_id] = SimpleNamespace(manifest=manifest, legacy=None, state='loaded', bundled=False)
        data = storage.data_dir(plugin_id)
        data.mkdir(parents=True)
        (data / 'history').write_bytes(b'keep history')
    catalog = service.browse()
    assert catalog['status'] == 'ready'
    assert {p['id'] for p in catalog['products']} == {'camera_angles', *plugin_ids}
    assert len(catalog['products']) == len(plugin_ids) + 1
    public = next(p for p in catalog['products'] if p['id'] == 'camera_angles')
    assert [r['manifest']['version'] for r in public['releases']] == ['1.0.0']
    assert service.preview_plan(None, 'camera_angles')['packages'][0]['manifest']['version'] == '1.0.0'
    selection = plugin_ids if include_official else PID
    plan = service.preview_plan(records, selection)
    assert {(p['manifest']['id'], p['previous_version'], p['manifest']['version'])
            for p in plan['packages']} == {(pid, '1.0.0', '1.0.1') for pid in plugin_ids}
    assert service.prepare(records, selection, None, plan['plan_id'])['ok']
    pending, errors = storage.pending(source.root / 'installed')
    assert set(pending) == set(plugin_ids) and errors == []
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', WTF_CSRF_ENABLED=False)
    db.init_app(app)
    csrf = CSRFProtect(app)
    with app.app_context():
        db.create_all()
        try:
            loaded = load_plugins(app, csrf)
            for plugin_id in plugin_ids:
                record = loaded.records[plugin_id]
                assert record.state == 'loaded', record.error
                assert record.manifest.version == '1.0.1'
                assert record.manifest.official is (plugin_id == 'manga')
            assert storage.pending(source.root / 'installed') == ({}, [])
        finally:
            db.session.remove()
            db.drop_all()
    for plugin_id in plugin_ids:
        assert (storage.data_dir(plugin_id) / 'history').read_bytes() == b'keep history'
    receipts = cfg.data_dir() / 'plugin-store' / 'installed'
    assert {p.stem for p in receipts.glob('*.json')} == ({'manga'} if include_official else set())
    if include_official:
        provenance = official.installed_provenance('manga', source.root / 'installed' / 'manga')
        assert provenance['source'] == 'verified_store'
        assert provenance['store'] == config.identity
        assert provenance['target'] == 'manga/1.0.1.ldsplugin'


def test_external_only_private_source_cannot_grant_first_party_or_unlisted_plugin_rights(private_source):
    source = private_source
    config = client.load_private_configs()[0]
    assert config.official_ids == frozenset()
    with pytest.raises(StoreError):
        parse_catalog(source.catalog, source.config)
    unknown = json.loads(json.dumps(source.catalog))
    unknown['products'][0]['id'] = 'studio.other'
    assert parse_catalog(unknown, config) == {}
    first_party, _ = package('1.0.1', 'manga')
    assert parse_catalog(first_party, config) == {}


@pytest.mark.parametrize('failure', [None, 'tampered', 'consent_mode'])
@pytest.mark.parametrize('private_enabled', [False, True])
def test_update_all_combines_sources_atomically_and_keeps_disabled_plugins(private_source, failure, private_enabled):
    source = private_source
    records = SimpleNamespace(records={})
    for plugin_id in ('camera_angles', PID):
        old_catalog, archives = package('0.9.0', plugin_id)
        folder = source.root / 'installed' / plugin_id
        folder.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(next(iter(archives.values())))) as archive:
            archive.extractall(folder)
        manifest = parse_manifest(old_catalog['products'][0]['releases'][0]['manifest'], folder,
                                  official=plugin_id == 'camera_angles')
        if manifest.official:
            official.record_install(plugin_id, folder, {
                'id': plugin_id, 'publisher': 'lds', 'source': 'legacy_migration',
                'manifest_sha256': official.manifest_digest(folder),
            })
        records.records[plugin_id] = SimpleNamespace(manifest=manifest, legacy=None, bundled=False,
                                                     state='disabled' if plugin_id == PID else 'loaded')
    # An enabled plugin that failed to load still keeps its desired activation.
    # An absent flag means enabled, just like the lifecycle API.
    cfg.save_config({'plugins': {'enabled': {} if private_enabled else {PID: False}}})
    ids = ['camera_angles', PID]
    plan = service.preview_plan(records, ids, update_only=True)
    assert len(plan['packages']) == 2
    private_plan = next(p for p in plan['packages'] if p['manifest']['id'] == PID)
    assert private_plan['remains_disabled'] is not private_enabled
    assert private_plan['will_enable'] is private_enabled
    if failure == 'tampered':
        next((source.private / 'targets' / PID).rglob('*.ldsplugin')).write_bytes(b'tampered')
    if failure:
        with pytest.raises(StoreError):
            service.prepare(records, ids, None, plan['plan_id'], update_only=failure != 'consent_mode')
        assert storage.pending(source.root / 'installed') == ({}, [])
    else:
        result = service.prepare(records, ids, None, plan['plan_id'], update_only=True)
        pending, errors = storage.pending(source.root / 'installed')
        assert result['ok'] and not errors and set(pending) == set(ids)
        assert pending[PID]['desired_enabled'] is private_enabled
        assert pending['camera_angles']['desired_enabled']
        assert pending['camera_angles']['provenance']['store'] == source.config.identity
        assert len(storage.transaction_history(source.root / 'installed')) == 1


def test_first_party_only_source_filters_catalog_and_has_its_own_scope_identity(private_source):
    source = private_source
    external_config = client.load_private_configs()[0]
    authorize_official_product(source)
    source.source['plugin_ids'] = ['manga']
    source.path.write_text(json.dumps({'sources': [source.source]}), encoding='utf-8')
    config = client.load_private_configs()[0]
    assert config.external_ids == frozenset()
    assert config.scoped_ids == config.official_ids == frozenset({'manga'})
    assert config.identity != external_config.identity
    assert client.config_for_plugins('manga') == config
    assert client.config_for_plugins(PID) is None
    assert set(parse_catalog(source.catalog, config)) == {'manga'}
    assert {p['id'] for p in service.browse()['products']} == {'camera_angles', 'manga'}
    plan = service.preview_plan(None, 'manga')
    assert [(p['manifest']['id'], p['manifest']['official']) for p in plan['packages']] == [('manga', True)]


def test_first_party_field_preserves_external_updates_and_canonical_permissions(private_source):
    source = private_source
    authorize_official_product(source)
    expected = client.load_private_configs()[0]
    expected_plan = service.preview_plan(None, [PID, 'manga'])
    source.source.pop('official_ids')
    source.source.update(plugin_ids=[PID], first_party_ids=['manga'])
    source.path.write_text(json.dumps({'sources': [source.source]}), encoding='utf-8')
    config = client.load_private_configs()[0]
    assert config == expected
    assert config.identity == expected.identity
    assert config.external_ids == frozenset({PID})
    for plugin_id in (PID, 'manga'):
        assert client.config_for_plugins(plugin_id) == expected
    assert parse_catalog(source.catalog, config) == parse_catalog(source.catalog, expected)
    assert {p['id'] for p in service.browse()['products']} == {'camera_angles', PID, 'manga'}
    assert service.preview_plan(None, [PID, 'manga']) == expected_plan


@pytest.mark.parametrize('permissions', [
    {'first_party_ids': 'manga'},
    {'first_party_ids': [PID]},
    {'first_party_ids': ['unreviewed']},
    {'first_party_ids': ['camera_angles']},
    {'first_party_ids': ['manga'], 'official_ids': ['manga']},
    {'first_party_ids': ['manga'], 'plugin_ids': ['creature_battle']},
], ids=['not-a-list', 'external-id', 'unknown-id', 'primary-takeover',
        'ambiguous-permissions', 'nonexternal-base-scope'])
def test_first_party_field_rejects_invalid_or_ambiguous_permissions(private_source, permissions):
    source = private_source
    source.source.update(permissions)
    source.path.write_text(json.dumps({'sources': [source.source]}), encoding='utf-8')
    with pytest.raises(StoreError, match='configuration'):
        client.load_private_configs()


@pytest.mark.parametrize('permissions', [
    {'plugin_ids': ['manga']},
    {'plugin_ids': ['camera_angles'], 'official_ids': ['camera_angles']},
    {'plugin_ids': [PID], 'official_ids': ['manga']},
    {'plugin_ids': ['manga'], 'official_ids': ['video']},
    {'plugin_ids': ['manga', 'manga'], 'official_ids': ['manga']},
    {'plugin_ids': ['manga'], 'official_ids': ['manga', 'manga']},
    {'plugin_ids': [PID], 'official_ids': [PID]},
    {'plugin_ids': ['unreviewed'], 'official_ids': ['unreviewed']},
], ids=['implicit', 'primary-takeover', 'out-of-scope', 'wrong-official-id',
        'duplicate-scope', 'duplicate-permission', 'external-as-official', 'unknown-official'])
def test_private_official_permissions_must_match_exact_non_public_scope(private_source, permissions):
    source = private_source
    source.source.update(permissions)
    source.path.write_text(json.dumps({'sources': [source.source]}), encoding='utf-8')
    with pytest.raises(StoreError, match='configuration'):
        client.load_private_configs()


def test_duplicate_sources_are_refused(private_source):
    source = private_source
    source.path.write_text(json.dumps({'sources': [source.source, source.source]}), encoding='utf-8')
    with pytest.raises(StoreError, match='configuration'):
        client.load_private_configs()


def test_failed_private_signature_keeps_public_updates_and_refuses_private_install(private_source):
    source = private_source
    assert service.browse()['status'] == 'ready'
    plan = service.preview_plan(None, PID)
    (source.private / 'metadata/timestamp.json').write_bytes(b'bad signature')
    assert service.browse()['status'] == 'ready'
    assert service.preview_plan(None, 'camera_angles')['packages'][0]['manifest']['id'] == 'camera_angles'
    with pytest.raises(StoreError, match='authenticated'):
        service.prepare(None, PID, None, plan['plan_id'])
    assert storage.pending(source.root / 'installed') == ({}, [])


def test_failed_public_catalog_keeps_private_updates(private_source, monkeypatch):
    def unavailable():
        raise StoreError('Public catalog is unavailable.')
    monkeypatch.setattr(service, 'load_config', unavailable)
    catalog = service.browse()
    assert catalog['status'] == 'ready'
    assert [p['id'] for p in catalog['products']] == [PID]
    assert service.preview_plan(None, PID)['packages'][0]['manifest']['version'] == '1.0.1'


def test_tampered_private_archive_cannot_reach_staging(private_source):
    source = private_source
    plan = service.preview_plan(None, PID)
    next((source.private / 'targets' / PID).iterdir()).write_bytes(b'tampered archive')
    with pytest.raises(StoreError, match='verification'):
        service.prepare(None, PID, None, plan['plan_id'])
    assert storage.pending(source.root / 'installed') == ({}, [])
