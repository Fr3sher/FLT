"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'BankJobBusy': ('app.services.bank_jobs', 'BankJobBusy'),
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
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
