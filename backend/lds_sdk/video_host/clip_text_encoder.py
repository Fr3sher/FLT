"""Named clip text encoder operations shared with the host; no module handle escapes."""

def encode_query(*args, **kwargs):
    from app.services.clip_text_encoder import encode_query
    return encode_query(*args, **kwargs)


def normalize_query(*args, **kwargs):
    from app.services.clip_text_encoder import normalize_query
    return normalize_query(*args, **kwargs)


def split_query(*args, **kwargs):
    from app.services.clip_text_encoder import split_query
    return split_query(*args, **kwargs)


def unavailable_reason(*args, **kwargs):
    from app.services.clip_text_encoder import unavailable_reason
    return unavailable_reason(*args, **kwargs)


def readline_with_timeout(*args, **kwargs):
    from app.services.clip_text_encoder import _readline_with_timeout
    return _readline_with_timeout(*args, **kwargs)


from app.services.clip_text_encoder import TextEncodeError as TextEncodeError  # noqa: E402 — stable value/type identity

__all__ = ['encode_query', 'normalize_query', 'split_query', 'unavailable_reason', 'readline_with_timeout', 'TextEncodeError']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'TextEncodeError': ('app.services.clip_text_encoder', 'TextEncodeError'),
 '_readline_with_timeout': ('app.services.clip_text_encoder',
                            '_readline_with_timeout'),
 'encode_query': ('app.services.clip_text_encoder', 'encode_query'),
 'normalize_query': ('app.services.clip_text_encoder', 'normalize_query'),
 'split_query': ('app.services.clip_text_encoder', 'split_query'),
 'unavailable_reason': ('app.services.clip_text_encoder', 'unavailable_reason')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
