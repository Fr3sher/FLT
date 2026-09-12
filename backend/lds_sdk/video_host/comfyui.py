"""Named adapters to the existing public host; no plugin implementation is imported."""

_EXPORTS = {'fetch_output_image_bytes': ('app.utils.comfyui', 'fetch_output_image_bytes')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
