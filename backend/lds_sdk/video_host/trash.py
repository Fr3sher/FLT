"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'TrashLockError': ('app.services.trash', 'TrashLockError'),
 'dispose': ('app.services.trash', 'dispose'),
 'restore': ('app.services.trash', 'restore'),
 'send_to_trash': ('app.services.trash', 'send_to_trash')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
