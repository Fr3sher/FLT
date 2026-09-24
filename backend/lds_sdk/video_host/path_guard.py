"""Named path guard operations shared with the host; no module handle escapes."""

def dataset_folder_conflict(*args, **kwargs):
    from app.services.path_guard import dataset_folder_conflict
    return dataset_folder_conflict(*args, **kwargs)



__all__ = ['dataset_folder_conflict']


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'dataset_folder_conflict': ('app.services.path_guard',
                             'dataset_folder_conflict')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
