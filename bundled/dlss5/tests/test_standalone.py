"""Real plugin registration and file workflow without Video or a GPU."""
import builtins
import io
from pathlib import Path
import sys
import threading
import time

import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'bundled/dlss5')]
from app import config, setup_installer
from app.plugins.api import PluginContext
from app.plugins.manifest import load_manifest
from app.plugins.registry import PluginRecord, PluginRegistry
from app.plugins import environment
from lds_sdk import dlss5, video_media
from lds_dlss5 import register, jobs, neural_render as nr, routes, runtime


@pytest.fixture
def product(tmp_path, monkeypatch):
    state = {'plugins': {'dlss5': {'python': '', 'python_migrated': True}}}
    def get(key, default=None):
        node = state
        for part in key.split('.'):
            node = node.get(part, default) if isinstance(node, dict) else default
        return node
    def save(values):
        state['plugins']['dlss5'].update(values['plugins']['dlss5'])
        return state
    monkeypatch.setattr(config, 'get', get)
    monkeypatch.setattr(config, 'data_dir', lambda: tmp_path)
    monkeypatch.setattr(config, 'save_config', save)
    monkeypatch.setattr(config, 'register_plugin_defaults', lambda *_: None)
    monkeypatch.setattr(setup_installer, 'plugin_install_busy', lambda _: False)
    monkeypatch.setattr(runtime.subprocess, 'run', lambda *_a, **_k: pytest.fail('Unexpected subprocess'))
    monkeypatch.setattr(runtime.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('Unexpected native worker'))
    original_import = builtins.__import__
    def without_video(name, *args, **kwargs):
        if name == 'lds_video' or name.startswith('lds_video.'):
            pytest.fail('The standalone plugin imported Video')
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', without_video)
    app = Flask(__name__)
    app.config['TESTING'] = True
    directory = ROOT / 'bundled/dlss5'
    manifest = load_manifest(directory)
    registry = PluginRegistry()
    record = PluginRecord(manifest.id, manifest, str(directory), True, state='loaded')
    registry.records[record.id] = record
    assert registry.claim_manifest(manifest) is None
    app.extensions['lds_plugins'] = registry
    ctx = PluginContext(app, registry, manifest, tmp_path / 'plugin-data/dlss5')
    register(ctx)
    return app, ctx, record, state


def test_alone_registers_owned_preparation_and_refuses_optional_video(product, monkeypatch):
    app, ctx, _, _ = product
    monkeypatch.setattr(nr, '_driver_files', lambda: {'ngx': False, 'nvof': False})
    client = app.test_client()
    result = client.get('/api/dlss5/status')
    assert result.status_code == 200
    value = result.get_json()
    assert not value['status']['ready']
    assert value['environment']['action'] == 'plugin_environment:dlss5'
    registry = app.extensions['lds_plugins']
    assert set(registry.records) == {'dlss5'}
    assert registry.probes['dlss5nr'][0] == 'dlss5'
    assert registry.install_actions['dlss5nr_bridge']['plugin'] == 'dlss5'
    assert client.get('/api/video-dataset/1/neural-render').status_code == 409
    with app.app_context():
        assert not video_media.available()
        assert ctx.plugin_environment()['can_install']


def upload(client):
    response = client.post('/api/dlss5/clips', data={'file': (io.BytesIO(b'ORIGINAL'), 'clip.mp4')})
    assert response.status_code == 201
    return response.get_json()['clip']


def wait_done(client, ident):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        value = client.get('/api/dlss5/clips/' + ident).get_json()['clip']
        if value['state'] not in ('running', 'queued'):
            return value
        time.sleep(.01)
    pytest.fail('Synthetic render did not complete')


