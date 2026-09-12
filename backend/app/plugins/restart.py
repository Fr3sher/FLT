"""Apply plugin changes only after closing the server's work admissions.

The desktop supervisor owns the relaunch. On success the admission locks stay
held until that process exits: releasing them after scheduling would leave a
window in which a background scheduler could start work before the exit. A
failed safety check or failed scheduling releases everything immediately.
"""
from __future__ import annotations

import errno
import logging
import threading
from urllib.parse import urlsplit

from flask import current_app, g, jsonify, request
import requests

log = logging.getLogger(__name__)
_EXTENSION = 'lds_plugin_restart_gate'
_TOKEN = '_lds_plugin_mutation'
_BUSY = 'Work is still running or being admitted. Let it finish before applying plugin changes.'
_RESTARTING = 'LDS is restarting. Wait for it to reconnect before making changes.'
_ACTIVE_QUEUE = ('pending', 'processing', 'sent_to_comfy', 'cancel_requested', 'stalled')


class RestartBlocked(RuntimeError):
    pass


class _Gate:
    def __init__(self):
        self.lock = threading.Lock()
        self.writers = set()
        self.frozen = False
        self.held = []
        self.finished = threading.Event()

    def freeze(self):
        with self.lock:
            if self.frozen:
                raise RestartBlocked(_RESTARTING)
            if self.writers:
                raise RestartBlocked(_BUSY)
            self.frozen = True
            self.finished.clear()

    def acquire(self, lock):
        # Never wait while holding another lane's lock. Contention means that
        # this request cannot prove idleness; a later Apply can try again.
        if not lock.acquire(blocking=False):
            raise RestartBlocked(_BUSY)
        self.held.append(lock)

    def release(self):
        for lock in reversed(self.held):
            lock.release()
        self.held.clear()
        with self.lock:
            self.frozen = False
        self.finished.set()


def install_gate(app):
    """Register once, before the app serves any requests (including kill switch)."""
    if _EXTENSION in app.extensions:
        return
    gate = app.extensions[_EXTENSION] = _Gate()

    @app.before_request
    def plugin_restart_admission():
        if request.method in ('GET', 'HEAD', 'OPTIONS'):
            return None
        if request.method == 'POST' and request.path.rstrip('/') == '/api/plugins/apply':
            return None
        with gate.lock:
            if gate.frozen:
                return jsonify(error=_RESTARTING, code='restarting'), 503
            token = object()
            gate.writers.add(token)
            setattr(g, _TOKEN, token)
        return None

    @app.teardown_request
    def plugin_restart_release_request(_error):
        token = g.pop(_TOKEN, None)
        if token is not None:
            with gate.lock:
                gate.writers.discard(token)


def _plugin_blockers(registry):
    # Use THIS app's registry. Another test/tool app in the same interpreter
    # must not replace the safety checks with its process-global active view.
    def check(name, *args):
        value = []
        for _owner, callback in registry.hooks.get(name, ()):
            value = callback(value, *args)
            if not isinstance(value, (list, tuple)) or any(not isinstance(x, str) for x in value):
                raise RestartBlocked('A plugin could not confirm that its work has stopped.')
        if any(value):
            raise RestartBlocked(next(x for x in value if x))

    check('comfyui.restart_blockers')
    for plugin_id in registry.records:
        check('plugin.disable_blockers', plugin_id)


def _lock_and_check_work(gate, registry):
    from .. import setup_installer
    from ..extensions import db
    from ..gpu_window import vision_gpu_window_blocks_gpu
    from ..job_queue import GPU_ARBITER_LOCK, QUEUE_EXECUTION_LOCK, queue_execution_busy, queue_manager
    from ..models import ImageGenerationQueue
    from ..services import bank_jobs, dataset_activity, lora_training, ollama_control, reference_edit_jobs
    from . import environment
    from .lifecycle import state_change_lock

    # Cloud admissions, plugin scripts and Setup all reserve under this lock.
    gate.acquire(state_change_lock)
    _plugin_blockers(registry)

    # Auto takes its own reentrant lock before the GPU lock. A paused handoff
    # still needs a living supervisor, even when its worker thread has stopped.
    runner = current_app.extensions.get('video_auto_continue')
    if runner is not None:
        gate.acquire(runner.lock)
        state = runner.status()
        if runner._busy() or (state and (state.get('enabled') or state.get('draining') or state.get('job_id'))):
            raise RestartBlocked('Stop Auto continuation and let its current clip finish before applying plugin changes.')

    # Match the existing local launch order. The remaining acquisitions never
    # block, so an older request/worker with a different order cannot deadlock.
    for lock in (lora_training._launch_transaction_lock, lora_training._queue_lock,
                 GPU_ARBITER_LOCK, QUEUE_EXECUTION_LOCK, bank_jobs._lock, dataset_activity._lock,
                 reference_edit_jobs._lock, setup_installer._lock, ollama_control._pull_lock):
        gate.acquire(lock)

    # A terminal queue row may still be copying/associating its result. The
    # execution reservation covers that tail without holding the GPU lock.
    if queue_execution_busy():
        raise RestartBlocked('A generation result is still being finalized. Let it finish before applying plugin changes.')
    if any(not job.get('finished') for job in bank_jobs._jobs.values()):
        raise RestartBlocked('A bank operation is still running. Let it finish before applying plugin changes.')
    if ollama_control._pull and ollama_control._pull.get('state') == 'running':
        raise RestartBlocked('An Ollama model is still downloading. Let it finish before applying plugin changes.')
    if any(dataset_activity._active.values()):
        raise RestartBlocked('A dataset operation is still running. Let it finish before applying plugin changes.')
    if any(candidate.get('status') == 'running' for job in reference_edit_jobs._jobs.values()
           for candidate in job.get('candidates', {}).values()):
        raise RestartBlocked('A reference edit is still running. Let it finish before applying plugin changes.')
    if (any(run.get('state') in ('running', 'queued') for run in setup_installer._runs.values())
            or setup_installer._pip_current is not None or setup_installer._pip_queue
            or any(environment._RUNNING.values())):
        raise RestartBlocked('An installation or plugin script is still running. Let it finish before applying plugin changes.')
    if (vision_gpu_window_blocks_gpu()
            or queue_manager._get_system_state('training_in_progress')
            or queue_manager._get_system_state('vision_in_progress')
            or lora_training.get_train_queue()
            or ImageGenerationQueue.query.filter(ImageGenerationQueue.status.in_(_ACTIVE_QUEUE)).first()):
        raise RestartBlocked('Generation, training or captioning still needs this server. Finish or clear its queue before applying plugin changes.')
    # No SQLite read snapshot is needed across the bounded external queue read.
    db.session.rollback()


