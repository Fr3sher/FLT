"""Named gpu speed operations shared with the host; no module handle escapes."""

def video_latent_rows(*args, **kwargs):
    from app.services.gpu_speed import video_latent_rows
    return video_latent_rows(*args, **kwargs)



__all__ = ['video_latent_rows']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'video_latent_rows': ('app.services.gpu_speed', 'video_latent_rows')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
