"""TUF transport refuses origin changes before requests can expose any state."""
from contextlib import contextmanager
import io

import pytest
import requests
from tuf.api.exceptions import DownloadHTTPError

from app.plugins.store.client import StoreConfig, StoreError, _Fetcher


def configuration(**changes):
    return StoreConfig(**{'metadata_url': 'https://store.example/metadata/',
                          'target_url': 'https://cdn.example/targets/',
                          'root': b'root', 'official_ids': frozenset(), **changes})


@pytest.mark.parametrize('url', [
    'http://store.example/metadata/', 'http://localhost/metadata/',
    'https://user:password@store.example/', 'https://store.example:99999/',
    'https://[broken/', 'https://store.example/%2e%2e/',
    'https://store.example/../private/', 'https://store.example/\\private/',
    'https://store.example/?token=hidden', 'https://store.example/#fragment',
])
def test_configuration_constructor_applies_operator_url_rules(url):
    with pytest.raises(StoreError):
        configuration(metadata_url=url)


@pytest.mark.parametrize('url', [
    'https://store.example.attacker/metadata/1.root.json',
    'https://store.example/elsewhere/1.root.json',
    'https://cdn.example/targets/../private/key',
    'https://cdn.example/targets/%2e%2e/private/key',
    'https://cdn.example/targets/item?token=secret',
])
def test_download_refuses_escaped_origin_and_nonportable_paths_before_network(monkeypatch, url):
    def forbidden(*args, **kwargs):
        pytest.fail('network was reached for an invalid download URL')
    monkeypatch.setattr(requests.Session, 'send', forbidden)
    with pytest.raises(StoreError):
        list(_Fetcher(configuration())._fetch(url))


def test_redirect_is_not_followed_and_public_fetcher_sends_no_credential(monkeypatch):
    calls = []

    class Response:
        status_code = 302

        def iter_content(self, **kwargs):
            pytest.fail('redirect response body was accepted')

    @contextmanager
    def get(self, url, **kwargs):
        calls.append((url, kwargs))
        yield Response()

    monkeypatch.setattr(requests.Session, 'get', get)
    with pytest.raises(DownloadHTTPError):
        list(_Fetcher(configuration())._fetch('https://cdn.example/targets/item'))
    assert len(calls) == 1
    assert calls[0][1]['allow_redirects'] is False
    assert not any(key.lower() in {'authorization', 'cookie', 'x-lds-download-grant'}
                   for key in calls[0][1]['headers'])


def test_only_literal_loopback_can_use_http():
    assert configuration(metadata_url='http://127.0.0.1:5191/meta').metadata_url.endswith('/meta/')
    assert configuration(metadata_url='http://[::1]:5191/meta').metadata_url.endswith('/meta/')


@pytest.mark.parametrize('changes', [{'root': b''}, {'root': 'root'},
                                     {'root': b'x' * 512001}, {'official_ids': {'other.product'}}])
def test_direct_configuration_cannot_skip_trust_bounds(changes):
    with pytest.raises(StoreError):
        configuration(**changes)


@pytest.mark.parametrize('url', ['https://store.example/metadata/root.json',
                                 'https://cdn.example/targets/item'])
def test_prepared_public_request_carries_no_ambient_credentials_or_proxy(monkeypatch, tmp_path, url):
    netrc = tmp_path / 'netrc'
    netrc.write_text('default login synthetic-user password synthetic-password\n', encoding='ascii')
    monkeypatch.setenv('NETRC', str(netrc))
    monkeypatch.setenv('HTTPS_PROXY', 'http://proxy.invalid:8080')
    monkeypatch.setenv('REQUESTS_CA_BUNDLE', str(tmp_path / 'unused-ca.pem'))
    observed = []

    def send(session, prepared, **options):
        observed.append((prepared, options))
        response = requests.Response()
        response.status_code = 200
        response.raw = io.BytesIO(b'public bytes')
        response.request = prepared
        response.url = prepared.url
        return response

    monkeypatch.setattr(requests.Session, 'send', send)
    assert b''.join(_Fetcher(configuration())._fetch(url)) == b'public bytes'
    assert len(observed) == 1
    prepared, options = observed[0]
    assert not any(key.lower() in {'authorization', 'cookie', 'x-lds-download-grant'}
                   for key in prepared.headers)
    assert not options.get('proxies')
    assert options['verify'] is True
    assert options['allow_redirects'] is False
