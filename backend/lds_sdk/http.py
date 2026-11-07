"""Flask responses shared with the host, including its stalled-job barrier."""


def map_error(error):
    from app.routes._common import _map_error
    return _map_error(error)


def require_idle_comfy():
    """Return the host's refusal response for stalled jobs, otherwise None.

    This is a stalled-result barrier, not a promise of exclusive GPU ownership;
    normal queue admission performs its own concurrency checks.
    """
    from app.routes._common import _require_no_stalled_comfyui
    return _require_no_stalled_comfyui()


__all__ = ['map_error', 'require_idle_comfy']
