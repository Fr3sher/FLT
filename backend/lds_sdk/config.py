"""Read the active LDS configuration without depending on its storage layout."""


def get(key, default=None):
    from app import config
    return config.get(key, default)


def comfyui_dir(kind):
    from app import config
    return config.comfyui_dir(kind)


def data_dir():
    from app import config
    return config.data_dir()


def local_user():
    from app.config import LOCAL_USER
    return LOCAL_USER


def secret(name):
    """Read one host-managed credential; never enumerate the process environment."""
    from app import config
    if name not in config.SECRET_KEYS:
        raise ValueError('The credential is not managed by LDS.')
    return config.secret(name)


__all__ = ['comfyui_dir', 'data_dir', 'get', 'local_user', 'secret']
