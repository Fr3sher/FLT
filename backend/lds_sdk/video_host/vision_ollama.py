"""Named vision ollama operations shared with the host; no module handle escapes."""

def get_vision_model(*args, **kwargs):
    from app.services.vision_ollama import get_vision_model
    return get_vision_model(*args, **kwargs)


def unload_vision_model(*args, **kwargs):
    from app.services.vision_ollama import unload_vision_model
    return unload_vision_model(*args, **kwargs)



__all__ = ['get_vision_model', 'unload_vision_model', 'LocalOllamaFenceError']


from app.services.vision_ollama import LocalOllamaFenceError


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'get_vision_model': ('app.services.vision_ollama', 'get_vision_model'),
 'unload_vision_model': ('app.services.vision_ollama', 'unload_vision_model')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
