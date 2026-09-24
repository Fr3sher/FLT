"""Explicit image restoration providers, separate from prompt generation."""
from contextlib import contextmanager
from flask import current_app, has_app_context
from .registry import active
from .lifecycle import state_change_lock

class RestoreUnavailable(RuntimeError):
    """An explicitly requested restoration is not active in this installation."""

def provider(engine):
    from app import config
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    spec = registry.restore_engines.get(engine) if registry else None
    record = registry.records.get(spec['plugin']) if spec else None
    if (not record or not record.enabled or record.state != 'loaded'
            or (config.get('plugins.enabled') or {}).get(record.id) is False):
        raise RestoreUnavailable(f'The {engine} restoration is unavailable. Install or enable its plug-in in the Store, then restart LDS.')
    return spec

@contextmanager
def admission(engine):
    with state_change_lock:
        yield provider(engine)

def error_response(error):
    if isinstance(error, RestoreUnavailable):
        return {'error': str(error), 'plugin_unavailable': True}, 409
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    for engine, spec in (registry.restore_engines.items() if registry else ()):
        try:
            provider(engine)
        except RestoreUnavailable:
            continue
        result = spec['error_response'](error)
        if result is not None:
            return result
    return None
