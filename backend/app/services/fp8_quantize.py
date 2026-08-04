"""Quantize a checkpoint you ALREADY have, locally, to the fp8 file ComfyUI loads.

WHY THIS EXISTS ALONGSIDE THE POD EXPORT
----------------------------------------
The cloud lane produces the fp8 twin automatically at the end of a dense run. But
the models people want to shrink are not only the ones they trained today: a
25.6 GB bf16 full model already downloaded from Hugging Face, a dense checkpoint
from an earlier run, a big finetune someone shared. This is the same conversion,
started by hand, on a file on this machine.

It is deliberately the SAME implementation — ``fp8_export.export_scaled_fp8``.
There is exactly one definition of "the fp8 file LDS produces", it is unit tested
against real torch, and its output was fed to ComfyUI's own ``convert_old_quants``
to prove the loader accepts it. A second local-only quantizer would have been a
second format nobody would notice diverging.

NOT THE SAME THING AS ai-toolkit's `quantize`
---------------------------------------------
ai-toolkit's ``model.quantize`` (and the app's Advanced ▸ memory settings) quantize
the model IN MEMORY while it loads, so a 24 GB card can train something that would
not otherwise fit. It produces no file and changes nothing on disk — the saved
checkpoint is still full precision. THIS produces a file, and that file is the
artifact you load in ComfyUI. The help text says so, because the two are
constantly confused.

CPU, NOT GPU
------------
Quantization here is an elementwise cast plus one reduction per tensor. Measured
on this machine: ~1.2 GB/s of source through the streaming writer, i.e. under a
minute of compute for a 25.6 GB checkpoint — the run is bound by disk, not by
arithmetic. Putting it on the GPU would buy nothing and would fight ComfyUI and
any training run for VRAM. It stays on the CPU, and takes no GPU lock.
"""
from __future__ import annotations

import logging
import os
import threading

from ..job_queue import queue_manager
from . import fp8_export, model_integrity

logger = logging.getLogger(__name__)

# system_state key — one quantization at a time, app-wide. Two 25 GB reads and
# two multi-GB writes at once would be slower than doing them in sequence and
# could fill the drive between the two free-space checks.
_STATE_KEY = 'fp8_quantize'
_STATE_TTL = 6 * 3600
_lock = threading.Lock()

# A 26 GB source needs room for its ~13 GB output plus normal headroom. Checked
# BEFORE anything is read, so a full drive is a refusal, not a half-written file.
MIN_FREE_GB = 30

_ACCEPTED_EXT = ('.safetensors', '.sft')


class QuantizeError(ValueError):
    """Refusal with a sentence for the user. Never a stack trace."""


def status() -> dict:
    return queue_manager._get_system_state(_STATE_KEY, {}) or {}


def _free_gb(path) -> float | None:
    try:
        import shutil
        return shutil.disk_usage(os.path.dirname(os.path.abspath(path))).free / (1000 ** 3)
    except Exception:
        return None


def plan(source) -> dict:
    """Validate one source file and describe what quantizing it would produce.

    Raises ``QuantizeError`` with an actionable sentence for every refusal, so
    the button can be disabled with a reason instead of failing on click.
    """
    path = str(source or '').strip().strip('"')
    if not path:
        raise QuantizeError('choose a .safetensors model file to quantize')
    if not os.path.isabs(path):
        raise QuantizeError('give the full path to the model file')
    if not os.path.isfile(path):
        raise QuantizeError(f'no file at {os.path.basename(path)} — check the path')
    if not path.lower().endswith(_ACCEPTED_EXT):
        raise QuantizeError('only .safetensors checkpoints can be quantized '
                            '(a .gguf file is already quantized)')

    # The volet-3 guard, used in reverse: there it refuses a quantized file as a
    # TRAINING base; here it refuses to quantize something already quantized,
    # which would double the error and produce a file nothing can load.
    report = model_integrity.quantization_report(path)
    if report.get('quantized'):
        raise QuantizeError(
            f'{os.path.basename(path)} is already a quantized export '
            f'({", ".join(report.get("signals") or []) or "quantized dtypes"}) — '
            'quantizing it again would only lose more precision. Use the '
            'full-precision (bf16/fp16) version.')

    integrity = model_integrity.validate_model_file(path)
    if integrity.get('blocking'):
        raise QuantizeError(integrity.get('reason') or 'this file is not a readable model')

    header = fp8_export.read_header(path)          # raises Fp8ExportError -> caught below
    layout = fp8_export.plan_quantization(header)
    if not layout['quantize']:
        raise QuantizeError(
            f'{os.path.basename(path)} has no large 2-D weight matrices to '
            'quantize — this is a LoRA or an adapter, not a full model. '
            'Quantizing it would save nothing.')

    destination = os.path.join(os.path.dirname(path),
                               fp8_export.fp8_name_for(os.path.basename(path)))
    return {
        'source': path,
        'source_name': os.path.basename(path),
        'source_bytes': os.path.getsize(path),
        # Written NEXT TO the source, never over it: the master is the only file
        # that can be trained again, and a user who chose the wrong file must be
        # able to just delete the output.
        'destination': destination,
        'destination_name': os.path.basename(destination),
        'destination_exists': os.path.isfile(destination),
        'quantized_tensors': len(layout['quantize']),
        'kept_tensors': len(layout['keep']),
        'estimated_bytes': layout['bytes_after'],
        'free_gb': _free_gb(destination),
    }


