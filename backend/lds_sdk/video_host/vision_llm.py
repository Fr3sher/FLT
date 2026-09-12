"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'describe_frames': ('app.services.vision_llm', 'describe_frames'),
 'describe_image': ('app.services.vision_llm', 'describe_image'),
 'generate_text': ('app.services.vision_llm', 'generate_text'),
 'label': ('app.services.vision_llm', 'label'),
 'list_models': ('app.services.vision_llm', 'list_models'),
 'provider': ('app.services.vision_llm', 'provider')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
