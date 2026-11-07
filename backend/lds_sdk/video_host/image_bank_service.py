"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'_push_down_weight': ('app.services.image_bank_service', '_push_down_weight'),
 'get_bank': ('app.services.image_bank_service', 'get_bank'),
 'resolved_image_path': ('app.services.image_bank_service', 'resolved_image_path')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
