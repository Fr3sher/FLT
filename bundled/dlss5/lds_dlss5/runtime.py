"""DLSS's managed Python/encoder, independent of Video and its preferences."""
from contextlib import contextmanager
import json
import os
import subprocess
import threading
import time

from flask import current_app
from lds_sdk import workers

_CACHE = {}
_WORKER_LOCK = threading.Lock()
_ACTIVE_WORKERS = 0
_PROBE = (
    'import json, subprocess, numpy, imageio_ffmpeg\n'
    'encoder = imageio_ffmpeg.get_ffmpeg_exe()\n'
    'p = subprocess.run([encoder, "-version"], capture_output=True, timeout=15)\n'
    'print(json.dumps({"ok": p.returncode == 0 and bool(numpy.ones(1).sum()), '
    '"ffmpeg": encoder}))\n'
)


def context():
    return current_app.extensions['dlss5.context']


def register(ctx):
    ctx.app.extensions['dlss5.context'] = ctx
    ctx.register_config_defaults({'python': None, 'python_migrated': False})
    if not ctx.config.own('python_migrated'):
        # One-time preference migration, never a continuing Video dependency.
        own = ctx.config.own('python')
        ctx.config.update_own({'python': own if own is not None else
                               str(ctx.config.get('video.python') or ''),
                               'python_migrated': True})
    _CACHE.clear()


def interpreter():
    override = str(context().config.own('python') or '').strip().strip('"')
    if override:
        return override
    return context().plugin_environment().get('python') or ''


@contextmanager
def use_worker():
    global _ACTIVE_WORKERS
    ctx = context()
    explicit = bool(str(ctx.config.own('python') or '').strip())
    with ctx.use_plugin_worker() if explicit else ctx.use_plugin_env() as python:
        with _WORKER_LOCK:
            _ACTIVE_WORKERS += 1
        try:
            yield interpreter() if explicit else str(python)
        finally:
            with _WORKER_LOCK:
                _ACTIVE_WORKERS -= 1


def running():
    with _WORKER_LOCK:
        return _ACTIVE_WORKERS > 0


def probe(force=False):
    selected = interpreter()
    if not selected:
        return {'ok': False, 'ffmpeg': None}
    key = os.path.normcase(os.path.abspath(selected))
    try:
        with use_worker() as leased:
            cached = _CACHE.get(key)
            if not force and cached and time.monotonic() - cached[0] < 120:
                return dict(cached[1])
            proc = subprocess.run(
                workers.isolated_worker_argv(leased, '-c', _PROBE),
                env=workers.isolated_worker_env(leased), capture_output=True,
                text=True, encoding='utf-8', errors='replace', timeout=40,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result = json.loads(proc.stdout.strip().splitlines()[-1])
            if proc.returncode or not result.get('ok'):
                return {'ok': False, 'ffmpeg': None}
    except (RuntimeError, ValueError, OSError, IndexError, subprocess.SubprocessError):
        return {'ok': False, 'ffmpeg': None}
    _CACHE[key] = (time.monotonic(), result)
    return dict(result)


def worker_ready():
    return bool(probe().get('ok'))


def ffmpeg_ready(force=False):
    return probe(force=force)


def ffmpeg_path():
    return probe().get('ffmpeg')
