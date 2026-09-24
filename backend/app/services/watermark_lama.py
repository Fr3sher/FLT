"""LaMa watermark inpainting in a dedicated interpreter outside Flask's
venv, like person_mask.py/face_similarity.py. Auto/GPU/CPU device choice
reserves the exclusive GPU window only when CUDA is actually used.

Only masked-rectangle pixels change; the rest remains identical.
Watermark correction inpaints non-edge boxes covering at most 10%
of the image. Edge boxes are cropped in PIL without this module."""
from __future__ import annotations
from ..timeout_settings import processing_timeout
import json
import logging
import math
import os
import subprocess
import sys
import time

from .. import config as cfg
from . import infer_env

logger = logging.getLogger(__name__)

# lama_infer.py lives in backend/infer, not app/services.
_SCRIPT = str(cfg.BACKEND_DIR / 'infer' / 'lama_infer.py')
_cuda_probe = {'python': None, 'checked': 0.0, 'available': False}


def lama_python() -> str:
    # Use the dedicated setting, then existing rembg/InsightFace ML Python,
    # then the current interpreter. simple-lama shares requirements-ml.txt.
    # The public Install inpainting action uses this same resolver so
    # installation and runtime imports target the same environment.
    return cfg.get('watermark.python') or cfg.get('masks.python') or sys.executable


# Backward-compatible alias (the private name was the original entry point).
_lama_python = lama_python


def is_available() -> bool:
    from ..capabilities import probe_watermark_inpaint
    return probe_watermark_inpaint()['ok']


