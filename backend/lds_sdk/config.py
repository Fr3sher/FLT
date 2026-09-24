"""Read the active LDS configuration without depending on its storage layout."""

__all__ = ['get', 'comfyui_dir', 'local_user', 'secret', 'data_dir', 'aitoolkit_path',
           'defaults', 'checkpoints_root', 'cloud_runs_root']


def get(key, default=None):
    from app import config
    return config.get(key, default)


def comfyui_dir(kind):
    from app import config
    return config.comfyui_dir(kind)


def local_user():
    from app.config import LOCAL_USER
    return LOCAL_USER


def secret(name):
    """Read one host-managed credential; never enumerate the process environment."""
    from app import config
    if name not in config.SECRET_KEYS:
        raise ValueError('The credential is not managed by LDS.')
    return config.secret(name)


def data_dir():
    """Writable application data root, for documented historical shared files.

    New plugin-owned state should use the plugin context's data_dir instead.
    This adapter preserves pre-existing shared credentials without relocating
    them or accidentally creating a second login.
    """
    from app import config
    return config.data_dir()


def aitoolkit_path(kind):
    from app import config
    return config.aitoolkit_path(kind)


def defaults(key):
    """An independent value copy of a documented configuration block."""
    from copy import deepcopy
    from app import config
    value = config.DEFAULTS
    for part in str(key).split('.'):
        value = value.get(part, {}) if isinstance(value, dict) else {}
    return deepcopy(value)


def checkpoints_root(create=True):
    from app import config
    return config.checkpoints_root(create=create)


def cloud_runs_root(create=True):
    from app import config
    return config.cloud_runs_root(create=create)
