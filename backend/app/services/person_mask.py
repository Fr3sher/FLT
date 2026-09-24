"""Person-mask generation using rembg/u2net in a dedicated interpreter,
outside Flask's venv, like face_similarity.py. CPU onnxruntime leaves
GPU/ComfyUI untouched.
Masked training (jandordoe method) uses one mask per training image;
ai-toolkit weights background by mask_min_value (0.1) so identity binds
to the subject rather than the setting."""
from __future__ import annotations
from ..timeout_settings import processing_timeout
import json
import logging
import os
import subprocess
import sys

from .. import config as cfg
from . import infer_env

logger = logging.getLogger(__name__)

# mask_infer.py lives in backend/infer, not app/services.
_SCRIPT = str(cfg.BACKEND_DIR / 'infer' / 'mask_infer.py')


def _mask_python() -> str:
    return cfg.get('masks.python') or sys.executable


def is_available() -> bool:
    from ..capabilities import probe_masks
    return probe_masks()['ok']


def generate_person_masks(image_paths, out_dir, timeout: int = 1200) -> dict:
    """Generate one same-basename PNG mask per image in out_dir. Return
    {ok: bool, written: N, results: {path: state}}, or {} on unavailability/
    failure. Never block training: training without masks remains valid."""
    image_paths = [p for p in (image_paths or []) if p and os.path.isfile(p)]
    if not image_paths or not is_available():
        return {}
    payload = json.dumps({"images": image_paths, "out_dir": out_dir})
    try:
        proc = subprocess.run(infer_env.worker_argv(_mask_python(), _SCRIPT),
                              input=payload,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=processing_timeout(timeout),
                              env=infer_env.worker_env(_mask_python()),
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning('person_mask: subprocess failed: %s', e)
        return {}
    line = next((ln for ln in reversed((proc.stdout or '').splitlines())
                 if ln.strip().startswith('{')), '')
    if not line:
        logger.warning('person_mask: no JSON (rc=%s) stderr=%s',
                       proc.returncode, (proc.stderr or '')[-400:])
        return {}
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning('person_mask: unreadable JSON: %s', e)
        return {}
    if not data.get('ok'):
        logger.warning('person_mask: failed: %s', data.get('error'))
        return {}
    return data