def _cuda_available() -> bool:
    """Probe CUDA in the same interpreter that runs LaMa (short cached subprocess)."""
    python = lama_python()
    now = time.monotonic()
    if _cuda_probe['python'] == python and now - _cuda_probe['checked'] < 60:
        return bool(_cuda_probe['available'])
    try:
        proc = subprocess.run(
            infer_env.worker_argv(
                python, '-c',
                'import torch; print("1" if torch.cuda.is_available() else "0")'),
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=processing_timeout(20),
            env=infer_env.worker_env(python),
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        available = proc.returncode == 0 and (proc.stdout or '').strip().endswith('1')
    except (subprocess.TimeoutExpired, OSError):
        available = False
    _cuda_probe.update(python=python, checked=now, available=available)
    return available


def resolve_device(requested=None) -> str:
    requested = (requested or cfg.get('watermark.device') or 'auto').lower()
    if requested not in ('auto', 'cuda', 'cpu'):
        raise RuntimeError(f"Unknown watermark device '{requested}'")
    if requested == 'cpu':
        return 'cpu'
    available = _cuda_available()
    if requested == 'cuda' and not available:
        raise RuntimeError('CUDA was selected for watermark cleaning but is not available in the configured ML Python environment')
    return 'cuda' if available else 'cpu'


def _stderr_tail(proc) -> str:
    return next((ln.strip() for ln in reversed((proc.stderr or '').splitlines())
                 if ln.strip()), '')


def _run_lama_payload(payload, timeout: int = 300) -> tuple[bool, dict | None]:
    """Run the LaMa worker while preserving its subprocess/JSON protocol."""
    image_path = payload.get('image_path')
    if not image_path or not os.path.isfile(image_path):
        return False, {'kind': 'failed', 'detail': 'image not found'}
    if not is_available():
        return False, {'kind': 'unavailable',
                       'detail': 'watermark inpainting is not installed (ML extras)'}
    payload_json = json.dumps(payload)
    try:
        proc = subprocess.run(infer_env.worker_argv(_lama_python(), _SCRIPT),
                              input=payload_json,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=processing_timeout(timeout),
                              env=infer_env.worker_env(_lama_python()),
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning('watermark_lama: subprocess failed: %s', e)
        return False, {'kind': 'failed', 'detail': str(e)}
    line = next((ln for ln in reversed((proc.stdout or '').splitlines())
                 if ln.strip().startswith('{')), '')
    if not line:
        tail = _stderr_tail(proc)
        logger.warning('watermark_lama: no JSON (rc=%s) stderr=%s',
                       proc.returncode, (proc.stderr or '')[-400:])
        return False, {'kind': 'failed',
                       'detail': tail or f'inpainter produced no output (rc={proc.returncode})'}
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning('watermark_lama: unreadable JSON: %s', e)
        return False, {'kind': 'failed', 'detail': f'unreadable inpainter output: {e}'}
    if not data.get('ok'):
        detail = data.get('error') or 'inpaint failed'
        logger.warning('watermark_lama: failed: %s', detail)
        return False, {'kind': 'failed', 'detail': detail}
    return True, None


def inpaint_watermarks(image_path, bboxes, timeout: int = 300, device: str = 'cpu') -> tuple[bool, dict | None]:
    """Inpaint normalized bboxes in one LaMa pass, modifying the image in
    place. Preserve the historical (ok, error) contract: error is None
    on success, otherwise contains kind/detail."""
    payload = {'image_path': str(image_path), 'bboxes': bboxes, 'device': device}
    return _run_lama_payload(payload, timeout=timeout)


def inpaint_watermark(image_path, bbox, timeout: int = 300, device: str = 'cpu') -> tuple[bool, dict | None]:
    """Compatibility adapter for the former single-rectangle call."""
    try:
        bbox = [float(value) for value in bbox]
        if len(bbox) != 4:
            raise ValueError('bbox must have 4 values')
        if not all(math.isfinite(value) for value in bbox):
            raise ValueError('bbox values must be finite')
    except Exception as e:
        return False, {'kind': 'failed', 'detail': f'payload: {e}'}
    x1, y1, x2, y2 = bbox
    left, right = sorted((x1, x2))
    top, bottom = sorted((y1, y2))
    normalized = [
        max(0.0, min(1.0, left)),
        max(0.0, min(1.0, top)),
        max(0.0, min(1.0, right)),
        max(0.0, min(1.0, bottom)),
    ]
    return inpaint_watermarks(image_path, [normalized], timeout=timeout, device=device)


def inpaint_batch(jobs, *, device: str, timeout: int = 900) -> dict:
    """Run multiple image jobs in one worker so SimpleLama is loaded only once."""
    normalized = []
    for job in jobs or []:
        path = str(job.get('image_path') or '')
        if not path or not os.path.isfile(path):
            raise ValueError(f'image not found: {path}')
        normalized.append({'image_path': path, 'bboxes': job.get('bboxes') or []})
    if not normalized:
        return {}
    if not is_available():
        err = {'kind': 'unavailable', 'detail': 'watermark inpainting is not installed (ML extras)'}
        return {job['image_path']: (False, err) for job in normalized}
    payload_json = json.dumps({'jobs': normalized, 'device': device})
    try:
        proc = subprocess.run(infer_env.worker_argv(lama_python(), _SCRIPT),
                              input=payload_json,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=processing_timeout(timeout),
                              env=infer_env.worker_env(lama_python()),
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.TimeoutExpired, OSError) as e:
        err = {'kind': 'failed', 'detail': str(e)}
        return {job['image_path']: (False, err) for job in normalized}
    line = next((ln for ln in reversed((proc.stdout or '').splitlines())
                 if ln.strip().startswith('{')), '')
    try:
        data = json.loads(line) if line else {}
    except json.JSONDecodeError:
        data = {}
    if not data.get('ok'):
        err = {'kind': 'failed', 'detail': data.get('error') or _stderr_tail(proc) or 'inpaint worker failed'}
        return {job['image_path']: (False, err) for job in normalized}
    by_path = {}
    for item in data.get('results') or []:
        path = str(item.get('image_path') or '')
        err = None if item.get('ok') else {'kind': 'failed', 'detail': item.get('error') or 'inpaint failed'}
        by_path[path] = (bool(item.get('ok')), err)
    return {job['image_path']: by_path.get(job['image_path'], (False, {'kind': 'failed', 'detail': 'missing worker result'}))
            for job in normalized}
