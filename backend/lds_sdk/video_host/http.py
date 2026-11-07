"""Named http operations shared with the host; no module handle escapes."""

def map_error(*args, **kwargs):
    from app.routes._common import _map_error
    return _map_error(*args, **kwargs)


def require_comfyui(*args, **kwargs):
    from app.routes._common import _require_comfyui
    return _require_comfyui(*args, **kwargs)


def require_no_stalled_comfyui(*args, **kwargs):
    from app.routes._common import _require_no_stalled_comfyui
    return _require_no_stalled_comfyui(*args, **kwargs)


def studio_missing_response(*args, **kwargs):
    from app.routes._common import _studio_missing_response
    return _studio_missing_response(*args, **kwargs)



__all__ = ['map_error', 'require_comfyui', 'require_no_stalled_comfyui', 'studio_missing_response']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'_map_error': ('app.routes._common', '_map_error'),
 '_studio_missing_response': ('app.routes._common', '_studio_missing_response'),
 'require_comfyui': ('app.routes._common', '_require_comfyui'),
 'require_no_stalled_comfyui': ('app.routes._common',
                                '_require_no_stalled_comfyui')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
