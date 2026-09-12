"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'salvage_orphan_tmp': ('app.services.atomic_npz', 'salvage_orphan_tmp'),
 'save_npz_atomic': ('app.services.atomic_npz', 'save_npz_atomic')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
