"""Real signed package -> consent -> durable staging -> one isolated boot.

Only the loopback repository fixture is contacted. The downloaded code is a
neutral ping handler, never an LDS product or a provider credential.
"""
import hashlib
import io
import json
import sys
import zipfile

from flask import Flask
from flask_wtf import CSRFProtect
import pytest

from app import config as cfg
from app.extensions import db
from app.plugins import registry, storage
from app.plugins.loader import load_plugins
from app.plugins.store import service
from app.plugins.store.client import StoreError
from public_store_fixtures import contract
from test_public_store_tuf import operator, repository  # noqa: F401


@pytest.fixture
def acquisition(repository, monkeypatch, tmp_path):
    public, keys, config = repository
    monkeypatch.setattr(service, 'load_config', lambda: config)
    monkeypatch.setattr('app.plugins.store.client.load_config', lambda: config)
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / '.env'))
    monkeypatch.setenv('LDS_PLUGIN_DISTRIBUTION', 'store')
    monkeypatch.setenv('LDS_PLUGINS_DIR', str(tmp_path / 'installed'))
    monkeypatch.setenv('LDS_EXTENSIONS', '0')
    monkeypatch.delenv('LDS_PLUGINS', raising=False)
    monkeypatch.setattr(cfg, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.setattr(cfg, '_cache', None)
    monkeypatch.setattr(registry, '_ACTIVE', None)
    original_path = sys.path[:]
    yield public, keys, config, tmp_path
    sys.path[:] = original_path
    sys.modules.pop('lds_store_sample', None)


def publish_package(public, keys, version='1.0.0'):
    manifest = contract(version=version, python_package='lds_store_sample')
    manifest_bytes = json.dumps(manifest).encode()
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w') as archive:
        archive.writestr('plugin.json', manifest_bytes)
        archive.writestr('ui/index.js', '// synthetic UI')
        archive.writestr('ui/styles.css', '.sample { color: blue; }')
        archive.writestr('lds_store_sample/__init__.py', '''from flask import Blueprint
def register(ctx):
    bp = Blueprint('store_sample', __name__)
    bp.add_url_rule('/ping', 'ping', lambda: {'ready': True})
    ctx.register_blueprint(bp)
''')
    target = f'camera/{version}.ldsplugin'
    release = {'manifest': manifest, 'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
               'target': target, 'price': {'kind': 'free'}}
    catalog = {'schema_version': 1, 'products': [{'id': 'camera_angles', 'releases': [release]}]}
    operator.publish(public, keys, catalog, {target: content.getvalue()})


def test_signed_acquisition_does_not_import_until_boot_and_preserves_plugin_data(acquisition):
    public, keys, _config, root = acquisition
    publish_package(public, keys)
    data = storage.data_dir('camera_angles')
    data.mkdir(parents=True)
    (data / 'saved').write_bytes(b'keep')
    plan = service.preview_plan(None, 'camera_angles')
    assert [p['manifest']['id'] for p in plan['packages']] == ['camera_angles']
    assert 'lds_store_sample' not in sys.modules
    result = service.prepare(None, 'camera_angles', None, plan['plan_id'])
    assert result['ok'] is True
    pending, errors = storage.pending(root / 'installed')
    assert set(pending) == {'camera_angles'} and errors == []
    assert 'lds_store_sample' not in sys.modules
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', WTF_CSRF_ENABLED=False)
    db.init_app(app)
    csrf = CSRFProtect(app)
    with app.app_context():
        db.create_all()
        try:
            loaded = load_plugins(app, csrf)
            record = loaded.records['camera_angles']
            assert record.state == 'loaded', record.error
            assert record.manifest.official is True
            assert app.test_client().get('/api/plugins/camera_angles/ping').get_json() == {'ready': True}
        finally:
            db.session.remove()
            db.drop_all()
    assert (data / 'saved').read_bytes() == b'keep'


def test_catalog_change_invalidates_the_reviewed_installation_plan(acquisition):
    public, keys, _config, root = acquisition
    publish_package(public, keys)
    plan = service.preview_plan(None, 'camera_angles')
    publish_package(public, keys, '2.0.0')
    with pytest.raises(StoreError, match='changed'):
        service.prepare(None, 'camera_angles', None, plan['plan_id'])
    assert storage.pending(root / 'installed') == ({}, [])
    assert 'lds_store_sample' not in sys.modules


def test_tampered_download_cannot_reach_staging(acquisition):
    public, keys, _config, root = acquisition
    publish_package(public, keys)
    plan = service.preview_plan(None, 'camera_angles')
    path = next((public / 'targets' / 'camera').iterdir())
    path.write_bytes(b'tampered')
    with pytest.raises(StoreError, match='verification'):
        service.prepare(None, 'camera_angles', None, plan['plan_id'])
    assert storage.pending(root / 'installed') == ({}, [])
    assert 'lds_store_sample' not in sys.modules
