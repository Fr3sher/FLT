"""Public product imports and boundaries against the real SDK and main schema.

The minimal Flask host deliberately has no main product blueprints or workers.
It verifies the SDK projection, not production create_app integration.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import importlib
import json
from pathlib import Path
import sys

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from PIL import Image, PngImagePlugin
import pytest
from sqlalchemy import text

from app import config as cfg
from app import models
from app.engines import registry as engines
from app.extensions import db
from app.plugins import registry
from app.plugins.loader import load_plugins

ROOT = Path(__file__).resolve().parents[2]
PRODUCTS = ('api_engines', 'camera_angles', 'canvas', 'civitai_publish', 'cloud_training', 'hf_publish', 'image_upscale', 'live',
            'model_tools', 'resource_monitor', 'scrape', 'seedvr2', 'video')


@pytest.fixture(autouse=True)
def no_external_runtime(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail('SDK integration tests may not start threads/processes or connect sockets')
    monkeypatch.setattr('socket.socket.connect', blocked)
    monkeypatch.setattr('socket.socket.connect_ex', blocked)
    monkeypatch.setattr('socket.create_connection', blocked)
    monkeypatch.setattr('threading.Thread.start', blocked)
    monkeypatch.setattr('subprocess.run', blocked)
    monkeypatch.setattr('subprocess.Popen', blocked)
    monkeypatch.setattr('requests.sessions.Session.request', blocked)


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setenv('LDS_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setenv('LDS_CONFIG', str(tmp_path / 'config.json'))
    monkeypatch.setenv('LDS_ENV', str(tmp_path / '.env'))
    monkeypatch.setenv('LDS_EXTENSIONS', '0')
    monkeypatch.setenv('LDS_PLUGIN_DISTRIBUTION', 'development')
    monkeypatch.setenv('LDS_BUNDLED_DIR', str(ROOT / 'bundled'))
    monkeypatch.setenv('LDS_PLUGINS_DIR', str(tmp_path / 'external'))
    monkeypatch.delenv('LDS_PLUGINS', raising=False)
    for key in cfg.SECRET_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(cfg, 'ENV_PATH', tmp_path / '.env')
    monkeypatch.setattr(cfg, 'DEFAULTS', deepcopy(cfg.DEFAULTS))
    monkeypatch.setattr(cfg, '_cache', None)
    monkeypatch.setattr(registry, '_ACTIVE', None)
    monkeypatch.setattr(engines, '_specs', {})
    monkeypatch.setattr('requests.sessions.Session.request',
                        lambda *_a, **_k: pytest.fail('Unexpected network request'))
    monkeypatch.setattr('subprocess.Popen',
                        lambda *_a, **_k: pytest.fail('Unexpected worker process'))
    original_path = list(sys.path)
    app = Flask(__name__)
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                      WTF_CSRF_ENABLED=False, SECRET_KEY='test-only')
    db.init_app(app)
    csrf = CSRFProtect(app)
    with app.app_context():
        db.create_all()
    yield app, csrf, tmp_path
    with app.app_context():
        db.session.remove()
        db.drop_all()
    # Keep imported mappings, like a real process. Re-importing duplicates the ORM.
    sys.path[:] = original_path


def activate(host, enabled):
    app, csrf, root = host
    discovered = {json.loads(path.read_text(encoding='utf-8'))['id']
                  for path in (ROOT / 'bundled').glob('*/plugin.json')}
    (root / 'config.json').write_text(json.dumps({'plugins': {'enabled': {
        pid: pid in enabled for pid in discovered}}}), encoding='utf-8')
    with app.app_context():
        return load_plugins(app, csrf)


@pytest.mark.parametrize('pid', PRODUCTS)
def test_each_public_product_registers_alone_with_real_sdk(host, pid):
    loaded = activate(host, {pid})
    assert loaded.records[pid].state == 'loaded', loaded.records[pid].error
    assert all(r.state == 'disabled' for key, r in loaded.records.items() if key != pid)
    # Public Video/publication history persists even while the packages are absent.
    assert len(db.metadata.tables) == 28
    assert {'video_civitai_link', 'video_checkpoint_preview'} <= set(db.metadata.tables)
    assert not any('creature' in name for name in db.metadata.tables)


def test_public_products_register_together_without_duplicate_routes(host):
    loaded = activate(host, PRODUCTS)
    assert {pid: loaded.records[pid].error for pid in PRODUCTS
            if loaded.records[pid].state != 'loaded'} == {}
    assert all(record.state == 'disabled' for pid, record in loaded.records.items() if pid not in PRODUCTS)
    routes = [(r.rule, tuple(sorted(r.methods))) for r in host[0].url_map.iter_rules()]
    assert len(routes) == len(set(routes))


def test_canvas_mapping_reads_and_writes_the_existing_main_table(host):
    activate(host, {'canvas'})
    from lds_canvas import models as plugin_models
    from lds_sdk.database import for_plugin
    app = host[0]
    with app.app_context():
        owner = plugin_models.db
        assert owner.table('canvas_node_position') is models.CanvasNodePosition.__table__
        dataset = models.FaceDataset(name='SDK fixture', trigger_word='fixture')
        db.session.add(dataset)
        db.session.commit()
        row = plugin_models.CanvasNodePosition(dataset_id=dataset.id, record_id=5, x=12, y=34)
        owner.session.add(row)
        owner.session.commit()
        main_row = db.session.get(models.CanvasNodePosition, row.id)
        assert (main_row.x, main_row.y) == (12, 34)
        with pytest.raises(ValueError, match='does not belong'):
            owner.session.query(models.FaceDataset)
        with pytest.raises(ValueError, match='Raw SQL'):
            owner.session.execute(text('select * from face_dataset'))
        with pytest.raises(ValueError, match='does not belong'):
            for_plugin('canvas', tables=('video_bank',))


def test_resource_monitor_route_uses_public_cached_snapshot_and_obeys_disable(host, monkeypatch):
    activate(host, {'resource_monitor'})
    monkeypatch.setattr('app.services.system_stats.machine_stats', lambda: {'cpu': {'percent': 7}})
    app = host[0]
    response = app.test_client().get('/api/system/stats')
    assert response.status_code == 200
    assert response.json == {'cpu': {'percent': 7}}
    cfg.save_config({'plugins': {'enabled': {'resource_monitor': False}}})
    assert app.test_client().get('/api/system/stats').status_code == 409
    assert all('restart' not in r.rule and 'interrupt' not in r.rule for r in app.url_map.iter_rules())


def test_public_h3_primitives_preserve_legacy_shapes_and_add_reference_support():
    from lds_sdk import h3_render
    from app.services import video_test_studio
    assert callable(h3_render.build_workflow)
    assert h3_render.profile() == video_test_studio._profile()
    assert h3_render.snap_frames(50) == video_test_studio.snap_frames(50)
    with pytest.raises(AttributeError):
        getattr(h3_render, 'reference')
    from lds_sdk.h3_downloads import H3_DOWNLOADS
    assert {'h3_base', 'h3_text_encoder', 'h3_video_vae', 'h3_audio_vae',
            'h3_turbo_lora', 'h3_parasyte_lora', 'h3_dareties_lora'} <= set(H3_DOWNLOADS)
    assert callable(h3_render.graft_reference_accel)


def test_publish_png_strips_metadata_without_rewriting_master(tmp_path):
    from lds_sdk.media import write_sanitized_publish_png
    original, sanitized = tmp_path / 'source.png', tmp_path / 'published.png'
    info = PngImagePlugin.PngInfo()
    info.add_text('workflow', 'private local source paths')
    Image.new('RGBA', (3, 2), (12, 34, 56, 128)).save(original, pnginfo=info)
    before = original.read_bytes()
    write_sanitized_publish_png(original, sanitized)
    assert original.read_bytes() == before
    with Image.open(sanitized) as image:
        assert image.info == {}
        assert image.getpixel((0, 0)) == (12, 34, 56, 128)


def test_engine_errors_keep_the_identity_caught_by_main():
    from lds_sdk import engine_errors
    from app.services import chatgpt_image, engine_errors as main_errors
    assert engine_errors.EngineFatal is main_errors.EngineFatal
    assert engine_errors.SubscriptionQuotaExceeded is chatgpt_image.SubscriptionQuotaExceeded
    assert engine_errors.SubscriptionUnavailable is chatgpt_image.SubscriptionUnavailable


def test_image_and_export_snapshots_preserve_main_fields_and_user_boundaries(host):
    from lds_sdk.images import DatasetImages, GalleryImages
    from lds_sdk.dataset_exports import DatasetExports
    from lds_sdk import training_data
    with host[0].app_context():
        dataset = models.FaceDataset(name='Owned dataset', trigger_word='fixture', user_id='owner')
        db.session.add(dataset)
        db.session.commit()
        source = models.FaceDatasetImage(dataset_id=dataset.id, status='keep', filename='source.png')
        gallery = models.LoraTestImage(dataset_id=dataset.id, checkpoint='fixture.safetensors',
                                      strength=1, filename='gallery.png', status='done')
        db.session.add_all([source, gallery])
        db.session.commit()
        exports = DatasetExports('owner')
        assert exports.get_dataset(dataset.id).name == 'Owned dataset'
        assert exports.kept_images(dataset.id)[0].filename == 'source.png'
        assert training_data.get_dataset('owner', dataset.id).trigger_word == 'fixture'
        assert len(training_data.list_datasets('owner')) == 1
        assert training_data.get_dataset('other', dataset.id) is None
        assert DatasetExports('other').get_dataset(dataset.id) is None
        assert DatasetExports('other').kept_images(dataset.id) == ()
        assert DatasetImages('other').get(source.id) is None
        assert GalleryImages('other').get(gallery.id) is None
        candidate = DatasetImages('owner').create_derivative(source.id, derivation_kind='camera')
        assert candidate.status == 'pending'
        assert candidate.parent_image_id == source.id
        assert DatasetImages('owner').fail_unqueued(candidate.id, 'test failure') is True
        gallery_candidate = GalleryImages('owner').create_derivative(gallery.id,
                            derivation_kind='upscale', prompt='fixture')
        assert GalleryImages('owner').discard_unqueued(gallery_candidate.id) is True


def test_credentials_follow_configured_output_and_refuse_path_keys(host, monkeypatch):
    from lds_sdk.credentials import civitai_api_key, resolve_credential_file
    root = host[2]
    monkeypatch.delenv('SCRAPE_COOKIES_DIR', raising=False)
    monkeypatch.delenv('CIVITAI_API_KEY', raising=False)
    cfg.save_config({'comfyui': {'output_dir': str(root / 'ComfyUI' / 'output')}})
    cookies = root / 'ComfyUI' / 'scrape_cookies'
    cookies.mkdir(parents=True)
    cookie_file = cookies / 'civitai_api_key.txt'
    cookie_file.write_text('test-fixture-token', encoding='utf-8')
    assert Path(resolve_credential_file('civitai_api_key')) == cookie_file
    assert civitai_api_key() == 'test-fixture-token'
    for key in ('../secret', 'a/b', r'a\b', 'a:stream', 'bad\x00key'):
        with pytest.raises(ValueError):
            resolve_credential_file(key)
    monkeypatch.setenv('CIVITAI_API_KEY', 'environment-fixture-token')
    assert civitai_api_key() == 'environment-fixture-token'


def test_model_worker_isolation_keeps_transport_but_removes_python_injection():
    from lds_sdk.workers import isolated_worker_argv, isolated_worker_env
    base = {'PYTHONPATH': 'untrusted', 'PYTHONHOME': 'untrusted', 'HTTPS_PROXY': 'fixture'}
    env = isolated_worker_env(sys.executable, base=base, PYTHONPATH='override')
    assert 'PYTHONPATH' not in env and 'PYTHONHOME' not in env
    assert env['PYTHONNOUSERSITE'] == '1' and env['HTTPS_PROXY'] == 'fixture'
    assert isolated_worker_argv(sys.executable, 'worker.py') == [sys.executable, '-I', 'worker.py']
    assert base['PYTHONPATH'] == 'untrusted'


def test_video_queue_owns_admission_and_cancellation(host, monkeypatch):
    activate(host, {'live'})
    from lds_sdk import video_runtime
    from app.job_queue import queue_manager
    calls = []
    monkeypatch.setattr(queue_manager, 'add_job', lambda **kw: calls.append(kw) or 'queued')
    monkeypatch.setattr(queue_manager, 'cancel_job', lambda *args: calls.append(args) or True)
    metadata = {'is_live': True, 'model_name': 'video_live', 'live_session': 'fixture'}
    kwargs = dict(job_type='image', user_id='local', workflow_data={}, prompt='test', metadata=metadata)
    app = host[0]
    with app.app_context():
        assert video_runtime.queue.add_job(**kwargs) == 'queued'
        assert calls[-1]['metadata'] == metadata
        for invalid in ({}, {**metadata, 'is_video_test': True}, {**metadata, 'is_external': True},
                        {**metadata, 'model_name': 'video_lora_test'}):
            with pytest.raises(ValueError):
                video_runtime.queue.add_job(**{**kwargs, 'metadata': invalid})
        db.session.add(models.ImageGenerationQueue(job_id='live-job', user_id='local',
                       status='pending', job_metadata=json.dumps(metadata)))
        db.session.add(models.ImageGenerationQueue(job_id='other-job', user_id='local',
                       status='pending', job_metadata='{}'))
        db.session.commit()
        snapshot = video_runtime.job('live-job')
        assert snapshot.status == 'pending'
        with pytest.raises(FrozenInstanceError):
            snapshot.status = 'done'
        assert video_runtime.job('other-job') is None
        with pytest.raises(LookupError):
            video_runtime.queue.cancel_job('live-job', 'someone-else')
        with pytest.raises(LookupError):
            video_runtime.queue.cancel_job('other-job', 'local')
        assert video_runtime.queue.cancel_job('live-job', 'local') is True
        cfg.save_config({'plugins': {'enabled': {'live': False}}})
        with pytest.raises(ValueError, match='Enable live'):
            video_runtime.queue.add_job(**kwargs)
        assert len(calls) == 2


def test_declared_sdk_exports_are_real_symbols():
    root = ROOT / 'backend' / 'lds_sdk'
    for path in root.rglob('*.py'):
        relative = path.relative_to(root).with_suffix('')
        parts = list(relative.parts)
        if parts[-1] == '__init__':
            parts.pop()
        module = importlib.import_module('.'.join(['lds_sdk', *parts]))
        for name in getattr(module, '__all__', ()):
            assert hasattr(module, name), f'{module.__name__}.{name}'
