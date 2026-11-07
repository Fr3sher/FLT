"""Named bank jobs operations shared with the host; no module handle escapes."""

def abort(*args, **kwargs):
    from app.services.bank_jobs import abort
    return abort(*args, **kwargs)


def bump(*args, **kwargs):
    from app.services.bank_jobs import bump
    return bump(*args, **kwargs)


def cancel(*args, **kwargs):
    from app.services.bank_jobs import cancel
    return cancel(*args, **kwargs)


def cancelled(*args, **kwargs):
    from app.services.bank_jobs import cancelled
    return cancelled(*args, **kwargs)


def fail(*args, **kwargs):
    from app.services.bank_jobs import fail
    return fail(*args, **kwargs)


def get(*args, **kwargs):
    from app.services.bank_jobs import get
    return get(*args, **kwargs)


def launched(*args, **kwargs):
    from app.services.bank_jobs import launched
    return launched(*args, **kwargs)


def mutation_lease(*args, **kwargs):
    from app.services.bank_jobs import mutation_lease
    return mutation_lease(*args, **kwargs)


def progress(*args, **kwargs):
    from app.services.bank_jobs import progress
    return progress(*args, **kwargs)


def require_reservation(*args, **kwargs):
    from app.services.bank_jobs import require_reservation
    return require_reservation(*args, **kwargs)


def reserve(*args, **kwargs):
    from app.services.bank_jobs import reserve
    return reserve(*args, **kwargs)


def running(*args, **kwargs):
    from app.services.bank_jobs import running
    return running(*args, **kwargs)


def set_cancel_hook(*args, **kwargs):
    from app.services.bank_jobs import set_cancel_hook
    return set_cancel_hook(*args, **kwargs)


def set_pipeline(*args, **kwargs):
    from app.services.bank_jobs import set_pipeline
    return set_pipeline(*args, **kwargs)


def start(*args, **kwargs):
    from app.services.bank_jobs import start
    return start(*args, **kwargs)


from app.services.bank_jobs import BankJobBusy as BankJobBusy  # noqa: E402 — stable value/type identity

__all__ = ['abort', 'bump', 'cancel', 'cancelled', 'fail', 'get', 'launched', 'mutation_lease', 'progress', 'require_reservation', 'reserve', 'running', 'set_cancel_hook', 'set_pipeline', 'start', 'BankJobBusy']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'BankJobBusy': ('app.services.bank_jobs', 'BankJobBusy'),
 'abort': ('app.services.bank_jobs', 'abort'),
 'bump': ('app.services.bank_jobs', 'bump'),
 'cancel': ('app.services.bank_jobs', 'cancel'),
 'cancelled': ('app.services.bank_jobs', 'cancelled'),
 'fail': ('app.services.bank_jobs', 'fail'),
 'get': ('app.services.bank_jobs', 'get'),
 'launched': ('app.services.bank_jobs', 'launched'),
 'mutation_lease': ('app.services.bank_jobs', 'mutation_lease'),
 'progress': ('app.services.bank_jobs', 'progress'),
 'require_reservation': ('app.services.bank_jobs', 'require_reservation'),
 'reserve': ('app.services.bank_jobs', 'reserve'),
 'running': ('app.services.bank_jobs', 'running'),
 'set_cancel_hook': ('app.services.bank_jobs', 'set_cancel_hook'),
 'set_pipeline': ('app.services.bank_jobs', 'set_pipeline'),
 'start': ('app.services.bank_jobs', 'start')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
