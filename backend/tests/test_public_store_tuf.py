"""Real signed metadata, HTTP downloads and cache replay; no mock verifier."""
import hashlib
import importlib.util
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from tuf.api.metadata import Metadata

from app.plugins.store.client import StoreConfig, StoreError, StoreSession
from app.plugins.store.catalog import parse_catalog, resolve
from public_store_fixtures import contract

pytest.importorskip('cryptography', reason='Signing proofs use the separate operator environment.')
spec = importlib.util.spec_from_file_location('lds_repository_tool', Path(__file__).resolve().parents[2] / 'store/tools/repository.py')
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture()
def repository(tmp_path, monkeypatch):
    public, keys = tmp_path / 'public', tmp_path / 'private'
    operator.initialize(public, keys)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(public)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f'http://127.0.0.1:{server.server_port}'
    config = StoreConfig(origin + '/metadata/', origin + '/targets/',
                         (public / 'bootstrap.root.json').read_bytes(), frozenset({'camera_angles', 'video'}))
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'client'))
    yield public, keys, config
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def catalog(version='1.0.0', **manifest_over):
    data = contract(version=version, **manifest_over)
    return {'schema_version': 1, 'products': [{'id': data['id'], 'releases': [{
        'manifest': data, 'manifest_sha256': hashlib.sha256(json.dumps(data).encode()).hexdigest(),
        'target': 'camera/' + version + '.ldsplugin', 'price': {'kind': 'free'}}]}]}


def publish(public, keys, version='1.0.0', data=b'package bytes'):
    value = catalog(version)
    operator.publish(public, keys, value, {'camera/' + version + '.ldsplugin': data})
    return value


def test_signed_catalog_download_update_and_key_rotation(repository):
    public, keys, config = repository
    publish(public, keys)
    with StoreSession(config) as session:
        value = session.catalog()
        parsed = parse_catalog(value, config)
        plan = resolve(parsed, 'camera_angles', {})
        path, _ = session.target(plan[0].target)
        assert path.read_bytes() == b'package bytes'
    operator.rotate(public, keys, 'targets')
    publish(public, keys, '2.0.0', b'updated')
    with StoreSession(config) as session:
        assert session.catalog()['products'][0]['releases'][0]['manifest']['version'] == '2.0.0'
        assert session.target('camera/2.0.0.ldsplugin')[0].read_bytes() == b'updated'


def test_tampered_archive_never_becomes_an_installable_file(repository):
    public, keys, config = repository
    publish(public, keys)
    path = next((public / 'targets' / 'camera').iterdir())
    path.write_bytes(b'altered bytes')
    with StoreSession(config) as session:
        with pytest.raises(StoreError, match='verification'):
            session.target('camera/1.0.0.ldsplugin')
        assert not (session.folder / 'targets' / hashlib.sha256(b'package bytes').hexdigest()).exists()


@pytest.mark.parametrize('kind', ['signature', 'expired', 'rollback'])
def test_bad_metadata_cannot_reuse_the_cached_catalog_for_install(repository, kind):
    public, keys, config = repository
    publish(public, keys)
    old = (public / 'metadata/timestamp.json').read_bytes()
    with StoreSession(config) as session:
        assert session.catalog()
    if kind == 'rollback':
        publish(public, keys, '2.0.0')
        with StoreSession(config) as session:
            assert session.catalog()
        (public / 'metadata/timestamp.json').write_bytes(old)
    else:
        metadata = Metadata.from_file(str(public / 'metadata/timestamp.json'))
        if kind == 'expired':
            metadata.signed.expires = datetime.now(timezone.utc) - timedelta(days=1)
            metadata.signed.version += 1
            metadata.sign(operator._key(keys, 'timestamp'))
        else:
            next(iter(metadata.signatures.values())).signature = '00' * 64
        (public / 'metadata/timestamp.json').write_bytes(metadata.to_bytes())
    with pytest.raises(StoreError, match='authenticated'):
        with StoreSession(config):
            pytest.fail('metadata was not verified')


