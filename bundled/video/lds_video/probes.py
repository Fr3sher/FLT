"""Public Video capability probes; ComfyUI results cached for one poll."""
from __future__ import annotations

import threading
import time
from copy import deepcopy

_TTL_S = 8.0
_lock = threading.Lock()
_cache: dict = {'at': 0.0, 'comfy_ok': False, 'classes': None}


def _comfy():
    """(comfy_ok, classes) — ComfyUI's reachability from the core's cheap probe,
    and its registered node classes when reachable, cached for _TTL_S."""
    now = time.monotonic()
    with _lock:
        if now - _cache['at'] < _TTL_S:
            return _cache['comfy_ok'], _cache['classes']
    from lds_sdk.video_host import capabilities
    from . import video_test_studio as vts
    ok = bool(capabilities.probe_comfyui().get('ok'))
    classes = vts.registered_classes() if ok else None
    with _lock:
        _cache.update(at=time.monotonic(), comfy_ok=ok, classes=classes)
    return ok, classes


def clear_cache():
    with _lock:
        _cache.update(at=0.0, comfy_ok=False, classes=None)


def video_studio_missing():
    from . import video_test_studio as vts
    return vts.missing_weights()


def video_studio_ready():
    from . import video_test_studio as vts
    return vts.studio_ready(vts.missing_weights())




def video_studio_options():
    # `available: null` per option means /object_info could not be read — the
    # panel keeps offering the option; a probe that could not run is not a verdict.
    from . import video_test_studio as vts
    ok, classes = _comfy()
    return vts.option_availability(classes=classes) if ok else {}


def video_studio_sage():
    # SageAttention is a speed patch the graph keeps when present and drops when
    # absent; published so the install card can link it.
    from . import video_test_studio as vts
    ok, _classes = _comfy()
    return {**vts.SAGE_PACK, 'present': vts.sage_available() if ok else None}








def video_host_ready():
    """Check the modules the bank imports in LDS, independently of video.python."""
    try:
        import av
        import cv2
        import numpy
        from curl_cffi import requests
        return all((callable(av.open), callable(cv2.VideoCapture),
                    callable(numpy.asarray), callable(requests.get)))
    except Exception:
        # An installed wheel whose native library cannot load is not ready.
        return False


def _video_piece(key):
    # Preserve main's three independently cached checks and interpreter choices.
    from lds_sdk.video_host.capabilities import probe_video
    return probe_video()[key]


def _when_enabled(fn, empty):
    def probe():
        from lds_sdk.lifecycle import is_available
        if not is_available('video'):
            return deepcopy(empty)
        return fn()
    return probe


PROBES = {
    'video': lambda: _video_piece('ok'),
    'video_detail': lambda: _video_piece('detail'),
    'video_decode': lambda: _video_piece('decode'),
    'video_detect': lambda: _video_piece('detect'),
    'video_encode': lambda: _video_piece('encode'),
    'video_host_ready': video_host_ready,
    'comfyui.video_studio_missing': video_studio_missing,
    'comfyui.video_studio_ready': video_studio_ready,
    'comfyui.video_studio_options': video_studio_options,
    'comfyui.video_studio_sage': video_studio_sage,
}

_EMPTY_PROBES = {'video_detail': '', 'comfyui.video_studio_missing': [],
                 'comfyui.video_studio_options': {}, 'comfyui.video_studio_sage': {}}
PROBES = {key: _when_enabled(fn, _EMPTY_PROBES.get(key, False)) for key, fn in PROBES.items()}