def _connection_refused(error):
    pending, seen = [error], set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        if isinstance(item, OSError) and (item.errno in (errno.ECONNREFUSED, 10061)
                                         or getattr(item, 'winerror', None) == 10061):
            return True
        pending.extend(x for x in (getattr(item, '__cause__', None),
                                   getattr(item, '__context__', None),
                                   getattr(item, 'reason', None),
                                   *getattr(item, 'args', ())) if isinstance(x, BaseException))
    return False


def _require_comfy_idle():
    from .. import config as cfg
    url = str(cfg.get('comfyui.api_url') or '').rstrip('/')
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise RestartBlocked('The ComfyUI address is invalid. Check it before applying plugin changes.')
        # Windows may take about two seconds to report a refused loopback
        # connection. A shorter budget turns that proof of absence into an
        # unknown timeout and blocks an explicitly skipped local ComfyUI.
        response = requests.get(f'{url}/queue', timeout=(3, 2), allow_redirects=False)
        data = response.json() if response.status_code == 200 else None
    except requests.ConnectionError as exc:
        # A user who explicitly skipped a local, uninstalled ComfyUI must still
        # be able to manage plugins. Only a refused loopback connection proves
        # absence here: a timeout, remote host or malformed answer does not.
        if (cfg.get('comfyui.setup_skipped') is True and not cfg.get('comfyui.base_dir')
                and parsed.hostname in ('localhost', '127.0.0.1', '::1')
                and _connection_refused(exc)):
            return
        raise RestartBlocked('ComfyUI did not confirm an empty queue. Check its connection before applying plugin changes.') from exc
    except (requests.RequestException, ValueError) as exc:
        raise RestartBlocked('ComfyUI did not confirm an empty queue. Check its connection before applying plugin changes.') from exc
    if (not isinstance(data, dict) or not isinstance(data.get('queue_running'), list)
            or not isinstance(data.get('queue_pending'), list)):
        raise RestartBlocked('ComfyUI did not confirm an empty queue. Check its connection before applying plugin changes.')
    if data['queue_running'] or data['queue_pending']:
        raise RestartBlocked('ComfyUI is still running or queuing work. Let it finish before applying plugin changes.')


def apply_changes():
    from ..services import updater
    from .routes import lifecycle_payload, restart_payload

    restart = restart_payload()
    if restart.get('mode') != 'self':
        return jsonify(error=restart['how'], code='manual_restart_required', restart=restart), 409
    registry = current_app.extensions.get('lds_plugins')
    gate = current_app.extensions.get(_EXTENSION)
    if registry is None or gate is None:
        return jsonify(error='Plugin restart safety is unavailable. Restart LDS manually.', code='restart_unavailable'), 409
    frozen_here = False
    try:
        gate.freeze()
        frozen_here = True
        state = lifecycle_payload(registry)
        if not state.get('pending_restart'):
            raise RestartBlocked('There are no plugin changes waiting to apply.')
        _lock_and_check_work(gate, registry)
        _require_comfy_idle()
        # False means a previous request already scheduled this process's exit.
        # Keep admissions closed in either case; opening them would be unsafe.
        updater.schedule_restart(block_during_update=True)
    except RestartBlocked as exc:
        if frozen_here:
            gate.release()
        return jsonify(error=str(exc), code='restart_blocked', restart=restart), 409
    except updater.UpdateInProgressError:
        if frozen_here:
            gate.release()
        return jsonify(error='An app update is in progress. Let it finish before applying plugin changes.',
                       code='restart_blocked', restart=restart), 409
    except Exception:
        if frozen_here:
            gate.release()
        log.warning('Plugin restart safety checks or scheduling failed', exc_info=True)
        return jsonify(error='LDS could not verify a safe restart. No plugin changes were applied; try again after checking running work.',
                       code='restart_blocked', restart=restart), 409
    response = jsonify(ok=True, restarting=True, boot_id=state['boot_id'], restart=restart)
    # Werkzeug calls close AFTER flushing the response. Keep the lock-owning
    # HTTP thread alive until exit, otherwise its identifier could be reused by
    # a fresh background thread and make a retained RLock appear reentrant.
    response.call_on_close(gate.finished.wait)
    return response
