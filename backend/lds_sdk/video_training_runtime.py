"""Named shared local-training lifecycle operations used by Video.

LDS retains process identity, global GPU locks and crash-safe training fences.
Video retains its target recipes, resources, launch policy and product state.
"""
from app.job_queue import GPU_ARBITER_LOCK

def aitoolkit_dir(*args, **kwargs):
    from app.services.lora_training import _aitoolkit_dir
    return _aitoolkit_dir(*args, **kwargs)


def assert_no_vision_pass_on_gpu(*args, **kwargs):
    from app.services.lora_training import _assert_no_vision_pass_on_gpu
    return _assert_no_vision_pass_on_gpu(*args, **kwargs)


def clear_training_identity(*args, **kwargs):
    from app.services.lora_training import _clear_training_identity
    return _clear_training_identity(*args, **kwargs)


def comfyui_free_before_training(*args, **kwargs):
    from app.services.lora_training import _comfyui_free_before_training
    return _comfyui_free_before_training(*args, **kwargs)


def comfyui_free_report(*args, **kwargs):
    from app.services.lora_training import _comfyui_free_report
    return _comfyui_free_report(*args, **kwargs)


def jobs_dir(*args, **kwargs):
    from app.services.lora_training import _jobs_dir
    return _jobs_dir(*args, **kwargs)


def output_dir(*args, **kwargs):
    from app.services.lora_training import _output_dir
    return _output_dir(*args, **kwargs)


def parse_training_log(*args, **kwargs):
    from app.services.lora_training import _parse_training_log
    return _parse_training_log(*args, **kwargs)


def record_training_process_identity(*args, **kwargs):
    from app.services.lora_training import _record_training_process_identity
    return _record_training_process_identity(*args, **kwargs)


def serial_local_launch(*args, **kwargs):
    from app.services.lora_training import _serial_local_launch
    return _serial_local_launch(*args, **kwargs)


def training_process_is_definitely_dead(*args, **kwargs):
    from app.services.lora_training import _training_process_is_definitely_dead
    return _training_process_is_definitely_dead(*args, **kwargs)


def venv_python(*args, **kwargs):
    from app.services.lora_training import _venv_python
    return _venv_python(*args, **kwargs)


def watch_training(*args, **kwargs):
    from app.services.lora_training import _watch_training
    return _watch_training(*args, **kwargs)


def assert_free_disk(*args, **kwargs):
    from app.services.lora_training import assert_free_disk
    return assert_free_disk(*args, **kwargs)


def assert_interpreter_ready(*args, **kwargs):
    from app.services.lora_training import assert_interpreter_ready
    return assert_interpreter_ready(*args, **kwargs)


def export_dataset_to_aitoolkit(*args, **kwargs):
    from app.services.lora_training import export_dataset_to_aitoolkit
    return export_dataset_to_aitoolkit(*args, **kwargs)


def free_disk_gb(*args, **kwargs):
    from app.services.lora_training import free_disk_gb
    return free_disk_gb(*args, **kwargs)


def is_installed(*args, **kwargs):
    from app.services.lora_training import is_installed
    return is_installed(*args, **kwargs)


def parse_download_progress(*args, **kwargs):
    from app.services.lora_training import parse_download_progress
    return parse_download_progress(*args, **kwargs)


def stop_training(*args, **kwargs):
    from app.services.lora_training import stop_training
    return stop_training(*args, **kwargs)


def training_subprocess_env(*args, **kwargs):
    from app.services.lora_training import training_subprocess_env
    return training_subprocess_env(*args, **kwargs)


from app.services.lora_training import MIN_FREE_GB_TRAIN as MIN_FREE_GB_TRAIN  # noqa: E402 — shared fence identity
from app.services.lora_training import _PROG_LOG_MAX_BYTES as PROG_LOG_MAX_BYTES  # noqa: E402 — shared fence identity
from app.services.lora_training import _TRAIN_STATE_TTL as TRAIN_STATE_TTL  # noqa: E402 — shared fence identity
from app.services.lora_training import _queue_lock as queue_lock  # noqa: E402 — shared fence identity

__all__ = ['GPU_ARBITER_LOCK', 'MIN_FREE_GB_TRAIN', 'PROG_LOG_MAX_BYTES', 'TRAIN_STATE_TTL', 'aitoolkit_dir', 'assert_no_vision_pass_on_gpu', 'clear_training_identity', 'comfyui_free_before_training', 'comfyui_free_report', 'jobs_dir', 'output_dir', 'parse_training_log', 'queue_lock', 'record_training_process_identity', 'serial_local_launch', 'training_process_is_definitely_dead', 'venv_python', 'watch_training', 'assert_free_disk', 'assert_interpreter_ready', 'export_dataset_to_aitoolkit', 'free_disk_gb', 'is_installed', 'parse_download_progress', 'stop_training', 'training_subprocess_env']
