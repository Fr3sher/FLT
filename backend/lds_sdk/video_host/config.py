"""Video configuration paths and its three persisted caption preferences."""
from lds_sdk.config import get, comfyui_dir, local_user, secret, data_dir

LOCAL_USER = local_user()


def video_banks_root():
    from app.config import video_banks_root
    return video_banks_root()


def video_datasets_root():
    from app.config import video_datasets_root
    return video_datasets_root()


def video_bank_sources_root():
    from app.config import video_bank_sources_root
    return video_bank_sources_root()


def save_config(values):
    if (not isinstance(values, dict) or set(values) != {'video_caption'}
            or not isinstance(values['video_caption'], dict)
            or set(values['video_caption']) - {'motion_dials', 'motion_model', 'reference_video_observer'}):
        raise ValueError('These settings do not belong to Video.')
    from app.config import save_config
    return save_config(values)


def duplicate_threshold_default():
    from app.config import DEFAULTS
    return DEFAULTS['bank']['semantic_dup_threshold']


__all__ = ['get', 'comfyui_dir', 'secret', 'data_dir', 'LOCAL_USER',
           'video_banks_root', 'video_datasets_root', 'video_bank_sources_root',
           'save_config', 'duplicate_threshold_default']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'BACKEND_DIR': ('app.config', 'BACKEND_DIR'),
 'DEFAULTS': ('app.config', 'DEFAULTS'),
 'LOCAL_USER': ('app.config', 'LOCAL_USER'),
 'comfyui_dir': ('app.config', 'comfyui_dir'),
 'data_dir': ('app.config', 'data_dir'),
 'get': ('app.config', 'get'),
 'save_config': ('app.config', 'save_config'),
 'video_bank_sources_root': ('app.config', 'video_bank_sources_root'),
 'video_banks_root': ('app.config', 'video_banks_root'),
 'video_datasets_root': ('app.config', 'video_datasets_root')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
