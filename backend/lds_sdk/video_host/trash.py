"""Named trash operations shared with the host; no module handle escapes."""

def dispose(*args, **kwargs):
    from app.services.trash import dispose
    return dispose(*args, **kwargs)


def restore(*args, **kwargs):
    from app.services.trash import restore
    return restore(*args, **kwargs)


def send_to_trash(*args, **kwargs):
    from app.services.trash import send_to_trash
    return send_to_trash(*args, **kwargs)


from app.services.trash import TrashLockError as TrashLockError  # noqa: E402 — stable value/type identity

__all__ = ['dispose', 'restore', 'send_to_trash', 'TrashLockError']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'TrashLockError': ('app.services.trash', 'TrashLockError'),
 'dispose': ('app.services.trash', 'dispose'),
 'restore': ('app.services.trash', 'restore'),
 'send_to_trash': ('app.services.trash', 'send_to_trash')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
