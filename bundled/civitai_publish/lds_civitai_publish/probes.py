"""Civitai credential presence only; validity checks require an explicit action."""


def configured():
    from lds_sdk.lifecycle import is_available
    if not is_available('civitai_publish'):
        return {'ok': False, 'detail': 'plugin disabled'}
    try:
        from lds_sdk.credentials import civitai_api_key
        ok = bool(civitai_api_key())
    except Exception:
        from lds_sdk.config import secret
        ok = bool(secret('CIVITAI_API_KEY'))
    return {'ok': ok, 'detail': 'key set' if ok else 'key missing'}