def describe(source) -> dict:
    """``plan`` as a payload the UI can render, refusal included. Never raises —
    a disabled button with a reason beats an error toast on click."""
    try:
        return {'ok': True, **plan(source)}
    except (QuantizeError, fp8_export.Fp8ExportError) as e:
        return {'ok': False, 'error': str(e), 'source': str(source or '')}


def quantize(source, *, overwrite=False, progress=None) -> dict:
    """Do it (BLOCKING, minutes on a 26 GB file). Returns the verified summary."""
    info = plan(source)
    if info['destination_exists'] and not overwrite:
        raise QuantizeError(
            f'{info["destination_name"]} already exists next to the source — '
            'delete it first, or re-run with overwrite.')
    free = info['free_gb']
    if free is not None and free < MIN_FREE_GB:
        raise QuantizeError(
            f'not enough disk space: {free:.1f} GB free where the output would go, '
            f'~{MIN_FREE_GB} GB needed — free up space and retry')
    summary = fp8_export.export_scaled_fp8(
        info['source'], info['destination'],
        metadata={'lds_quantized_from': info['source_name']},
        progress=progress)
    return {**info, **summary, **verify(info['destination'])}


def verify(path) -> dict:
    """Re-open the file we just wrote and prove it is what we claimed.

    Same checks as the unit test, run on the REAL output: the fp8 marker, one
    per-tensor scale, and the payload dtype. A conversion that produced an
    unloadable file must say so here rather than at generation time, days later.
    """
    out = {'verified': False, 'verify_error': None}
    try:
        from safetensors import safe_open
        with safe_open(str(path), framework='pt') as fh:
            keys = list(fh.keys())
            if fp8_export.MARKER_KEY not in keys:
                raise ValueError('the scaled-fp8 marker is missing')
            marker = fh.get_tensor(fp8_export.MARKER_KEY)
            scales = [k for k in keys if k.endswith(fp8_export.SCALE_SUFFIX)]
            if not scales:
                raise ValueError('no per-tensor scale was written')
            weight = scales[0][:-len(fp8_export.SCALE_SUFFIX)] + '.weight'
            payload = fh.get_tensor(weight)
            scale = fh.get_tensor(scales[0])
        import torch
        if marker.dtype is not torch.float8_e4m3fn or marker.nelement() != 2:
            raise ValueError('the marker does not describe float8_e4m3fn weights')
        if payload.dtype is not torch.float8_e4m3fn:
            raise ValueError(f'{weight} was not written as float8_e4m3fn')
        if scale.dtype is not torch.float32 or scale.ndim != 0:
            raise ValueError('the per-tensor scale is not a float32 scalar')
        out.update(verified=True, scaled_tensors=len(scales))
    except Exception as e:                        # noqa: BLE001 — reported
        out['verify_error'] = str(e)[:300]
    return out


def start_async(app, source, *, overwrite=False) -> dict:
    """Run it in a daemon thread; progress and outcome live in system_state.

    Refuses immediately (before the thread) when another quantization is running
    or the source is not usable — a rejection the user sees on click, not in a
    status poll thirty seconds later.
    """
    info = plan(source)
    with _lock:
        if status().get('status') == 'running':
            raise QuantizeError('a quantization is already running — wait for it to finish')
        _set('running', info, done=0, total=0)

    def _run():
        with app.app_context():
            def on_progress(done, total):
                # Cheap and throttled by the tensor count itself (hundreds, not
                # millions), so every update is a real step forward.
                _set('running', info, done=done, total=total)
            try:
                result = quantize(info['source'], overwrite=overwrite,
                                  progress=on_progress)
                _set('error' if result.get('verify_error') else 'done', info,
                     result=result, error=result.get('verify_error'))
                logger.info('fp8 quantization finished: %s', info['destination_name'])
            except Exception as e:
                _set('error', info, error=str(e)[:400])
                logger.warning('fp8 quantization failed (%s): %s',
                               info['source_name'], e)

    threading.Thread(target=_run, daemon=True).start()
    return info


def _set(state, info, **extra):
    queue_manager._set_system_state(_STATE_KEY, {
        'status': state,
        'source_name': info['source_name'],
        'destination_name': info['destination_name'],
        'source_bytes': info['source_bytes'],
        'estimated_bytes': info['estimated_bytes'],
        **extra,
    }, ttl_seconds=_STATE_TTL)
