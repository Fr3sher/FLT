"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'TextEncodeError': ('app.services.clip_text_encoder', 'TextEncodeError'),
 '_readline_with_timeout': ('app.services.clip_text_encoder', '_readline_with_timeout'),
 'encode_query': ('app.services.clip_text_encoder', 'encode_query'),
 'normalize_query': ('app.services.clip_text_encoder', 'normalize_query'),
 'split_query': ('app.services.clip_text_encoder', 'split_query'),
 'unavailable_reason': ('app.services.clip_text_encoder', 'unavailable_reason')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
