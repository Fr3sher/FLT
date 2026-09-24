"""Named comfy model paths operations shared with the host; no module handle escapes."""

def scan_family_tree(*args, **kwargs):
    from app.services.comfy_model_paths import scan_family_tree
    return scan_family_tree(*args, **kwargs)


def search_roots(*args, **kwargs):
    from app.services.comfy_model_paths import search_roots
    return search_roots(*args, **kwargs)



__all__ = ['scan_family_tree', 'search_roots']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'search_roots': ('app.services.comfy_model_paths', 'search_roots')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
