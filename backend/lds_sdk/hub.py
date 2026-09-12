"""Named adapters to the existing public host; no plugin implementation is imported."""

_EXPORTS = {'HfPublishError': ('app.services.hf_publish', 'HfPublishError'), 'hf_namespace': ('app.services.hf_publish', 'hf_namespace'), 'http_status': ('app.services.hf_publish', '_http_status'), 'make_api': ('app.services.hf_publish', '_make_api'), 'require_write_scope': ('app.services.hf_publish', '_require_write_scope')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
