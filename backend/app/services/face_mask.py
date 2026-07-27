"""Face masks for CONCEPT training — the INVERSE polarity of person_mask.py.

person_mask.py answers "learn the subject, not the room": person white, background
black, background weighted to 10% of the loss.

This module answers the opposite question, raised by shivdbz2010 (GitHub issue #15):
a concept LoRA also learns the FACES of its dataset, so combining it with a character
LoRA makes the two fight over the identity. Masking the faces during concept training
teaches the act without the identity.

It is a LOSS mask, not an image edit — ai-toolkit multiplies the per-pixel loss by
the mask (white 1.0, black -> mask_min_value). Nothing is painted into the training
image. Blurring or pixelating the faces instead would make the blur the regression
TARGET, and the LoRA would learn to render blurred faces.

Runs InsightFace in the DEDICATED ML interpreter (face_scoring.python), like
face_similarity.py — insightface is not in the Flask venv. Note it needs
`face_scoring`, NOT `masks`/rembg: an install with face scoring but no rembg can
still mask faces.
"""
from __future__ import annotations
import json
import logging
import os
import subprocess
import sys

from .. import config as cfg

logger = logging.getLogger(__name__)

_SCRIPT = str(cfg.BACKEND_DIR / 'infer' / 'face_mask_infer.py')

# Bounds for the two exposed knobs. Clamping happens SERVER-side so a hand-edited
# config.json (or a stale UI) degrades to a usable value instead of killing an
# export halfway through: a bad number must never be the reason a training run dies.
EXPAND_MIN, EXPAND_MAX = 1.0, 3.0
# The floor is NOT 0.0. A zero-weight region is not ignored, it is unpenalised (the
# model may render anything there for free), and ai-toolkit divides the mask by its
# own mean — an all-black mask would divide by zero and NaN the run. See config.py.
MIN_WEIGHT_MIN, MIN_WEIGHT_MAX = 0.05, 1.0


def _clamp(value, low, high, fallback):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    if v != v:  # NaN
        return fallback
    return max(low, min(high, v))


def expand_factor() -> float:
    """Configured face->head growth factor, clamped. 2.0 is the shipped default."""
    return _clamp(cfg.get('face_mask.expand'), EXPAND_MIN, EXPAND_MAX,
                  cfg.defaults()['face_mask']['expand'])


def min_weight() -> float:
    """Configured loss weight left inside the mask, clamped away from zero."""
    return _clamp(cfg.get('face_mask.min_weight'), MIN_WEIGHT_MIN, MIN_WEIGHT_MAX,
                  cfg.defaults()['face_mask']['min_weight'])


def is_available() -> bool:
    from ..capabilities import probe_face_scoring
    return probe_face_scoring()['ok']


def _face_python() -> str:
    return cfg.get('face_scoring.python') or sys.executable


def _run(images, out_dir, expand, timeout) -> dict:
    images = [p for p in (images or []) if p and os.path.isfile(p)]
    if not images or not is_available():
        return {}
    payload = json.dumps({'images': images, 'out_dir': out_dir, 'expand': expand,
                          'models_root': cfg.get('face_scoring.models_root') or None})
    try:
        proc = subprocess.run([_face_python(), _SCRIPT], input=payload,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=timeout,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning('face_mask: subprocess échec : %s', e)
        return {}
    line = next((ln for ln in reversed((proc.stdout or '').splitlines())
                 if ln.strip().startswith('{')), '')
    if not line:
        logger.warning('face_mask: pas de JSON (rc=%s) stderr=%s',
                       proc.returncode, (proc.stderr or '')[-400:])
        return {}
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        logger.warning('face_mask: JSON illisible : %s', e)
        return {}
    if not data.get('ok'):
        logger.warning('face_mask: échec : %s', data.get('error'))
        return {}
    return data


def generate_face_masks(image_paths, out_dir, expand=None, timeout: int = 1800) -> dict:
    """Write one mask PNG per image (face black, frame white) into `out_dir`.
    Returns {'ok', 'written', 'results'}; {} on any failure/unavailability —
    never blocking, exactly like generate_person_masks: a run without masks is
    still a valid run, it just trains the historical way."""
    return _run(image_paths, out_dir, expand if expand is not None else expand_factor(), timeout)


def detect_faces(image_paths, timeout: int = 900) -> dict:
    """Detection ONLY — no file written. Feeds the preview, which grows the raw
    boxes itself so moving the expand slider costs nothing (the same arithmetic
    lives in infer/face_mask_infer.dilate_box and utils/faceMaskBox.js)."""
    return _run(image_paths, None, expand_factor(), timeout)


def coverage_summary(results: dict) -> dict:
    """Fold a results map into the numbers the UI must show.

    `masked`/`total` is a SAFETY figure, not a statistic: a partially masked set is
    the worst outcome of all. The faces that stayed unmasked become the only ones
    carrying loss weight, so they end up over-represented in what the LoRA learns
    about faces — the "remaining guys have won" effect reported by the community
    workflow this feature follows. Surface it, do not bury it."""
    states = [(r or {}).get('state') for r in (results or {}).values()]
    total = len(states)
    return {
        'total': total,
        'masked': sum(1 for s in states if s == 'masked'),
        'no_face': sum(1 for s in states if s == 'no_face'),
        'too_large': sum(1 for s in states if s == 'too_large'),
        'failed': sum(1 for s in states if s in ('error', 'unreadable')),
    }
