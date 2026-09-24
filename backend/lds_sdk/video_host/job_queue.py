"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'GPU_ARBITER_LOCK': ('app.job_queue', 'GPU_ARBITER_LOCK')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
