"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'claim_output_file': ('app.utils.comfy_fs', 'claim_output_file'),
 'ensure_input_usable': ('app.utils.comfy_fs', 'ensure_input_usable'),
 'stage_input_image': ('app.utils.comfy_fs', 'stage_input_image')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
