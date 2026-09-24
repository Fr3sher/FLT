"""Named comfy fs operations shared with the host; no module handle escapes."""

def claim_output_file(*args, **kwargs):
    from app.utils.comfy_fs import claim_output_file
    return claim_output_file(*args, **kwargs)


def drop_staged_inputs(*args, **kwargs):
    from app.utils.comfy_fs import drop_staged_inputs
    return drop_staged_inputs(*args, **kwargs)


def ensure_input_usable(*args, **kwargs):
    from app.utils.comfy_fs import ensure_input_usable
    return ensure_input_usable(*args, **kwargs)


def stage_input_image(*args, **kwargs):
    from app.utils.comfy_fs import stage_input_image
    return stage_input_image(*args, **kwargs)



__all__ = ['claim_output_file', 'drop_staged_inputs', 'ensure_input_usable', 'stage_input_image']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'claim_output_file': ('app.utils.comfy_fs', 'claim_output_file'),
 'ensure_input_usable': ('app.utils.comfy_fs', 'ensure_input_usable'),
 'stage_input_image': ('app.utils.comfy_fs', 'stage_input_image')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