def test_a_catalog_cannot_authorize_its_own_official_id(repository):
    public, keys, config = repository
    publish(public, keys)
    config = StoreConfig(config.metadata_url, config.target_url, config.root, frozenset())
    with StoreSession(config) as session:
        with pytest.raises(StoreError, match='invalid product'):
            parse_catalog(session.catalog(), config)


def test_published_archive_is_immutable(repository):
    public, keys, _ = repository
    publish(public, keys)
    before = (public / 'metadata/timestamp.json').read_bytes()
    with pytest.raises(ValueError, match='immutable'):
        publish(public, keys, data=b'changed same version')
    assert (public / 'metadata/timestamp.json').read_bytes() == before


def test_withdrawal_does_not_allow_replacing_an_old_release(repository):
    public, keys, config = repository
    publish(public, keys)
    operator.publish(public, keys, {'schema_version': 1, 'products': []}, {})
    with StoreSession(config) as session:
        assert session.catalog()['products'] == []
        with pytest.raises(StoreError, match='unavailable'):
            session.target('camera/1.0.0.ldsplugin')
    with pytest.raises(ValueError, match='immutable'):
        publish(public, keys, data=b'replacement')
    changed = catalog()
    changed['products'][0]['releases'][0]['target'] = 'renamed.ldsplugin'
    with pytest.raises(ValueError, match='immutable'):
        operator.publish(public, keys, changed, {'renamed.ldsplugin': b'package bytes'})
    publish(public, keys)
    with StoreSession(config) as session:
        assert session.target('camera/1.0.0.ldsplugin')[0].read_bytes() == b'package bytes'


def test_parallel_publications_get_distinct_complete_metadata_generations(repository):
    public, keys, config = repository
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda v: publish(public, keys, v), ['1.0.0', '2.0.0']))
    assert len(results) == 2
    generations = sorted(int(p.name.split('.')[0]) for p in (public / 'metadata').glob('*.targets.json'))
    assert generations == [1, 2, 3]
    with StoreSession(config) as session:
        data = session.catalog()
        release = data['products'][0]['releases'][0]
        assert session.target(release['target'])[0].read_bytes() == b'package bytes'


@pytest.mark.parametrize('point', ['versioned_targets', 'root_alias'])
def test_interrupted_publication_or_rotation_can_resume(repository, monkeypatch, point):
    public, keys, config = repository
    publish(public, keys)
    original = operator._atomic
    def interrupted(path, data, **kwargs):
        if (point == 'versioned_targets' and path.name == 'targets.json') or (point == 'root_alias' and path.name == 'root.json'):
            raise OSError('simulated operator interruption')
        return original(path, data, **kwargs)
    # Let rotation reach the versioned root; the lock first repairs the old alias.
    if point == 'root_alias':
        calls = 0
        def root_interrupted(path, data, **kwargs):
            nonlocal calls
            if path.name == 'root.json':
                calls += 1
                if calls == 2:
                    raise OSError('simulated operator interruption')
            return original(path, data, **kwargs)
        monkeypatch.setattr(operator, '_atomic', root_interrupted)
        with pytest.raises(OSError):
            operator.rotate(public, keys, 'targets')
    else:
        monkeypatch.setattr(operator, '_atomic', interrupted)
        with pytest.raises(OSError):
            publish(public, keys, '2.0.0')
    monkeypatch.setattr(operator, '_atomic', original)
    publish(public, keys, '2.0.0')
    with StoreSession(config) as session:
        assert session.catalog()['products'][0]['releases'][0]['manifest']['version'] == '2.0.0'


def test_tampered_cached_archive_is_verified_again(repository):
    public, keys, config = repository
    publish(public, keys)
    with StoreSession(config) as session:
        path, _ = session.target('camera/1.0.0.ldsplugin')
        path.write_bytes(b'local corruption')
    with StoreSession(config) as session:
        assert session.target('camera/1.0.0.ldsplugin')[0].read_bytes() == b'package bytes'
