"""Named ffmpeg tools operations shared with the host; no module handle escapes."""

def ffmpeg_path(*args, **kwargs):
    from app.services.ffmpeg_tools import ffmpeg_path
    return ffmpeg_path(*args, **kwargs)


def ffmpeg_ready(*args, **kwargs):
    from app.services.ffmpeg_tools import ffmpeg_ready
    return ffmpeg_ready(*args, **kwargs)



__all__ = ['ffmpeg_path', 'ffmpeg_ready']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'ffmpeg_path': ('app.services.ffmpeg_tools', 'ffmpeg_path'),
 'ffmpeg_ready': ('app.services.ffmpeg_tools', 'ffmpeg_ready')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
