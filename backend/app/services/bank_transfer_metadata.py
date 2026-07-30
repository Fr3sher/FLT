"""Durable metadata carried between Image Banks and face datasets.

The two containers deliberately own separate image files.  A Bank -> Dataset
promotion therefore needs more than the ``bank_image_id`` back-link: the Bank's
per-image analysis must travel with the copied Dataset image so a later
Dataset -> Bank import can recover it.  The snapshot carries a full-content
integrity fingerprint of the exact bytes written to the Dataset.  If that file
is edited later, consumers keep the safe user-authored fields but discard the
stale pixel analysis.

Only independent per-image measurements belong in this snapshot.  Group and
cluster ids are meaningful only in their original Bank, and rotation/cleaning
markers would make a destination apply an already-materialised transformation a
second time.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re


SNAPSHOT_VERSION = 2
_MAX_SNAPSHOT_JSON_BYTES = 8 * 1024
_FINGERPRINT_RE = re.compile(r'^[0-9a-f]{64}$')

# These values are reproducible from a decoded image without an ML model.  A
# Dataset snapshot is deliberately limited to this list: it records what the
# *final normalized WebP* measures, never a historical source-file verdict.
DETERMINISTIC_ANALYSIS_FIELDS = (
    'quality_state',
    'blur_score',
    'noise_score',
    'uniformity_score',
    'dhash',
    'detail_ratio',
    'bars_ratio',
    'jpeg_quality',
    'origin',
    'origin_evidence',
)

# These ML-derived values are meaningful only for the exact Bank file a model
# saw.  They are never serialised in a Dataset snapshot.  A direct Bank -> Bank
# copy may retain them because it copies unchanged source bytes; a resolved
# clean/rotated copy must clear them and remeasure only the deterministic set.
MODEL_ANALYSIS_FIELDS = (
    'face_state',
    'face_det',
    'aesthetic_score',
    'nsfw_score',
)

# Kept as the Bank-row convenience set.  Do not use it for snapshot payloads.
PIXEL_ANALYSIS_FIELDS = DETERMINISTIC_ANALYSIS_FIELDS + MODEL_ANALYSIS_FIELDS

_TEXT_LIMITS = {
    'quality_state': 12,
    'dhash': 16,
    'origin': 8,
    'origin_evidence': 24,
}


def content_fingerprint_bytes(data: bytes | bytearray) -> str | None:
    """Return a full SHA-256 integrity fingerprint for transferred bytes.

    This intentionally does *not* reuse run_snapshot's sampled large-file
    fingerprint.  Transfer restoration promises that the copied Dataset bytes
    are unchanged, so a mutation in the middle of a large image must be caught.
    """
    if not isinstance(data, (bytes, bytearray)):
        return None
    return hashlib.sha256(data).hexdigest()


def content_fingerprint_path(path: str | os.PathLike | None) -> str | None:
    """Return a full transfer integrity fingerprint, never raising on a missing file."""
    if not path:
        return None
    try:
        digest = hashlib.sha256()
        with open(path, 'rb') as fh:
            while True:
                chunk = fh.read(1 << 20)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _normalized_analysis(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    # Require the exact v2 fields before inspecting values. Besides keeping the
    # stored schema versioned and bounded, this refuses a deeply nested junk
    # branch without walking it.
    if set(value) != set(DETERMINISTIC_ANALYSIS_FIELDS):
        return None
    out = {}
    for name in DETERMINISTIC_ANALYSIS_FIELDS:
        item = value.get(name)
        if item is None:
            out[name] = None
            continue
        if name in _TEXT_LIMITS:
            if not isinstance(item, str) or len(item) > _TEXT_LIMITS[name]:
                return None
            if name == 'dhash' and not re.fullmatch(r'[0-9a-fA-F]{16}', item):
                return None
            if name == 'quality_state' and item not in ('ok', 'unreadable'):
                return None
            if name == 'origin' and item not in ('ai', 'camera', 'unknown'):
                return None
            out[name] = item
            continue
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        try:
            if not math.isfinite(item):
                return None
        except (TypeError, OverflowError):
            return None
        out[name] = float(item)
    return out


def snapshot_storage(analysis, image_bytes: bytes | bytearray) -> str | None:
    """Store final-WebP deterministic analysis with its integrity fingerprint."""
    analysis = _normalized_analysis(analysis)
    fingerprint = content_fingerprint_bytes(image_bytes)
    if analysis is None or fingerprint is None:
        return None
    try:
        return json.dumps({
            'v': SNAPSHOT_VERSION,
            'fingerprint': fingerprint,
            'analysis': analysis,
        }, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    except (TypeError, ValueError, RecursionError, MemoryError):
        return None


def parse_snapshot(value) -> dict | None:
    """Return one strictly-shaped stored snapshot, or ``None`` for legacy/bad data."""
    if isinstance(value, str):
        # A snapshot only has fixed-width strings/numbers; accepting a megabyte
        # of JSON here buys no compatibility and makes backup restore an avoidable
        # parser attack surface. Check chars first (cheap), then actual UTF-8 size.
        if len(value) > _MAX_SNAPSHOT_JSON_BYTES:
            return None
        try:
            if len(value.encode('utf-8')) > _MAX_SNAPSHOT_JSON_BYTES:
                return None
            value = json.loads(value)
        except (TypeError, ValueError, UnicodeError, RecursionError, MemoryError):
            return None
    if (not isinstance(value, dict) or len(value) != 3
            or set(value) != {'v', 'fingerprint', 'analysis'}
            or value.get('v') != SNAPSHOT_VERSION):
        return None
    fingerprint = value.get('fingerprint')
    if not isinstance(fingerprint, str) or not _FINGERPRINT_RE.fullmatch(fingerprint):
        return None
    analysis = _normalized_analysis(value.get('analysis'))
    if analysis is None:
        return None
    return {'v': SNAPSHOT_VERSION, 'fingerprint': fingerprint, 'analysis': analysis}


def normalized_snapshot_storage(value) -> str | None:
    """Canonicalize a persisted snapshot for a Dataset backup restore."""
    snapshot = parse_snapshot(value)
    if snapshot is None:
        return None
    try:
        return json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'),
                          sort_keys=True)
    except (TypeError, ValueError, RecursionError, MemoryError):
        return None


def compatible_analysis(value, path: str | os.PathLike | None) -> dict | None:
    """Return analysis only when ``path`` is still the snapshotted file bytes."""
    snapshot = parse_snapshot(value)
    if snapshot is None:
        return None
    if content_fingerprint_path(path) != snapshot['fingerprint']:
        return None
    return dict(snapshot['analysis'])
