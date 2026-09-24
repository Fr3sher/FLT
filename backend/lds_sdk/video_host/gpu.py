"""Named gpu operations shared with the host; no module handle escapes."""

def gpu_exclusive_vision_window(*args, **kwargs):
    from app.gpu_window import gpu_exclusive_vision_window
    return gpu_exclusive_vision_window(*args, **kwargs)


from app.gpu_window import GpuBusyError as GpuBusyError  # noqa: E402 — stable value/type identity

__all__ = ['gpu_exclusive_vision_window', 'GpuBusyError', 'ensure_released_for_comfy', 'release_vision_for_comfy', 'vision_block', 'vision_block_message']


def ensure_released_for_comfy(*args, **kwargs):
    from app.services.ollama_gpu_fence import ensure_released_for_comfy
    return ensure_released_for_comfy(*args, **kwargs)


def release_vision_for_comfy(reason):
    from app.services.vision_keepalive import ensure_released_for_comfy
    return ensure_released_for_comfy(reason)


def vision_block():
    from app.services.ollama_gpu_fence import last_block
    return dict(last_block() or {})


def vision_block_message():
    from app.services.ollama_gpu_fence import blocked_message
    return blocked_message()


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'GpuBusyError': ('app.gpu_window', 'GpuBusyError'),
 'gpu_exclusive_vision_window': ('app.gpu_window',
                                 'gpu_exclusive_vision_window')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
