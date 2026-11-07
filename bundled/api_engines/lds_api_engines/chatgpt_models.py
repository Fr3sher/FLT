"""Account-scoped model discovery for the experimental subscription lane.

The catalog lists ChatGPT routing models, not image-renderer versions. Never
use the paid API catalog or credentials to resolve a subscription preference.
"""
from __future__ import annotations

import hashlib
import threading
import time

import requests

from lds_sdk import config as cfg
from lds_sdk.engine_errors import EngineFatal, SubscriptionUnavailable
from . import chatgpt_oauth

MODELS_URL = 'https://chatgpt.com/backend-api/codex/models'
CLIENT_VERSION = '0.156.1'
_TTL = 300
_lock = threading.Lock()
_cache = None


class ModelCatalogUnavailable(EngineFatal):
    """A subscription model cannot be resolved; stop before generating a batch."""


def selected_model() -> str:
    value = (cfg.get('engines.chatgpt_subscription_model') or '').strip()
    # This was the shipped default, including on hosts older than this plugin.
    # Migrate its meaning at read time without overwriting saved preferences.
    return '' if value in ('', 'auto', 'gpt-5.4-mini') else value


def _normalize(payload):
    models = payload.get('models') if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise ModelCatalogUnavailable('ChatGPT returned an unreadable model list.')
    choices = {}
    for row in models:
        if not isinstance(row, dict) or row.get('visibility') != 'list':
            continue
        slug = row.get('slug')
        if not isinstance(slug, str) or not slug.strip():
            continue
        if 'image' not in (row.get('input_modalities') or []):
            continue
        priority = row.get('priority')
        choices[slug] = {
            'id': slug, 'name': row.get('display_name') or slug,
            'description': row.get('description') or '',
            'priority': priority if isinstance(priority, (int, float)) else 9999,
        }
    result = sorted(choices.values(), key=lambda item: (item['priority'], item['id']))
    if not result:
        raise ModelCatalogUnavailable('ChatGPT returned no available models accepting reference images.')
    return result


def available_models(*, refresh=False) -> list[dict]:
    global _cache
    # Serialize discovery across the image workers; cache only successful lists,
    # bound to this credential/account, never a token or provider response body.
    with _lock:
        for attempt in (0, 1):
            token = chatgpt_oauth.access_token(force_refresh=bool(attempt))
            if not token:
                raise SubscriptionUnavailable('Connect your ChatGPT account in plugin settings to load its models.')
            account = chatgpt_oauth.account_id() or ''
            identity = hashlib.sha256((account + ':' + token).encode()).hexdigest()
            if not refresh and _cache and _cache[0] == identity and time.monotonic() < _cache[1]:
                return [dict(item) for item in _cache[2]]
            try:
                response = requests.get(
                    MODELS_URL, params={'client_version': CLIENT_VERSION},
                    headers={'Authorization': f'Bearer {token}',
                             'chatgpt-account-id': account, 'originator': 'codex_cli_rs'},
                    timeout=(10, 30))
            except requests.RequestException:
                raise ModelCatalogUnavailable(
                    'Could not load your ChatGPT models. Refresh the model list in plugin settings. '
                    'No API-key fallback was used.') from None
            if response.status_code == 401:
                if attempt == 0:
                    continue
                raise SubscriptionUnavailable('ChatGPT refused the model list connection. Reconnect in plugin settings.')
            if response.status_code != 200:
                raise ModelCatalogUnavailable(
                    f'Could not load your ChatGPT models (HTTP {response.status_code}). '
                    'Refresh the model list in plugin settings. No API-key fallback was used.')
            try:
                models = _normalize(response.json())
            except ValueError:
                raise ModelCatalogUnavailable('ChatGPT returned an unreadable model list.') from None
            _cache = (identity, time.monotonic() + _TTL, models)
            return [dict(item) for item in models]


def resolve_model() -> str:
    # An explicit choice stays pinned. The provider validates access at use time;
    # catalog/network failure must not silently replace a user's chosen model.
    return selected_model() or available_models()[0]['id']
