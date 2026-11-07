"""Named netguard operations shared with the host; no module handle escapes."""

def public_bind(*args, **kwargs):
    from app.netguard import public_bind
    return public_bind(*args, **kwargs)



__all__ = ['public_bind']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'public_bind': ('app.netguard', 'public_bind')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
