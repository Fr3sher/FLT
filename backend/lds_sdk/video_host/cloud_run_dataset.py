"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'VIDEO': ('app.services.cloud_run_dataset', 'VIDEO'),
 'dataset_row': ('app.services.cloud_run_dataset', 'dataset_row'),
 'is_video': ('app.services.cloud_run_dataset', 'is_video'),
 'owns': ('app.services.cloud_run_dataset', 'owns'),
 'table_of': ('app.services.cloud_run_dataset', 'table_of')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
