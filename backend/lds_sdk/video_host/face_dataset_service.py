"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'_source_metadata_storage': ('app.services.face_dataset_service', '_source_metadata_storage'),
 'get_dataset': ('app.services.face_dataset_service', 'get_dataset')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
