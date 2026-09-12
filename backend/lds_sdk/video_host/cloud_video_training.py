"""Named adapters to existing public host services; implementations remain in main."""

_EXPORTS = {'continue_cloud_video_run': ('app.services.cloud_video_training', 'continue_cloud_video_run'),
 'delete_cloud_video_run': ('app.services.cloud_video_training', 'delete_cloud_video_run'),
 'group_saves_by_step': ('app.services.cloud_video_training', 'group_saves_by_step'),
 'harvested_steps': ('app.services.cloud_video_training', 'harvested_steps'),
 'launch_cloud_video_training': ('app.services.cloud_video_training', 'launch_cloud_video_training'),
 'retry_cloud_video_run': ('app.services.cloud_video_training', 'retry_cloud_video_run'),
 'video_gpu_tiers': ('app.services.cloud_video_training', 'video_gpu_tiers')}
__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _EXPORTS[name]
    return getattr(import_module(module), symbol)
