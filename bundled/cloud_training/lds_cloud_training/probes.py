"""Cloud key readiness and the explicitly requested Settings key test."""
import requests
from lds_sdk.cloud_host import config as cfg

VAST_API_BASE = 'https://console.vast.ai/api/v0'


def configured():
    return bool(cfg.secret('VAST_API_KEY'))


def vast_ready():
    ok = configured()
    return {'ok': ok, 'detail': 'API key configured' if ok else 'Cloud training is not configured'}


def probe_vast() -> dict:
    """Live check of the vast.ai API key (used by the Settings 'Test' button).
    The capability gate itself is key-presence only — probe() must stay
    network-free for this entry (it runs on every /api/capabilities call)."""
    key = cfg.secret('VAST_API_KEY')
    if not key:
        return {'ok': False, 'detail': 'API key missing'}
    try:
        r = requests.get(f'{VAST_API_BASE}/users/current/',
                         headers={'Authorization': f'Bearer {key}'}, timeout=8)
        if r.status_code == 200:
            email = (r.json() or {}).get('email') or 'account'
            return {'ok': True, 'detail': f'connected as {email}'}
        return {'ok': False, 'detail': f'vast.ai returned HTTP {r.status_code}'}
    except Exception as e:
        return {'ok': False, 'detail': f'unreachable: {e}'}
