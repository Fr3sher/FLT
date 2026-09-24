"""Named atomic npz operations shared with the host; no module handle escapes."""

def salvage_orphan_tmp(*args, **kwargs):
    from app.services.atomic_npz import salvage_orphan_tmp
    return salvage_orphan_tmp(*args, **kwargs)


def save_npz_atomic(*args, **kwargs):
    from app.services.atomic_npz import save_npz_atomic
    return save_npz_atomic(*args, **kwargs)



__all__ = ['salvage_orphan_tmp', 'save_npz_atomic']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'salvage_orphan_tmp': ('app.services.atomic_npz', 'salvage_orphan_tmp'),
 'save_npz_atomic': ('app.services.atomic_npz', 'save_npz_atomic')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
