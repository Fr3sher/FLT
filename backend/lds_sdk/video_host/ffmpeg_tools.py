"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'ffmpeg_path': ('app.services.ffmpeg_tools', 'ffmpeg_path'),
 'ffmpeg_ready': ('app.services.ffmpeg_tools', 'ffmpeg_ready')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
