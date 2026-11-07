"""Named vision image operations shared with the host; no module handle escapes."""

def ensure_vision_safe_jpeg(*args, **kwargs):
    from app.services.vision_image import ensure_vision_safe_jpeg
    return ensure_vision_safe_jpeg(*args, **kwargs)



__all__ = ['ensure_vision_safe_jpeg']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'ensure_vision_safe_jpeg': ('app.services.vision_image',
                             'ensure_vision_safe_jpeg')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
