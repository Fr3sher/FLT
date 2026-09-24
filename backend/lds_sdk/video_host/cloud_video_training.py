"""Pure local save grouping and explicit active Cloud-product operations."""
from app.services.cloud_video_training import group_saves_by_step, harvested_steps
from lds_sdk.lifecycle import is_available, state_change_lock

__all__ = ['continue_cloud_video_run', 'delete_cloud_video_run', 'group_saves_by_step',
           'harvested_steps', 'launch_cloud_video_training', 'retry_cloud_video_run', 'video_gpu_tiers']


def _active_product():
    if not is_available('cloud_training'):
        raise RuntimeError('Cloud training is disabled or unavailable')
    from lds_cloud_training import cloud_video_training
    return cloud_video_training


def continue_cloud_video_run(*args, **kwargs):
    return _active_product().continue_cloud_video_run(*args, **kwargs)


def delete_cloud_video_run(*args, **kwargs):
    with state_change_lock:
        return _active_product().delete_cloud_video_run(*args, **kwargs)


def launch_cloud_video_training(*args, **kwargs):
    return _active_product().launch_cloud_video_training(*args, **kwargs)


def retry_cloud_video_run(*args, **kwargs):
    return _active_product().retry_cloud_video_run(*args, **kwargs)


def video_gpu_tiers(*args, **kwargs):
    return _active_product().video_gpu_tiers(*args, **kwargs)
