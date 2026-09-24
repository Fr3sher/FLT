"""Explicit optional Model tools API; conversion admission honors OFF."""


def _provider():
    import importlib
    from flask import current_app, has_app_context
    from app.plugins.registry import active
    from app.plugins.optional import ServiceUnavailable
    from app import config
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    record = registry.records.get('model_tools') if registry is not None else None
    if (record is None or record.state != 'loaded' or not record.enabled
            or (config.get('plugins.enabled') or {}).get('model_tools') is False):
        raise ServiceUnavailable('model_tools', 'Model tools is not enabled')
    module = importlib.import_module('lds_model_tools.public_api_v1')
    if module.API_VERSION != 1:
        raise ServiceUnavailable('model_tools', 'The Model tools API is incompatible')
    return module


def available():
    from app.plugins.optional import ServiceUnavailable
    try:
        _provider()
        return True
    except ServiceUnavailable:
        return False


def write_headroom_bytes():
    return _provider().write_headroom_bytes()


def __getattr__(name):
    if name == 'QuantizeError':
        from app.plugins.optional import ServiceUnavailable
        try:
            return _provider().QuantizeError
        except ServiceUnavailable:
            from app.services.fp8_quantize import QuantizeError
            return QuantizeError
    raise AttributeError(name)



def plan(source, *, overwrite=False, destination=None):
    return _provider().plan(source, overwrite=overwrite, destination=destination)



def quantize(source, *, overwrite=False, destination=None, progress=None, cancelled=None):
    return _provider().quantize(source, overwrite=overwrite, destination=destination, progress=progress, cancelled=cancelled)



def interpreter():
    return _provider().interpreter()



def status():
    return _provider().status()


__all__ = ['available', 'write_headroom_bytes', 'plan', 'quantize', 'interpreter', 'status', 'QuantizeError']  # noqa: F822 -- lazy provider exception
