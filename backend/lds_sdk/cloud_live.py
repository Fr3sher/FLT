"""Versioned live_pod operations; no provider implementation path is exposed."""
from __future__ import annotations
from ._cloud_provider import provider as _cloud_provider

from .cloud_errors import LivePodError, VastError
__all__ = ['LivePodError', 'VastError', 'MAX_GPUS', 'REFERENCE_GPU', 'rent',
           'wait_ready', 'validate_workflow', 'upload_lora', 'destroy',
           'parse_history', 'attention_from_log', 'current', 'config',
           'pack_bytes', 'offers', 'gpu_choices', 'available', 'tls_ready', 'engine_status',
           'download_minutes', 'quoted_price_cap']
MAX_GPUS = 4
REFERENCE_GPU = 'RTX 4090'


def provider(*, recovery=False):
    module = _cloud_provider(recovery=recovery)
    if not recovery:
        from . import live_services
        from .plugin_services import ServiceUnavailable
        try:
            owner = live_services.provider_id()
        except ServiceUnavailable:
            owner = None
        if owner == 'live' and getattr(module, 'LIVE_INDEPENDENT', False) is not True:
            raise ServiceUnavailable('cloud_training', 'Update Cloud training to use independently installed Live.')
    return module



def rent(session_id, gpu_name, light=False, on_phase=None, gpus=1, *, engine='comfyui',
         owner='live', profile=None, quote_max_price_per_hour=None):
    module = provider(recovery=False)
    _require_engine(module, engine)
    if owner != 'live' or profile is not None or quote_max_price_per_hour is not None:
        _require_reference(module)
        return module.live_rent(session_id, gpu_name, light, on_phase, gpus, engine=engine,
                                owner=owner, profile=profile, quote_max_price_per_hour=quote_max_price_per_hour)
    if engine == 'comfyui':
        return module.live_rent(session_id, gpu_name, light, on_phase, gpus)
    return module.live_rent(session_id, gpu_name, light, on_phase, gpus, engine=engine)



def wait_ready(pod, stop_event, expected_loras=(), on_phase=None):
    return provider(recovery=False).live_wait_ready(pod, stop_event, expected_loras, on_phase)



def validate_workflow(pod, workflow):
    return provider(recovery=False).live_validate_workflow(pod, workflow)



def upload_lora(pod, local_path, rel_name, on_phase=None, stop_event=None):
    return provider(recovery=False).live_upload_lora(pod, local_path, rel_name, on_phase, stop_event)



def destroy(pod):
    return provider(recovery=True).live_destroy(pod)



def parse_history(entry):
    return provider(recovery=True).live_parse_history(entry)



def attention_from_log(text):
    return provider(recovery=True).live_attention_from_log(text)



def current():
    from app.plugins.optional import ServiceUnavailable
    try:
        return provider(recovery=True).live_current()
    except ServiceUnavailable:
        return None


def available():
    from app.plugins.optional import ServiceUnavailable
    try:
        provider()
        return True
    except ServiceUnavailable:
        return False



def config():
    return provider(recovery=True).live_config()



def pack_bytes(light=False):
    return provider(recovery=False).live_pack_bytes(light)



def offers(light=False, include_over_budget=False, *, engine='comfyui', gpus=None):
    module = provider(recovery=False)
    _require_engine(module, engine)
    if gpus is not None:
        _require_reference(module)
        return module.live_offers(light, include_over_budget, engine=engine, gpus=gpus)
    if engine == 'comfyui':
        return module.live_offers(light, include_over_budget)
    return module.live_offers(light, include_over_budget, engine=engine)



def gpu_choices(c):
    return provider(recovery=False).live_gpu_choices(c)


def tls_ready():
    from app.plugins.optional import ServiceUnavailable
    try:
        module = provider()
        ready = getattr(module, 'live_tls_ready', None)
        if not callable(ready):
            return {'ok': False, 'detail': 'Update Cloud to use Native MiniMax TLS.'}
        return ready()
    except ServiceUnavailable:
        return {"ok": False, "detail": "Enable Cloud to use Native MiniMax rental and its TLS setup."}


def _require_engine(module, engine):
    from app.plugins.optional import ServiceUnavailable
    advertised = getattr(module, 'live_engines', None)
    engines = advertised() if callable(advertised) else ('comfyui',)
    if engine not in ('comfyui', 'sglang') or engine not in engines:
        raise ServiceUnavailable('cloud_training', 'Update Cloud to use the requested Live rendering engine.')
    # Earlier Cloud advertises native rendering but only knows its fixed
    # one-H200 profile. Options, offers and rent must agree on group support
    # before Live prepares a writer or session for a selection it cannot rent.
    if engine == 'sglang':
        _require_reference(module)


def engine_status(engine):
    """Negotiate optional Live engines; older Cloud keeps its ComfyUI contract."""
    from app.plugins.optional import ServiceUnavailable
    try:
        _require_engine(provider(), engine)
        return {'ok': True, 'detail': ''}
    except ServiceUnavailable as exc:
        return {'ok': False, 'detail': str(exc)}


def _require_reference(module):
    from .plugin_services import ServiceUnavailable
    if getattr(module, 'REFERENCE_API_VERSION', None) != 1:
        raise ServiceUnavailable('cloud_training', 'Update Cloud to use Reference rentals and selected GPU groups.')


def download_minutes(size, inet_down):
    module = provider()
    _require_reference(module)
    return module.live_download_minutes(size, inet_down)


def quoted_price_cap(config, quote):
    module = provider()
    _require_reference(module)
    return module.live_quoted_price_cap(config, quote)
