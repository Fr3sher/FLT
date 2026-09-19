"""Named vision llm operations shared with the host; no module handle escapes."""

def base_url(*args, **kwargs):
    from app.services.vision_llm import base_url
    return base_url(*args, **kwargs)


def describe_frames(*args, **kwargs):
    from app.services.vision_llm import describe_frames
    return describe_frames(*args, **kwargs)


def describe_image(*args, **kwargs):
    from app.services.vision_llm import describe_image
    return describe_image(*args, **kwargs)


def generate_text(*args, **kwargs):
    from app.services.vision_llm import generate_text
    return generate_text(*args, **kwargs)


def label(*args, **kwargs):
    from app.services.vision_llm import label
    return label(*args, **kwargs)


def list_models(*args, **kwargs):
    from app.services.vision_llm import list_models
    return list_models(*args, **kwargs)


def provider(*args, **kwargs):
    from app.services.vision_llm import provider
    return provider(*args, **kwargs)


def unload_vision_model(*args, **kwargs):
    from app.services.vision_llm import unload_vision_model
    return unload_vision_model(*args, **kwargs)


def vision_model(*args, **kwargs):
    from app.services.vision_llm import vision_model
    return vision_model(*args, **kwargs)



__all__ = ['base_url', 'describe_frames', 'describe_image', 'generate_text', 'label', 'list_models', 'provider', 'unload_vision_model', 'vision_model']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'describe_frames': ('app.services.vision_llm', 'describe_frames'),
 'describe_image': ('app.services.vision_llm', 'describe_image'),
 'generate_text': ('app.services.vision_llm', 'generate_text'),
 'label': ('app.services.vision_llm', 'label'),
 'list_models': ('app.services.vision_llm', 'list_models'),
 'provider': ('app.services.vision_llm', 'provider')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
