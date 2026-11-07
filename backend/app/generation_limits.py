"""Operator controls for long local generation runs."""
from . import config as cfg
from .timeout_settings import processing_timeout


def _comfy_integer(field, minimum, maximum):
    default = cfg.DEFAULTS['comfyui'][field]
    raw = cfg.get('comfyui.' + field)
    try:
        value = int(raw) if not isinstance(raw, bool) else default
    except (ValueError, TypeError, OverflowError):
        value = default
    return max(minimum, min(value, maximum))


def local_queue_limit():
    return _comfy_integer('local_queue_limit', 1, 10_000)


def generation_timeout_seconds(metadata=None):
    minutes = _comfy_integer('generation_timeout_minutes', 0, 1440)
    budget = processing_timeout(minutes * 60) if minutes else float('inf')
    # Synchronous repair/improve callers may need longer than the general
    # generation budget. Their finite/unlimited choice must reach the worker.
    override = (metadata or {}).get('processing_timeout_seconds') if isinstance(metadata, dict) else None
    if isinstance(override, (int, float)) and not isinstance(override, bool) and 0 <= override <= 8640000:
        budget = max(budget, override or float('inf'))
    return budget


def repair_timeout_seconds():
    return _operation_timeout('repair_timeout_minutes')


def improve_timeout_seconds():
    return _operation_timeout('improve_timeout_minutes')


def _operation_timeout(field):
    minutes = _comfy_integer(field, 0, 1440)
    return processing_timeout(minutes * 60) if minutes else float('inf')
