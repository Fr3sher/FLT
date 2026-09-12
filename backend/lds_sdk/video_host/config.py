"""Named adapters to the existing public host; no plugin implementation is imported."""

_EXPORTS = {'LOCAL_USER': ('app.config', 'LOCAL_USER'), 'data_dir': ('app.config', 'data_dir'), 'get': ('app.config', 'get')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
