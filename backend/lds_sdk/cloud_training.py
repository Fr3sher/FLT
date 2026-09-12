"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'ACTIVE_STATES': ('app.services.cloud_training', 'ACTIVE_STATES'),
 '_run_param': ('app.services.cloud_training', '_run_param'),
 'cfg': ('app.services.cloud_training', 'cfg'),
 'checkpoint_store_dir': ('app.services.cloud_training', 'checkpoint_store_dir'),
 'delete_cloud_checkpoint': ('app.services.cloud_training', 'delete_cloud_checkpoint'),
 'get_active_runs': ('app.services.cloud_training', 'get_active_runs'),
 'latest_run_for': ('app.services.cloud_training', 'latest_run_for'),
 'month_spend_usd': ('app.services.cloud_training', 'month_spend_usd'),
 'run_checkpoint_files': ('app.services.cloud_training', 'run_checkpoint_files'),
 'run_checkpoint_path': ('app.services.cloud_training', 'run_checkpoint_path')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