def test_open_folder_uses_the_selected_clip_directory_before_and_after_render(product, monkeypatch):
    app, ctx, _, _ = product
    opened = []
    monkeypatch.setattr(routes.os, 'startfile', opened.append, raising=False)
    client = app.test_client()
    clip = upload(client)
    directory = ctx.data_dir / 'clips' / clip['id']
    url = f"/api/dlss5/clips/{clip['id']}/open-folder"
    for has_result in (False, True):
        if has_result:
            (directory / 'render.mp4').write_bytes(b'RENDER')
            with app.app_context():
                record = jobs.read(clip['id'])
                record.update(state='done', has_result=True)
                jobs.save(record)
        response = client.post(url, json={'path': str(directory.parent)})
        assert response.status_code == 200 and response.get_json()['ok']
        assert opened[-1] == str(directory)
    assert (directory / 'original.mp4').read_bytes() == b'ORIGINAL'
    assert (directory / 'render.mp4').read_bytes() == b'RENDER'
    assert client.get(url).status_code == 405


def test_open_folder_rejects_missing_clips_and_reports_explorer_failure(product, monkeypatch):
    app, _, _, _ = product
    monkeypatch.setattr(routes.os, 'startfile', lambda *_: pytest.fail('Unexpected folder opened'), raising=False)
    client = app.test_client()
    for ident in ('invalid', '0' * 32):
        assert client.post(f'/api/dlss5/clips/{ident}/open-folder', json={}).status_code == 400
    clip = upload(client)
    def fail_open(_path):
        raise OSError('Private filesystem details')
    monkeypatch.setattr(routes.os, 'startfile', fail_open)
    response = client.post(f"/api/dlss5/clips/{clip['id']}/open-folder", json={})
    assert response.status_code == 500
    assert response.get_json() == {'error': 'Could not open the video folder on the computer running LDS.'}


def test_import_render_download_and_history_preserve_the_original(product, monkeypatch):
    app, _, _, _ = product
    monkeypatch.setattr(nr, 'status', lambda: {'ready': True, 'missing': []})
    def render(source, destination, params, **kwargs):
        assert environment.running('dlss5')
        assert Path(source).read_bytes() == b'ORIGINAL'
        Path(destination).write_bytes(b'RENDER')
        kwargs['on_progress']({'frame': 3, 'total': 3})
        return {'frames': 3, 'temporal': False}
    monkeypatch.setattr(nr, 'render_video', render)
    client = app.test_client()
    clip = upload(client)
    assert client.post(f"/api/dlss5/clips/{clip['id']}/render", json={'tone': 0}).status_code == 202
    done = wait_done(client, clip['id'])
    assert done['state'] == 'done' and done['has_result']
    assert done['params']['tone'] == 0
    assert client.get(f"/api/dlss5/clips/{clip['id']}/media/original").data == b'ORIGINAL'
    response = client.get(f"/api/dlss5/clips/{clip['id']}/media/result?download=1")
    assert response.data == b'RENDER' and 'attachment' in response.headers['Content-Disposition']
    assert client.get('/api/dlss5/clips').get_json()['clips'][0]['id'] == clip['id']
    assert not environment.running('dlss5')


def test_cancel_has_a_worker_lease_and_cannot_replace_the_original(product, monkeypatch):
    app, _, _, _ = product
    entered = threading.Event()
    monkeypatch.setattr(nr, 'status', lambda: {'ready': True, 'missing': []})
    def render(_source, destination, _params, **kwargs):
        entered.set()
        while not kwargs['cancel']():
            time.sleep(.01)
        Path(destination).write_bytes(b'PARTIAL')
        raise nr.NeuralRenderError('cancelled')
    monkeypatch.setattr(nr, 'render_video', render)
    client = app.test_client()
    clip = upload(client)
    client.post(f"/api/dlss5/clips/{clip['id']}/render", json={})
    assert entered.wait(1) and environment.running('dlss5')
    assert client.post('/api/dlss5/settings', json={'python': 'other.exe'}).status_code == 409
    assert client.post(f"/api/dlss5/clips/{clip['id']}/cancel", json={}).get_json()['cancelled']
    done = wait_done(client, clip['id'])
    assert done['state'] == 'cancelled' and not done['has_result']
    assert client.get(f"/api/dlss5/clips/{clip['id']}/media/original").data == b'ORIGINAL'
    with app.app_context():
        assert not (jobs.folder(clip['id']) / 'render.part.mp4').exists()
    assert not environment.running('dlss5')


