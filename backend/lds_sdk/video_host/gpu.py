"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'GpuBusyError': ('app.gpu_window', 'GpuBusyError'),
 'gpu_exclusive_vision_window': ('app.gpu_window', 'gpu_exclusive_vision_window')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
