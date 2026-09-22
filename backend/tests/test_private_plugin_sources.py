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
from app.plugins import storage
from app.plugins.loader import load_plugins
from app.plugins.manifest import parse_manifest
from app.plugins.store import client, service
from app.plugins.store.catalog import parse_catalog
from app.plugins.store.client import StoreError
from public_store_fixtures import contract
from test_public_store_service import acquisition, publish_package  # noqa: F401
from test_public_store_tuf import QuietHandler, operator, repository  # noqa: F401

PID = 'studio.depth'


def external_package(version):
    manifest = contract(id=PID, name='Depth', version=version,
                        publisher={'id': 'studio', 'name': 'Studio'})
    raw = json.dumps(manifest).encode()
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w') as archive:
        archive.writestr('plugin.json', raw)
        archive.writestr('ui/index.js', '// synthetic plugin')
        archive.writestr('ui/styles.css', '/* synthetic styles */')
    target = f'{PID}/{version}.ldsplugin'
    release = {'manifest': manifest, 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
               'target': target, 'price': {'kind': 'free'}}
    return {'schema_version': 1, 'products': [{'id': PID, 'releases': [release]}]}, {target: content.getvalue()}


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
    catalog, artifacts = external_package('1.0.1')
    operator.publish(private, keys, catalog, artifacts)
    yield SimpleNamespace(root=root, private=private, keys=keys, config=config,
                          source=source, path=path, catalog=catalog)
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_private_update_uses_normal_transaction_and_keeps_public_catalog(private_source):
    source = private_source
    old_catalog, old_archives = external_package('1.0.0')
    folder = source.root / 'installed' / PID
    folder.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(next(iter(old_archives.values())))) as archive:
        archive.extractall(folder)
    manifest = parse_manifest(old_catalog['products'][0]['releases'][0]['manifest'], folder)
    records = SimpleNamespace(records={PID: SimpleNamespace(manifest=manifest, legacy=None, state='loaded', bundled=False)})
    data = storage.data_dir(PID)
    data.mkdir(parents=True)
    (data / 'history').write_bytes(b'keep history')
    catalog = service.browse()
    assert catalog['status'] == 'ready'
    assert {p['id'] for p in catalog['products']} == {'camera_angles', PID}
    plan = service.preview_plan(records, PID)
    assert [(p['manifest']['id'], p['previous_version'], p['manifest']['version'])
            for p in plan['packages']] == [(PID, '1.0.0', '1.0.1')]
    assert service.prepare(records, PID, None, plan['plan_id'])['ok']
    pending, errors = storage.pending(source.root / 'installed')
    assert set(pending) == {PID} and errors == []
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', WTF_CSRF_ENABLED=False)
    db.init_app(app)
    csrf = CSRFProtect(app)
    with app.app_context():
        db.create_all()
        try:
            loaded = load_plugins(app, csrf)
            assert loaded.records[PID].state == 'loaded', loaded.records[PID].error
            assert loaded.records[PID].manifest.version == '1.0.1'
            assert not loaded.records[PID].manifest.official
        finally:
            db.session.remove()
            db.drop_all()
    assert (data / 'history').read_bytes() == b'keep history'


def test_private_source_cannot_grant_first_party_or_unlisted_plugin_rights(private_source):
    source = private_source
    config = client.load_private_configs()[0]
    assert config.official_ids == frozenset()
    with pytest.raises(StoreError):
        parse_catalog(source.catalog, source.config)
    unknown = json.loads(json.dumps(source.catalog))
    unknown['products'][0]['id'] = 'studio.other'
    assert parse_catalog(unknown, config) == {}
    source.source['plugin_ids'] = ['camera_angles']
    source.path.write_text(json.dumps({'sources': [source.source]}), encoding='utf-8')
    with pytest.raises(StoreError, match='configuration'):
        client.load_private_configs()


def test_duplicate_sources_and_mixed_source_transactions_are_refused(private_source):
    source = private_source
    with pytest.raises(StoreError, match='separately'):
        service.preview_plan(None, ['camera_angles', PID])
    assert storage.pending(source.root / 'installed') == ({}, [])
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
