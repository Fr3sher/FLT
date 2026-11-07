"""Core model downloads and prompt browsing retain their shared credentials."""
import pytest

from test_public_backend_mount import factory  # noqa: F401
from app import capabilities, config as cfg
from app.services import civitai_browser


def test_core_can_manage_shared_credentials_without_products(factory, monkeypatch):
    app = factory()
    monkeypatch.setattr('app.routes.settings._lan_ip', lambda: None)
    monkeypatch.setattr('app.routes.settings._tailscale_ip', lambda: None)
    client = app.test_client()
    for key in ('HF_TOKEN', 'CIVITAI_API_KEY'):
        before = client.get('/api/settings').json['secrets']
        assert before[key] is False
        response = client.put('/api/settings', json={'secrets': {key: 'fixture-credential'}})
        assert response.status_code == 200, response.json
        assert response.json['secrets'][key] is True
        assert 'fixture-credential' not in response.get_data(as_text=True)
        assert cfg.secret(key) == 'fixture-credential'
        assert client.delete(f'/api/settings/secret/{key}').status_code == 200
        assert not cfg.secret(key)
    for key in ('VAST_API_KEY', 'HF_CLOUD_TOKEN', 'GEMINI_API_KEY'):
        assert key not in client.get('/api/settings').json['secrets']
        assert client.put('/api/settings', json={'secrets': {key: 'fixture'}}).status_code == 400


@pytest.mark.parametrize('scope', [None, 'scrape', 'civitai_publish'])
def test_core_and_declared_active_owners_can_test_shared_civitai(factory, monkeypatch, scope):
    app = factory({scope} if scope else None)
    calls = []
    monkeypatch.setattr(civitai_browser, 'civitai_api_key', lambda: 'fixture-credential')
    monkeypatch.setattr(civitai_browser, '_http_get_json',
                        lambda url, key: calls.append((url, key)) or {'username': 'creator'})
    suffix = f'?plugin={scope}' if scope else ''
    response = app.test_client().post('/api/settings/test/civitai' + suffix)
    assert response.status_code == 200
    assert response.json == {'ok': True, 'detail': 'signed in as creator'}
    assert calls == [('https://civitai.com/api/v1/me', 'fixture-credential')]


def test_unrelated_and_off_owners_cannot_test_civitai(factory):
    app = factory({'api_engines'})
    for owner in ('api_engines', 'scrape', 'civitai_publish'):
        assert app.test_client().post(f'/api/settings/test/civitai?plugin={owner}').status_code == 409


@pytest.mark.parametrize('answer', [None, [], {}, {'username': ''}, PermissionError(), RuntimeError()])
def test_civitai_probe_handles_refused_unreachable_and_invalid_response(monkeypatch, answer):
    monkeypatch.setattr(civitai_browser, 'civitai_api_key', lambda: 'fixture')
    def get(*args):
        if isinstance(answer, Exception):
            raise answer
        return answer
    monkeypatch.setattr(civitai_browser, '_http_get_json', get)
    assert capabilities.probe_civitai_test()['ok'] is False
