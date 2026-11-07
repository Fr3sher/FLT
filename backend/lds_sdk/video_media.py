"""API 1.21: Video-owned media operations for optional finishing products.

The application supplies user identity; no ORM, transport or configuration
handle escapes. Import and access are refused while Video is disabled.
"""
from importlib import import_module
from .lifecycle import is_available, state_change_lock
from .dlss5 import NeuralRenderError


def available():
    with state_change_lock:
        return is_available('video')


def _call(operation, *args):
    with state_change_lock:
        if not is_available('video'):
            raise NeuralRenderError('Enable Video to use its datasets or clip Studio.')
        api = import_module('lds_video.neural_render_media')
        if getattr(api, 'API_VERSION', None) != 1:
            raise NeuralRenderError('Update Video to use the DLSS 5 integration.')
        return getattr(api, operation)(*args)


def dataset_exists(user_id, dataset_id):
    return _call('dataset_exists', user_id, dataset_id)


def dataset_clip_media_path(user_id, dataset_id, clip_id):
    return _call('dataset_clip_media_path', user_id, dataset_id, clip_id)


def dataset_job(dataset_id):
    return _call('dataset_job', dataset_id)


def cancel_dataset_job(dataset_id):
    return _call('cancel_dataset_job', dataset_id)


def rendered_clip_ids(user_id, dataset_id):
    return _call('rendered_clip_ids', user_id, dataset_id)


def rendered_clip_params(user_id, dataset_id):
    return _call('rendered_clip_params', user_id, dataset_id)


def start_dataset_render(app, user_id, dataset_id, clip_ids, params):
    return _call('start_dataset_render', app, user_id, dataset_id, clip_ids, params)


def original_clip_path(user_id, dataset_id, clip_id):
    return _call('original_clip_path', user_id, dataset_id, clip_id)


def restore_dataset_clips(user_id, dataset_id, clip_ids=None):
    return _call('restore_dataset_clips', user_id, dataset_id, clip_ids)


def start_studio_render(app, user_id, clip_id, params):
    return _call('start_studio_render', app, user_id, clip_id, params)


def studio_comparison_paths(user_id, clip_id):
    return _call('studio_comparison_paths', user_id, clip_id)


__all__ = ['available', 'dataset_exists', 'dataset_clip_media_path', 'dataset_job',
           'cancel_dataset_job', 'rendered_clip_ids', 'rendered_clip_params',
           'start_dataset_render', 'original_clip_path', 'restore_dataset_clips',
           'start_studio_render', 'studio_comparison_paths']
