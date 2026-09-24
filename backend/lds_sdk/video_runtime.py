"""Snapshots and owner-checked admission for the public Video and Live queue."""
from dataclasses import dataclass
import json

from .lifecycle import is_available, state_change_lock


@dataclass(frozen=True)
class QueueRecord:
    job_id: str
    user_id: str
    status: str
    result_filename: str | None
    started_at: object
    completed_at: object


def _owner(metadata):
    if not isinstance(metadata, dict) or any(not isinstance(key, str) for key in metadata):
        return None
    flags = (metadata.get('is_video_test') is True, metadata.get('is_live') is True)
    if sum(flags) != 1 or any(key.startswith('is_') and key not in {'is_video_test', 'is_live'}
                              for key in metadata):
        return None
    owner, model = ('live', 'video_live') if flags[1] else ('video', 'video_lora_test')
    return owner if metadata.get('model_name') == model else None


def _row(job_id):
    from app.models import ImageGenerationQueue
    row = ImageGenerationQueue.query.filter_by(job_id=str(job_id)).populate_existing().first()
    if row is None:
        return None, None
    try:
        owner = _owner(json.loads(row.job_metadata or '{}'))
    except (TypeError, ValueError):
        owner = None
    return (row, owner) if owner else (None, None)


def job(job_id):
    row, _ = _row(job_id)
    return QueueRecord(**{key: getattr(row, key) for key in QueueRecord.__dataclass_fields__}) if row else None


class VideoQueue:
    _read = frozenset({'training_dataset_id', 'training_dataset_table', 'training_error',
                       'training_in_progress', 'training_pid', 'vision_in_progress'})
    _write = frozenset({'training_error', 'training_in_progress', 'training_dataset_id',
                        'training_dataset_table', 'training_target_step', 'training_run_token',
                        'training_train_type'})

    def get_state(self, key, default=None):
        if key not in self._read:
            raise ValueError('Unsupported Video admission state.')
        from app.job_queue import queue_manager
        return queue_manager._get_system_state(key, default)

    def set_state(self, key, value, *, ttl_seconds=None):
        if key not in self._write:
            raise ValueError('Unsupported Video admission state.')
        if key == 'training_dataset_table' and value != 'video_dataset':
            raise ValueError('Video training must belong to video_dataset.')
        if key == 'training_train_type' and value != 'video':
            raise ValueError('Video training must use the video training type.')
        from app.job_queue import queue_manager
        with state_change_lock:
            if not is_available('video'):
                raise ValueError('Enable video before changing its admission state.')
            return queue_manager._set_system_state(key, value, ttl_seconds=ttl_seconds)

    _get_system_state = get_state
    _set_system_state = set_state

    def has_comfyui_work(self):
        from app.job_queue import queue_manager
        return queue_manager.has_comfyui_work()

    def add_job(self, *, job_type, user_id, workflow_data, prompt, metadata, job_id=None, commit=True):
        owner = _owner(metadata)
        if job_type != 'image' or owner is None:
            raise ValueError('Expected an owned Video or Live workflow.')
        from app.job_queue import queue_manager
        with state_change_lock:
            if not is_available(owner):
                raise ValueError(f'Enable {owner} before creating clips.')
            return queue_manager.add_job(job_type=job_type, user_id=user_id, workflow_data=workflow_data,
                                         prompt=prompt, metadata=metadata, job_id=job_id, commit=commit)

    def cancel_job(self, job_id, user_id):
        from app.job_queue import queue_manager
        with state_change_lock:
            row, owner = _row(job_id)
            if row is None or row.user_id != str(user_id):
                raise LookupError('Video job not found.')
            if not is_available(owner):
                raise ValueError(f'Enable {owner} before controlling its queue.')
            return queue_manager.cancel_job(job_id, user_id)


queue = VideoQueue()
__all__ = ['QueueRecord', 'VideoQueue', 'job', 'queue']


def require_comfyui_enqueue_ready(*args, **kwargs):
    from app.job_queue import require_comfyui_enqueue_ready
    return require_comfyui_enqueue_ready(*args, **kwargs)


def annotate_checkpoint_steps(rows, dataset_id, run_id, paths):
    from app.plugins.hooks import run_filter
    return run_filter('video_lineage.checkpoints', rows, dataset_id, run_id, paths)


def battle_session():
    """Current cloud session of the independent Creature Battle product."""
    from .lifecycle import is_available, state_change_lock
    from importlib import import_module
    from .plugin_services import ServiceUnavailable
    with state_change_lock:
        if not is_available('creature_battle'):
            return None
        api = import_module('lds_creature_battle.public_api_v1')
        operation = getattr(api, 'battle_session', None)
        if getattr(api, 'API_VERSION', None) != 1 or not callable(operation):
            raise ServiceUnavailable('creature_battle', 'Update Creature Battle to use its cloud renderer.')
        return operation()

__all__ += ["require_comfyui_enqueue_ready", "annotate_checkpoint_steps", "battle_session"]