def test_failed_worker_start_releases_lease_even_when_failure_cannot_be_saved(product, monkeypatch):
    app, _, _, _ = product
    monkeypatch.setattr(nr, 'status', lambda: {'ready': True, 'missing': []})
    clip = upload(app.test_client())
    original_save = jobs.save

    def save(record):
        if record['state'] == 'failed':
            raise OSError('No space to persist failure')
        return original_save(record)

    def fail_start(_thread):
        raise RuntimeError('No worker thread available')

    monkeypatch.setattr(jobs, 'save', save)
    monkeypatch.setattr(threading.Thread, 'start', fail_start)
    with app.app_context(), pytest.raises(OSError, match='No space'):
        jobs.start(app, clip['id'], {})
    assert not jobs.busy()
    assert not environment.running('dlss5')
    assert app.test_client().get(f"/api/dlss5/clips/{clip['id']}/media/original").data == b'ORIGINAL'


def test_off_refuses_routes_and_sdk_before_any_import(product, monkeypatch):
    app, _, record, _ = product
    record.enabled = False
    monkeypatch.setattr(dlss5, 'import_module', lambda *_: pytest.fail('DLSS OFF imported its engine'))
    monkeypatch.setattr(video_media, 'import_module', lambda *_: pytest.fail('Video OFF imported its tables'))
    client = app.test_client()
    assert client.get('/api/dlss5/clips').status_code == 409
    with app.app_context():
        assert not dlss5.status()['available']
        with pytest.raises(dlss5.NeuralRenderError):
            dlss5.render_video('source', 'target', {})
        with pytest.raises(dlss5.NeuralRenderError):
            video_media.dataset_exists('local', 1)


def test_paths_and_interrupted_records_are_bounded_and_recovered(product):
    app, _, _, _ = product
    client = app.test_client()
    clip = upload(client)
    with app.app_context():
        record = jobs.read(clip['id'])
        record['state'] = 'running'
        jobs.save(record)
        jobs.recover()
        assert jobs.read(clip['id'])['state'] == 'failed'
        with pytest.raises(nr.NeuralRenderError):
            jobs.folder('../outside')
        record['original'] = '../../secret.mp4'
        jobs.save(record)
        with pytest.raises(nr.NeuralRenderError):
            jobs.media_path(clip['id'])


def test_python_migration_is_once_and_later_video_changes_are_independent(product):
    app, ctx, _, state = product
    state['plugins']['dlss5'] = {'python_migrated': False}
    state['video'] = {'python': 'previous-python.exe'}
    with app.app_context():
        runtime.register(ctx)
        assert runtime.interpreter() == 'previous-python.exe'
        state['video']['python'] = 'different-video-python.exe'
        runtime.register(ctx)
        assert runtime.interpreter() == 'previous-python.exe'
    assert app.test_client().post('/api/dlss5/settings', json={'python': ''}).status_code == 200
    assert state['plugins']['dlss5']['python'] == ''


def test_cancel_reaps_a_silent_native_child(product, monkeypatch):
    app, _, _, _ = product
    killed = threading.Event()
    cancellation = threading.Event()
    class SilentStream:
        def __iter__(self):
            killed.wait(2)
            return iter(())
        def close(self):
            pass
    class Child:
        stdout = SilentStream()
        stderr = io.StringIO('')
        def poll(self):
            return -1 if killed.is_set() else None
        def kill(self):
            killed.set()
        def wait(self, timeout=None):
            return -1
    monkeypatch.setattr(nr.subprocess, 'Popen', lambda *_a, **_k: Child())
    monkeypatch.setattr(nr, 'status', lambda: {'ready': True, 'driver_nvof': True})
    monkeypatch.setattr(nr, 'clip_dimensions', lambda _: (800, 600))
    monkeypatch.setattr(runtime, 'ffmpeg_path', lambda: 'ffmpeg')
    monkeypatch.setattr(runtime, 'interpreter', lambda: 'python')
    cancellation.set()
    with app.app_context(), pytest.raises(nr.NeuralRenderError, match='cancelled'):
        nr._render_video('source', 'target', nr.normalize_params({}), cancel=cancellation.is_set)
    assert killed.is_set()
