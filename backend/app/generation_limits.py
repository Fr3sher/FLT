"""Operator controls for long local generation runs."""
from . import config as cfg


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


def generation_timeout_seconds():
    minutes = _comfy_integer('generation_timeout_minutes', 0, 1440)
    return minutes * 60 if minutes else float('inf')
