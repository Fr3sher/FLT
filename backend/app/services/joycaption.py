"""JoyCaption Beta One LoRA dataset captioning through a subprocess.

Run Llava 8B NF4 in ai-toolkit's torch/transformers/bitsandbytes venv,
not Flask's Python. Load once for the entire batch rather than per
image. Missing/failed inference is nonfatal and returns {}; the caller
falls back to Qwen3-VL or honors the explicitly selected backend."""
from __future__ import annotations
from ..timeout_settings import processing_timeout

import collections
import json
import logging
import os
import subprocess
import threading
import time

from .. import config as cfg
from . import infer_env

logger = logging.getLogger(__name__)

# joycaption_infer.py lives in backend/infer, not app/services.
_SCRIPT = cfg.BACKEND_DIR / 'infer' / 'joycaption_infer.py'


def availability() -> dict:
    """Single source of truth for JoyCaption readiness: the capability probe.
    Returns {ok, detail} — `detail` names what's missing (the exact pip command
    for the ai-toolkit venv when the deps aren't importable). Delegating here means
    is_available() can't drift from what the Settings UI advertises (issue #6: the
    old filesystem-only check said "ready" while transformers was absent)."""
    from .. import capabilities
    return capabilities.probe_joycaption()


def is_available() -> bool:
    """True only when the ai-toolkit venv + script exist AND the venv can import the
    JoyCaption deps (transformers/bitsandbytes/accelerate) — otherwise the batch
    subprocess would ModuleNotFoundError. See availability() for the reason string."""
    return availability()['ok']


def _reflect_stage(line: str, activity_token) -> None:
    """Mirror one of the infer script's own ``[joycaption] …`` markers into the dataset
    activity indicator so the UI shows a live stage ("first run: downloading …",
    "model loaded", per-image progress) instead of a frozen "Loading…". Raw Hugging Face
    tqdm download bars (no ``[joycaption]`` prefix) go to the log only, keeping the UI
    detail readable. Non-fatal: never let progress reflection break captioning."""
    if not activity_token or not line.startswith('[joycaption]'):
        return
    try:
        from . import dataset_activity
        dataset_activity.progress(activity_token, detail=line[len('[joycaption]'):].strip()[:200])
    except Exception:  # noqa: BLE001
        pass


