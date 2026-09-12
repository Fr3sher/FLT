"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'ImageEncoder': ('app.services.clip_image_encoder', 'ImageEncoder'),
 'unavailable_reason': ('app.services.clip_image_encoder', 'unavailable_reason')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
