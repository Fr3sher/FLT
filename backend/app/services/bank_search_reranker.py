"""Bounded optional refinement; owns no persistent model or image cache."""
from contextlib import nullcontext
import hashlib
import json
import math
import subprocess
import threading
import time

from .. import config as cfg
from . import bank_reranker_models as assets
from . import infer_env

_lock = threading.Lock()
TIMEOUT = 600


class RerankError(RuntimeError):
    pass


def status():
    from ..capabilities import probe_bank_reranker
    probe = probe_bank_reranker()
    try:
        device = assets.device()
    except ValueError:
        device = 'unknown'
    return {'available': probe['ok'], 'reason': probe['detail'],
            'model_key': assets.MODEL_KEY, 'top_n': assets.TOP_N,
            'device': device, 'busy': _lock.locked(), 'warm': False}


def validate_results(data, images):
    rows = data.get('results') if isinstance(data, dict) and data.get('ok') is True else None
    if not isinstance(rows, list) or len(rows) != len(images):
        raise RerankError('Qwen refinement failed; try again or turn refinement off.')
    expected = {r['id'] for r in images}
    seen = set()
    scores = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get('id')) is not int:
            raise RerankError('Qwen returned an invalid candidate.')
        image_id, score = row['id'], row.get('score')
        if (image_id not in expected or image_id in seen or isinstance(score, bool)
                or not isinstance(score, (int, float)) or not math.isfinite(score)
                or not 0 <= score <= 1):
            raise RerankError('Qwen returned an invalid ranking.')
        seen.add(image_id)
        scores[image_id] = float(score)
    return scores


def rerank(query, images):
    if not images or len(images) > assets.TOP_N:
        raise ValueError('Qwen refinement needs between 1 and 20 candidates')
    if not _lock.acquire(blocking=False):
        raise RerankError('Another Qwen refinement is running; try again shortly.')
    try:
        ready = status()
        if not ready['available']:
            raise RerankError(ready['reason'])
        from ..gpu_window import GpuBusyError, gpu_exclusive_vision_window
        device = assets.device()
        window = gpu_exclusive_vision_window(flag_ttl=TIMEOUT + 60) if device == 'cuda' else nullcontext()
        python = assets.inference_python()
        env = infer_env.worker_env(python, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                                   HF_HUB_DISABLE_PROGRESS_BARS='1')
        from .input_budget import infer_worker_env
        env.update(infer_worker_env())
        if device == 'cpu':
            env['CUDA_VISIBLE_DEVICES'] = ''
        payload = {'query': query, 'images': images, 'device': device,
                   'model_path': str(assets.snapshot_dir())}
        started = time.monotonic()
        try:
            with window:
                proc = subprocess.run(
                    infer_env.worker_argv(python, cfg.BACKEND_DIR / 'infer' / 'qwen_reranker_infer.py'),
                    input=json.dumps(payload), capture_output=True, text=True,
                    encoding='utf-8', errors='replace', env=env, timeout=TIMEOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except GpuBusyError as exc:
            raise RerankError(str(exc)) from None
        except subprocess.TimeoutExpired:
            raise RerankError('Qwen refinement timed out; its worker was stopped. '
                              'Try fewer candidates or turn refinement off.') from None
        except OSError:
            raise RerankError('The Qwen interpreter could not start; repair it in Setup.') from None
        try:
            data = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise RerankError('Qwen returned no usable result; repair it in Setup.') from None
        if proc.returncode:
            raise RerankError('Qwen refinement failed; check the model runtime in Setup '
                              'or turn refinement off.')
        scores = validate_results(data, images)
        # The child checked the bytes it decoded. Reject replacements made while
        # the model ran rather than presenting a score for a previous generation.
        from .image_bank_service import _read_safe_bank_source_bytes
        for item in images:
            try:
                current = hashlib.sha256(_read_safe_bank_source_bytes(item['path'])).hexdigest()
            except (OSError, ValueError):
                raise RerankError('A candidate changed; run the search again.') from None
            if current != item['sha256']:
                raise RerankError('A candidate changed; run the search again.')
        ranked = sorted(images, key=lambda r: -scores[r['id']])
        return [r['id'] for r in ranked], {
            'model_key': assets.MODEL_KEY, 'count': len(images), 'device': device,
            'seconds': round(time.monotonic() - started, 3), 'scores': scores}
    finally:
        _lock.release()
