"""Standalone contract harness: every SDK service below is a test double.

No app/ORM or real LDS SDK is imported. SDK replacements are restored after
preloading Live, then installed with monkeypatch only for individual tests.
Graph-shaped samples do not qualify the host H3 implementation.
"""
from __future__ import annotations

import importlib
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
from types import ModuleType, SimpleNamespace

from flask import Flask
import pytest


PLUGIN_DIR = Path(__file__).resolve().parents[1]
_prior_modules = {}
_sdk_modules = {}
_missing = object()


def _module(name, **values):
    module = ModuleType(name, 'Hermetic Live test double; not a host implementation.')
    module.__path__ = []
    module.__dict__.update(values)
    _prior_modules[name] = sys.modules.get(name, _missing)
    _sdk_modules[name] = module
    sys.modules[name] = module
    if '.' in name:
        parent, attr = name.rsplit('.', 1)
        setattr(sys.modules[parent], attr, module)
    return module


def _forbidden(*args, **kwargs):
    raise AssertionError('External runtime access is forbidden in the mocked Live contract harness.')


if 'lds_live' in sys.modules:
    raise RuntimeError('Collect mocked Live tests before importing another Live implementation.')

_module('lds_sdk')
_module('lds_sdk.video_host')
_module('lds_sdk.media', redact_user_paths=lambda text: re.sub(
    r'(?i)[a-z]:[\\/]Users[\\/][^\\/\s]+', '<user>', str(text)))
CONFIG = _module('lds_sdk.video_host.config', LOCAL_USER='local', get=lambda key, default=None: default,
                 data_dir=_forbidden)
_module('lds_sdk.video_host.netguard', public_bind=lambda: False)
_module('lds_sdk.video_host.http', require_comfyui=lambda **kw: None,
        require_no_stalled_comfyui=lambda: None)
_module('lds_sdk.video_host.studio', comfy_output_dir=lambda: None,
        unsafe_lora_name=lambda value: not isinstance(value, str) or value.startswith(('/', '\\'))
        or ':' in value or '..' in value.replace('\\', '/').split('/'))
_module('lds_sdk.video_host.comfy_fs', claim_output_file=lambda src, dst: False)
_module('lds_sdk.video_host.comfyui', fetch_output_image_bytes=lambda name: None)
_module('lds_sdk.video_host.ffmpeg_tools', ffmpeg_path=lambda: None,
        ffmpeg_ready=lambda force=False: {'ok': False})
_module('lds_sdk.local_render', comfyui_reachable=lambda: True)
_module('lds_sdk.lifecycle', is_available=lambda plugin: plugin == 'live')
QUEUE = SimpleNamespace(add_job=_forbidden, cancel_job=_forbidden)
RUNTIME = _module('lds_sdk.video_runtime', queue=QUEUE, job=lambda job_id: None)
H3 = _module('lds_sdk.h3_render', MP_DEFAULT=0.3, MP_MIN=0.1, MP_MAX=2.0,
             FRAMES_DEFAULT=124, FRAMES_MIN=28, FRAMES_MAX=364,
             TURBO_STEPS=4, DEFAULT_STEPS=20, SPARSE_MODES=('', 'sage'),
             SAGE_PACK={'name': 'Sage fixture', 'url': 'https://example.invalid/sage'},
             registered_classes=lambda: set(), eros_on_disk=lambda: False,
             sage_available=lambda classes=None: False, new_prefix=lambda user: 'local_lds_video_test_fixture',
             missing_weights=lambda: [], studio_ready=lambda missing: not missing,
             option_availability=lambda classes=None: {'turbo': True},
             profile=lambda: {'frame_choices': [124, 244, 364], 'fps': 24},
             deployed_loras=lambda: [], trained_loras=lambda: [],
             deploy_checkpoint=_forbidden, import_external_lora=_forbidden,
             snap_frames=lambda value: 124,
             clamp_megapixels=lambda value: max(0.1, min(2.0, float(value))),
             build_workflow=_forbidden)
_module('lds_sdk.h3_downloads', H3_DOWNLOADS={key: {
    'url': 'https://example.invalid/' + key, 'filename': key + '.safetensors',
    'subdir': 'fixture-h3',
} for key in ('h3_base', 'h3_text_encoder', 'h3_video_vae', 'h3_audio_vae', 'h3_turbo_lora')})

sys.path.insert(0, str(PLUGIN_DIR))
try:
    for name in ('lds_live.live_studio', 'lds_live.setup', 'lds_live.routes.video_live'):
        importlib.import_module(name)
finally:
    for name, previous in reversed(tuple(_prior_modules.items())):
        if previous is _missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    sys.path.remove(str(PLUGIN_DIR))


@pytest.fixture(autouse=True)
def sdk_fakes(monkeypatch, tmp_path):
    """Reset state and forbid external work even if a regression adds a call."""
    for name, module in _sdk_modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    live = importlib.import_module('lds_live.live_studio')
    calls = SimpleNamespace(builds=[], queued=[], cancelled=[], threads=[], h3=H3, runtime=RUNTIME,
                            lifecycle=_sdk_modules['lds_sdk.lifecycle'],
                            local_render=_sdk_modules['lds_sdk.local_render'])
    monkeypatch.setattr(threading.Thread, 'start', lambda thread: calls.threads.append(thread.name))
    monkeypatch.setattr(subprocess, 'run', _forbidden)
    monkeypatch.setattr(subprocess, 'Popen', _forbidden)
    monkeypatch.setattr(socket.socket, 'connect', _forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', _forbidden)
    monkeypatch.setattr(socket, 'create_connection', _forbidden)
    monkeypatch.setattr(CONFIG, 'data_dir', lambda: tmp_path)

    def build_workflow(**params):
        # Only the shape asserted by the upstream unit tests: not an H3 graph.
        calls.builds.append(params)
        return {'seed': params['seed'], 'workflow': {
            '104': {'inputs': {'prompt': params['prompt']}},
            '9': {'inputs': {'steps': params.get('steps'), 'seed': params['seed']}},
        }}

    def add_job(**params):
        calls.queued.append(params)
        return f'fake-job-{len(calls.queued)}'

    monkeypatch.setattr(H3, 'build_workflow', build_workflow)
    monkeypatch.setattr(QUEUE, 'add_job', add_job)
    monkeypatch.setattr(QUEUE, 'cancel_job', lambda job_id, user_id=None: calls.cancelled.append(job_id))
    live._session = None
    live._recent.clear()
    live._FFMPEG_FACTS.clear()
    yield calls
    live._session = None
    live._recent.clear()
    live._FFMPEG_FACTS.clear()


@pytest.fixture
def app():
    from lds_live.routes.video_live import bp
    instance = Flask('mocked-live-contract')
    instance.config.update(TESTING=True, SECRET_KEY='test-only')
    instance.register_blueprint(bp)
    return instance


@pytest.fixture
def client(app):
    return app.test_client()