def caption_images_joycaption(paths, prompt: str | None = None,
                              max_tokens: int = 300, timeout: int = 1800,
                              activity_token=None, should_cancel=None,
                              errors_out=None) -> dict:
    """Caption an image list with one model load. Return {path: caption},
    or {} for nonfatal unavailability/failure.

    Stream subprocess stderr line by line into app logs via a reader thread.
    The first run downloads about 7 GB from Hugging Face; without visible
    loading/download/error progress the app appeared frozen (issue #6).
    Optional activity_token also updates persistent dataset activity.

    Poll should_cancel at image boundaries. Stream each caption immediately
    and retain completed work; on cancellation terminate the worker between
    images and return collected captions. This matches Ollama's stop-rest/
    keep-written contract rather than letting an entire batch continue
    after the UI says Stopping.
    Optional errors_out maps refused image paths to reasons. Per-image
    failures do not abort the batch, but their explanations must be
    available beyond server logs."""
    paths = [p for p in (paths or []) if p and os.path.isfile(p)]
    if not paths or not is_available():
        return {}
    payload = json.dumps({'images': paths, 'prompt': prompt, 'max_tokens': max_tokens})
    venv_python = str(cfg.aitoolkit_path('venv_python'))
    script = str(_SCRIPT)
    # HF_HOME shares the training cache. Also pass the image input budget
    # to the separate worker interpreter: otherwise its old 16 Mi-pixel/8192
    # limits reject DSLR/phone originals accepted under the configured
    # (default 64 Mi-pixel/16384) budget. Vision downsizes to 384 square
    # anyway, so full-size images are held only briefly.
    from .input_budget import infer_worker_env
    env = infer_env.worker_env(venv_python,
                               HF_HOME=str(cfg.aitoolkit_path('hf_home')),
                               PYTHONIOENCODING='utf-8', **infer_worker_env())
    started = time.monotonic()
    logger.info('joycaption: starting batch (%d image(s), timeout=%ss)', len(paths), timeout)
    try:
        proc = subprocess.Popen(
            infer_env.worker_argv(venv_python, script),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, cwd=os.path.dirname(script), text=True,
            encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError as e:
        logger.error('joycaption: could not start subprocess after %.1fs: %s',
                     time.monotonic() - started, e)
        return {}

    # Drain both pipes in threads: stderr is logged live (first-run download visibility),
    # stdout is streamed LINE BY LINE and parsed as each per-image caption lands. Reading
    # both concurrently avoids the pipe-buffer deadlock a naive proc.wait() would hit on a
    # chatty subprocess, and lets us enforce the timeout via proc.wait() while the readers
    # keep draining. Streaming stdout (rather than one end-of-run .read()) is what makes a
    # graceful Stop keep the captions already produced.
    captions: dict[str, str] = {}
    errors: dict[str, str] = {}
    cancelled = {'flag': False}
    stderr_tail: collections.deque = collections.deque(maxlen=25)

    def _consume_json_line(line: str) -> None:
        """Parse one stdout JSON line: a per-image {i,path,caption|error}, or the final
        {captions,errors} aggregate (merged defensively for a stale worker)."""
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            return
        if not isinstance(obj, dict):
            return
        if 'path' in obj:
            p = obj['path']
            if obj.get('caption'):
                captions[p] = str(obj['caption']).strip()
            elif obj.get('error'):
                errors[p] = str(obj['error'])
        elif 'captions' in obj:
            for p, cap in (obj.get('captions') or {}).items():
                if cap and p not in captions:
                    captions[p] = str(cap).strip()
            errors.update(obj.get('errors') or {})

    def _drain_stdout():
        try:
            for raw in proc.stdout:
                line = raw.strip()
                if line.startswith('{'):
                    _consume_json_line(line)
                    # Graceful Stop seam: we just captured an image's caption, so killing
                    # here loses nothing already produced. The next generate() (possibly
                    # long) never starts.
                    if should_cancel and not cancelled['flag'] and should_cancel():
                        cancelled['flag'] = True
                        logger.info('joycaption: stop requested — killing batch after '
                                    '%d caption(s)', len(captions))
                        try:
                            proc.kill()
                        except Exception:  # noqa: BLE001
                            pass
                        break
        except Exception:  # noqa: BLE001
            pass

    def _drain_stderr():
        try:
            for raw in proc.stderr:
                line = raw.rstrip('\n')
                if not line:
                    continue
                stderr_tail.append(line)
                logger.info('joycaption[sub]: %s', line)
                _reflect_stage(line, activity_token)
        except Exception:  # noqa: BLE001
            pass

    t_out = threading.Thread(target=_drain_stdout, daemon=True)
    t_err = threading.Thread(target=_drain_stderr, daemon=True)
    t_out.start()
    t_err.start()
    try:
        proc.stdin.write(payload)
        proc.stdin.close()
    except OSError:
        pass
    try:
        proc.wait(timeout=processing_timeout(timeout))
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        t_out.join(timeout=5)
        t_err.join(timeout=5)
        # The dominant cause of a first-run timeout is the ~7 GB model download, not a
        # hang — say so, and note the download is cached so a re-run resumes instead of
        # restarting from zero. Anything already streamed is still returned below.
        logger.error('joycaption: timed out after %.1fs while processing %d image(s) — '
                     'if this was the FIRST run the ~7 GB model was still downloading; '
                     'the partial download is cached, so just run captioning again to '
                     'resume. Last subprocess output: %s',
                     time.monotonic() - started, len(paths),
                     ' | '.join(list(stderr_tail)[-5:]) or '(none)')
    t_out.join(timeout=5)
    t_err.join(timeout=5)

    # `captions`/`errors` were filled by the stdout drain as each per-image line arrived, so
    # a graceful Stop (or a timeout) still returns everything produced so far.
    result = {k: v for k, v in captions.items() if v}
    if errors_out is not None:
        errors_out.update(errors)
    if errors:
        logger.info('joycaption: %d image error(s): %s',
                    len(errors), list(errors.values())[:3])
    if not result and not cancelled['flag'] and not errors:
        logger.warning('joycaption: no captions (rc=%s) stderr=%s',
                       proc.returncode, ' | '.join(list(stderr_tail)[-6:]))
    logger.info('joycaption: batch %s (%d/%d captioned, elapsed=%.1fs)',
                'stopped' if cancelled['flag'] else 'finished',
                len(result), len(paths), time.monotonic() - started)
    return result
