"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'BACKEND_DIR': ('app.config', 'BACKEND_DIR'),
 'DEFAULTS': ('app.config', 'DEFAULTS'),
 'LOCAL_USER': ('app.config', 'LOCAL_USER'),
 'comfyui_dir': ('app.config', 'comfyui_dir'),
 'data_dir': ('app.config', 'data_dir'),
 'get': ('app.config', 'get'),
 'save_config': ('app.config', 'save_config'),
 'video_bank_sources_root': ('app.config', 'video_bank_sources_root'),
 'video_banks_root': ('app.config', 'video_banks_root'),
 'video_datasets_root': ('app.config', 'video_datasets_root')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
