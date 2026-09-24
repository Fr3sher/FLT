"""One CPU runtime for both Model tools workers; never borrow another plugin."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
import subprocess
import time

from flask import current_app
from lds_sdk import config as cfg, workers

_CACHE = {}
_PROBE_CODE = (
    'import json, torch\n'
    'value = torch.ones(1, device="cpu") + 1\n'
    'serialized = value.numpy().tobytes()\n'
    'print(json.dumps({"torch": bool(value.item() == 2 and len(serialized) == 4), '
    '"torch_version": torch.__version__, "cuda_build": torch.version.cuda}))\n'
)


def register(ctx):
    clear_probe_cache()
    ctx.app.extensions['model_tools.runtime'] = ctx
    ctx.register_probe('model_tools', status)


def _context():
    return current_app.extensions['model_tools.runtime']


def explicit_python():
    return str(cfg.get('quantize.python') or '').strip().strip('"')


def environment():
    return _context().plugin_environment()


def candidates():
    explicit = explicit_python()
    if explicit:
        return [explicit]
    own = environment()
    return [own['python']] if own.get('ready') and own.get('python') else []


def clear_probe_cache():
    _CACHE.clear()


def _same_path(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


@contextmanager
def use_worker(expected_python):
    """Reserve this product until the managed or override child has been reaped."""
    explicit = explicit_python()
    if explicit:
        with _context().use_plugin_worker():
            explicit = explicit_python()
            if not expected_python or not _same_path(explicit, expected_python):
                raise RuntimeError('The Python override changed. Review the plan again.')
            yield explicit
        return
    with _context().use_plugin_env() as python:
        if not expected_python or not _same_path(str(python), expected_python):
            raise RuntimeError('The Model tools engine changed. Review the plan again.')
        yield str(python)


def probe(python):
    """Import and exercise torch on CPU in the worker, never in Flask."""
    try:
        with use_worker(python) as selected:
            # A warm cache avoids importing Torch again, but never skips the
            # current owner's admission or the reservation of its work.
            key = os.path.normcase(os.path.abspath(selected))
            hit = _CACHE.get(key)
            if hit and time.monotonic() - hit[0] < 300:
                return hit[1]
            proc = subprocess.run(
                workers.isolated_worker_argv(selected, '-c', _PROBE_CODE),
                capture_output=True, text=True, encoding='utf-8', errors='replace',
                timeout=90, env=workers.isolated_worker_env(selected),
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        info = json.loads((proc.stdout.strip().splitlines() or [''])[-1])
        if proc.returncode or not isinstance(info, dict):
            return None
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        return None
    _CACHE[key] = (time.monotonic(), info)
    return info


def interpreter():
    choices = candidates()
    if not choices:
        return {'python': None, 'ready': False, 'missing': ['torch'],
                'reason': 'Install the CPU engine in Plugins > Model tools > Settings before converting or merging.'}
    python = choices[0]
    info = probe(python)
    if info and info.get('torch'):
        return {'python': python, 'ready': True, 'missing': [], 'reason': None,
                'torch_version': info.get('torch_version'), 'cuda_build': info.get('cuda_build')}
    if explicit_python():
        reason = ('The selected Python override could not run PyTorch and NumPy on CPU. '
                  'In Plugins > Model tools > Settings > Advanced Python override, '
                  'select a compatible existing environment, or clear and save the override '
                  'to use the managed CPU engine. Keep the LDS application environment unchanged.')
    else:
        reason = ('The Model tools CPU engine could not run PyTorch and NumPy. '
                  'Open Plugins > Model tools > Settings and repair the CPU engine, then check again.')
    return {'python': python, 'ready': False, 'missing': ['torch'], 'reason': reason}


def status(*, refresh=False):
    if refresh:
        clear_probe_cache()
    own = environment()
    selected = interpreter()
    return {**selected, 'source': 'override' if explicit_python() else 'managed',
            'environment': own}
