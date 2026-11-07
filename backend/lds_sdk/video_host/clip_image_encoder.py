"""Named clip image encoder operations shared with the host; no module handle escapes."""

def unavailable_reason(*args, **kwargs):
    from app.services.clip_image_encoder import unavailable_reason
    return unavailable_reason(*args, **kwargs)


from app.services.clip_image_encoder import ImageEncoder as ImageEncoder  # noqa: E402 — stable value/type identity

__all__ = ['unavailable_reason', 'ImageEncoder']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'ImageEncoder': ('app.services.clip_image_encoder', 'ImageEncoder'),
 'unavailable_reason': ('app.services.clip_image_encoder',
                        'unavailable_reason')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
