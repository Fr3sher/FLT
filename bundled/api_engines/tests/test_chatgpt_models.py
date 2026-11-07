"""Subscription discovery: availability, account isolation and no paid fallback."""
from unittest.mock import Mock

import pytest
import requests


def _connected(monkeypatch):
    from lds_api_engines import chatgpt_models as models
    monkeypatch.setattr(models.chatgpt_oauth, 'access_token', lambda force_refresh=False: 'test-session')
    monkeypatch.setattr(models.chatgpt_oauth, 'account_id', lambda: 'test-account')
    return models


def _catalog():
    return {'models': [
        {'slug': 'older', 'visibility': 'list', 'priority': 9, 'input_modalities': ['text', 'image']},
        {'slug': 'current', 'display_name': 'Current model', 'visibility': 'list',
         'priority': 1, 'input_modalities': ['text', 'image']},
        {'slug': 'internal', 'visibility': 'hide', 'priority': 0, 'input_modalities': ['image']},
        {'slug': 'text-only', 'visibility': 'list', 'priority': 0, 'input_modalities': ['text']},
    ]}


def test_auto_uses_account_priority_and_catalog_cache_is_account_scoped(monkeypatch):
    models = _connected(monkeypatch)
    get = Mock(return_value=Mock(status_code=200, json=lambda: _catalog()))
    monkeypatch.setattr(models.requests, 'get', get)
    assert models.resolve_model() == 'current'  # also replaces the old host default
    choices = models.available_models()
    assert [item['id'] for item in choices] == ['current', 'older']
    choices[0]['id'] = 'mutated-by-caller'
    assert models.available_models()[0]['id'] == 'current'
    assert get.call_count == 1
    models.available_models(refresh=True)
    assert get.call_count == 2
    monkeypatch.setattr(models.chatgpt_oauth, 'access_token', lambda force_refresh=False: 'different-session')
    models.available_models()
    assert get.call_count == 3
    monkeypatch.setattr(models.chatgpt_oauth, 'account_id', lambda: 'different-account')
    models.available_models()
    assert get.call_count == 4
    assert get.call_args.args[0] == models.MODELS_URL


def test_manual_choice_stays_pinned_without_catalog_request(monkeypatch):
    from lds_sdk import config
    models = _connected(monkeypatch)
    config.save_config({'engines': {'chatgpt_subscription_model': 'my-choice'}})
    assert models.resolve_model() == 'my-choice'


def test_expired_session_refreshes_once_and_returns_safe_route_metadata(app, monkeypatch):
    models = _connected(monkeypatch)
    token = Mock(side_effect=['expired-session', 'fresh-session'])
    monkeypatch.setattr(models.chatgpt_oauth, 'access_token', token)
    get = Mock(side_effect=[Mock(status_code=401), Mock(status_code=200, json=lambda: _catalog())])
    monkeypatch.setattr(models.requests, 'get', get)
    from lds_api_engines.routes import bp
    app.register_blueprint(bp, url_prefix='/api')
    result = app.test_client().get('/api/settings/chatgpt-oauth/models?refresh=1')
    assert result.status_code == 200
    assert result.json['recommended'] == 'current'
    assert token.call_args.kwargs == {'force_refresh': True}
    assert get.call_args.kwargs['headers']['Authorization'] == 'Bearer fresh-session'
    assert 'session' not in result.text
    assert 'account' not in result.text


@pytest.mark.parametrize('failure', ['offline', 'invalid-json', 'empty', 'denied'])
def test_failed_catalog_stops_auto_without_using_api_key(monkeypatch, failure):
    from lds_sdk.engine_errors import EngineFatal
    models = _connected(monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-unused-api-key')
    get = Mock()
    if failure == 'offline':
        get.side_effect = requests.ConnectionError('offline')
    elif failure == 'invalid-json':
        get.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError()))
    elif failure == 'empty':
        get.return_value = Mock(status_code=200, json=lambda: {'models': []})
    else:
        get.return_value = Mock(status_code=403)
    monkeypatch.setattr(models.requests, 'get', get)
    with pytest.raises(EngineFatal):
        models.resolve_model()
    assert get.call_count == 1
    assert models._cache is None


def test_disconnected_route_does_not_expose_previous_catalog(app, monkeypatch):
    models = _connected(monkeypatch)
    monkeypatch.setattr(models.requests, 'get', Mock(return_value=Mock(status_code=200, json=lambda: _catalog())))
    models.available_models()
    monkeypatch.setattr(models.chatgpt_oauth, 'access_token', lambda force_refresh=False: None)
    from lds_api_engines.routes import bp
    app.register_blueprint(bp, url_prefix='/api')
    response = app.test_client().get('/api/settings/chatgpt-oauth/models')
    assert response.status_code == 401
    assert 'models' not in response.json
