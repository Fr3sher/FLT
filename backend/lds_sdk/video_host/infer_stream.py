"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'run_infer_script': ('app.services.infer_stream', 'run_infer_script'),
 'stderr_tail': ('app.services.infer_stream', 'stderr_tail')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
