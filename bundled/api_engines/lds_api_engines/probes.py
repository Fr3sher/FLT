"""Readiness of the three API engines — a key's PRESENCE, never its validity:
these run on every capabilities poll, and two of the providers bill per
request. A key that is set but refused is reported at generation time, with
the provider's own words. The same functions serve the "Save & test" button of
each key field (the engine's `key_test_target`)."""
from lds_sdk import config as cfg


def probe_gemini() -> dict:
    ok = bool(cfg.secret('GEMINI_API_KEY'))
    return {'ok': ok, 'detail': 'key set' if ok else 'key missing'}


def probe_openai() -> dict:
    """ChatGPT engine readiness: a pay-per-use API key OR a connected ChatGPT
    subscription (Codex OAuth) both light the engine up."""
    from . import chatgpt_oauth
    key = bool(cfg.secret('OPENAI_API_KEY'))
    sub = chatgpt_oauth.status()['connected']
    parts = (['key set'] if key else []) + (['subscription connected'] if sub else [])
    return {'ok': key or sub, 'detail': ' + '.join(parts) if parts else 'key missing'}


def probe_openrouter() -> dict:
    ok = bool(cfg.secret('OPENROUTER_API_KEY'))
    return {'ok': ok, 'detail': 'key set' if ok else 'key missing'}


def chatgpt_subscription() -> dict:
    """The capabilities' `chatgpt_subscription` section: whether the Codex
    OAuth lane is connected, for whom, and whether a Codex CLI login exists on
    this machine to import."""
    from . import chatgpt_oauth
    status = chatgpt_oauth.status()
    return {
        'connected': status['connected'],
        'email': status['email'],
        'plan': status['plan'],
        'codex_cli_detected': chatgpt_oauth.codex_auth_path().is_file(),
    }
