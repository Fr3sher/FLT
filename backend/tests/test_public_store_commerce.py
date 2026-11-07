"""No merchant calls: exercise credential storage, transport and TUF-bound grants."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from flask import Blueprint, Flask, jsonify
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
import pytest
import requests

from app.plugins.store import commerce as commerce

SECRET = 's' * 43
CLIENT_ID = 'a' * 32
CONFIG = {'service_url': 'https://commerce.example.test', 'checkout_origin': 'https://checkout.example.test'}
ITEM = {'plugin_id': 'video', 'status': 'active', 'acquisition': 'all_published',
        'updates': 'included', 'offline': 'installed_continues', 'valid_until': None}


class Response:
    def __init__(self, body, status=200):
        self.body = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
        self.status_code = status
        self.closed = False
    def iter_content(self, chunk_size):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset:offset + chunk_size]
    def close(self):
        self.closed = True


@pytest.fixture
def remote(tmp_path, monkeypatch):
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setattr(commerce, 'load_commerce_config', lambda: CONFIG)
    replies, calls = [], []
    class Session:
        trust_env = True
        def request(self, method, url, **options):
            assert self.trust_env is False
            calls.append((method, url, options))
            assert options['allow_redirects'] is False
            assert options['stream'] is True
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        def close(self):
            pass
    monkeypatch.setattr(commerce.requests, 'Session', Session)
    return replies, calls


def connected(remote):
    remote[0].append(Response({'client_id': CLIENT_ID, 'client_secret': SECRET}, 201))
    client = commerce.CommerceClient()
    assert client.credential(enroll=True) == CLIENT_ID + '.' + SECRET
    return client


def artifact():
    content = b'authentic plugin archive bytes'
    release = SimpleNamespace(target='packages/video-1.ldsplugin', manifest=SimpleNamespace(id='video', version='1.0.0'))
    info = SimpleNamespace(path=release.target, length=len(content), hashes={'sha256': hashlib.sha256(content).hexdigest()})
    grant = {'token': 'g' * 43, 'target': release.target, 'sha256': info.hashes['sha256'],
             'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
             'download_url': CONFIG['service_url'] + '/v1/artifacts/' + release.target}
    return release, info, grant, content


def test_enrollment_is_persistent_origin_scoped_and_not_in_library(remote):
    client = connected(remote)
    remote[0].append(Response({'items': [{**ITEM, 'client_secret': SECRET}]}))
    value = client.library()
    assert value['items'] == [ITEM]
    assert SECRET not in json.dumps(value)
    assert client.credential() == CLIENT_ID + '.' + SECRET
    assert len(remote[1]) == 2
    assert remote[1][-1][2]['headers']['Authorization'] == 'Bearer ' + CLIENT_ID + '.' + SECRET
    saved = client.folder / 'installation.json'
    if commerce.os.name == 'nt':
        assert SECRET.encode() not in saved.read_bytes()  # Actual DPAPI roundtrip on Windows.
    else:
        assert saved.stat().st_mode & 0o077 == 0
    other = commerce.CommerceClient({**CONFIG, 'service_url': 'https://other.example.test'})
    assert other.credential() is None


def test_library_read_does_not_silently_enroll(remote):
    assert commerce.CommerceClient().library()['status'] == 'not_connected'
    assert not remote[1]


def test_activation_key_is_sent_only_to_service_and_not_saved(remote):
    client = connected(remote)
    remote[0].append(Response(ITEM))
    key = 'test-license-not-a-real-key'
    assert client.activate('video', key) == ITEM
    assert remote[1][-1][2]['json'] == {'plugin_id': 'video', 'license_key': key}
    assert all(key.encode() not in path.read_bytes() for path in client.folder.iterdir() if path.is_file())


@pytest.mark.parametrize('url', ['http://example.test', 'https://user:pass@example.test', 'https://example.test/path',
                               'https://example.test?token=foo', 'https://example.test:0', 'http://localhost',
                               'https://example.test\\evil', None])
def test_transport_origin_rejects_unsafe_configuration(url):
    with pytest.raises(commerce.StoreError):
        commerce._origin(url)


def test_loopback_http_is_explicitly_supported_for_tests():
    assert commerce._origin('http://127.0.0.1:8989') == 'http://127.0.0.1:8989'


@pytest.mark.parametrize('reply', [Response({'client_id': CLIENT_ID, 'client_secret': SECRET}, 302),
                                  Response({'client_id': CLIENT_ID, 'client_secret': SECRET, 'padding': 'x' * commerce.MAX_RESPONSE}),
                                  requests.RequestException('must-not-echo-password')])
def test_redirects_oversize_and_network_errors_are_sanitized(remote, reply):
    remote[0].append(reply)
    with pytest.raises(commerce.StoreError) as error:
        commerce.CommerceClient().credential(enroll=True)
    assert 'must-not-echo-password' not in str(error.value)
    assert len(remote[1]) == 1


def test_corrupted_local_credential_is_not_replaced_with_new_identity(remote):
    client = connected(remote)
    (client.folder / 'installation.json').write_text('{"protection":"invalid"}')
    with pytest.raises(commerce.StoreError, match='not replaced'):
        client.credential(enroll=True)
    assert len(remote[1]) == 1


def test_checkout_is_confined_to_operator_payment_origin(remote):
    client = connected(remote)
    remote[0].append(Response({'hosted_checkout': 'https://checkout.example.test/buy/123?checkout=abc', 'intent_id': 'i'}))
    assert client.checkout('video') == {'hosted_checkout': 'https://checkout.example.test/buy/123?checkout=abc'}
    remote[0].append(Response({'hosted_checkout': 'https://attacker.example.test/pay'}))
    with pytest.raises(commerce.StoreError):
        client.checkout('video')


def test_download_uses_both_headers_and_matches_tuf_bytes(remote, tmp_path):
    client = connected(remote)
    release, info, grant, content = artifact()
    remote[0].extend([Response(grant), Response(content)])
    destination = tmp_path / 'verified.ldsplugin'
    assert client.download(release, info, destination).read_bytes() == content
    headers = remote[1][-1][2]['headers']
    assert headers['Authorization'] == 'Bearer ' + CLIENT_ID + '.' + SECRET
    assert headers['X-LDS-Download-Grant'] == grant['token']
    assert remote[1][-1][1] == grant['download_url']


@pytest.mark.parametrize('field,value', [('download_url', 'https://attacker.example.test/payload'),
                                      ('target', 'packages/other.ldsplugin'), ('sha256', '0' * 64),
                                      ('expires_at', '2000-01-01T00:00:00Z')])
def test_grant_cannot_redirect_or_substitute_release(remote, tmp_path, field, value):
    client = connected(remote)
    release, info, grant, _ = artifact()
    grant[field] = value
    remote[0].append(Response(grant))
    with pytest.raises(commerce.StoreError):
        client.download(release, info, tmp_path / 'result')
    assert len(remote[1]) == 2  # Registration, grant, no artifact request.


@pytest.mark.parametrize('content', [b'changed plugin archive bytes!!', b'too short', b'x' * 100])
def test_bad_artifact_keeps_previous_cache_and_cleans_partial(remote, tmp_path, content):
    client = connected(remote)
    release, info, grant, _ = artifact()
    remote[0].extend([Response(grant), Response(content)])
    destination = tmp_path / 'previous.ldsplugin'
    destination.write_bytes(b'previous cache')
    with pytest.raises(commerce.StoreError):
        client.download(release, info, destination)
    assert destination.read_bytes() == b'previous cache'
    assert not list(tmp_path.glob('.commerce-*'))


def test_routes_require_admin_and_csrf_and_never_return_credentials(remote):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY='test-session-signing-only')
    CSRFProtect(app)
    bp = Blueprint('commerce_test', __name__, url_prefix='/api/plugins/store')
    commerce.register_commerce_routes(bp)
    app.register_blueprint(bp)
    app.add_url_rule('/csrf', view_func=lambda: jsonify(token=generate_csrf()))
    client = app.test_client()
    remote[0].append(Response({'client_id': CLIENT_ID, 'client_secret': SECRET}, 201))
    assert client.post('/api/plugins/store/commerce/connect', json={}).status_code == 400
    token = client.get('/csrf').json['token']
    assert client.get('/api/plugins/store/commerce/library', environ_base={'REMOTE_ADDR': '198.51.100.8'}).status_code == 403
    response = client.post('/api/plugins/store/commerce/connect', json={}, headers={'X-CSRFToken': token})
    assert response.status_code == 200 and response.json == {'ok': True}
    assert SECRET not in response.get_data(as_text=True)
    assert response.headers['Cache-Control'] == 'no-store'
