"""Public Video/API registration and local data routes with the real host SDK."""
import importlib
import base64
import json
from pathlib import Path
from unittest.mock import Mock

from PIL import Image
import pytest

from app import models
from app.engines import registry as engines
from app.extensions import db
from test_public_sdk_integration import ROOT, activate, host  # noqa: F401 — shared fixture


@pytest.fixture(autouse=True)
def no_external_connection_or_worker(monkeypatch):
    def refuse(*_args, **_kwargs):
        pytest.fail('Video/API SDK qualification must not connect or launch a worker')
    monkeypatch.setattr('socket.socket.connect', refuse)
    monkeypatch.setattr('socket.socket.connect_ex', refuse)
    monkeypatch.setattr('socket.create_connection', refuse)
    monkeypatch.setattr('requests.sessions.Session.request', refuse)
    monkeypatch.setattr('subprocess.Popen', refuse)
    monkeypatch.setattr('threading.Thread.start', refuse)


@pytest.mark.parametrize('product', ['video', 'api_engines'])
def test_all_product_service_modules_import_with_real_sdk(host, product):
    loaded = activate(host, {product})
    assert loaded.records[product].state == 'loaded', loaded.records[product].error
    package = 'lds_' + product
    root = ROOT / 'bundled' / product / package
    with host[0].app_context():
        for path in root.rglob('*.py'):
            parts = list(path.relative_to(root).with_suffix('').parts)
            if parts[-1] == '__init__':
                parts.pop()
            importlib.import_module('.'.join([package, *parts]))
    assert len(db.metadata.tables) == 28


def test_video_catalog_and_empty_lists_work_without_other_plugins(host):
    loaded = activate(host, {'video'})
    app = host[0]
    assert all(not record.enabled for pid, record in loaded.records.items() if pid != 'video')
    for route, key in [('/api/video-banks', 'banks'), ('/api/video-datasets', 'datasets'),
                       ('/api/video-studio/clips', 'clips')]:
        response = app.test_client().get(route)
        assert response.status_code == 200, response.json
        assert response.json[key] == []
    targets = app.test_client().get('/api/video/targets')
    assert targets.status_code == 200
    assert 'minimax_h3' in {row['key'] for row in targets.json['targets']}
    assert app.test_client().get('/api/video-dataset/999').status_code == 404
    assert app.test_client().get('/api/video-studio/clip/999').status_code == 404


@pytest.mark.parametrize('route', ['/api/video-banks', '/api/video-datasets', '/api/video-studio/clips'])
def test_video_routes_obey_runtime_disablement(host, route):
    activate(host, {'video'})
    app = host[0]
    assert app.test_client().get(route).status_code == 200
    from app import config
    config.save_config({'plugins': {'enabled': {'video': False}}})
    response = app.test_client().get(route)
    assert response.status_code == 409
    assert response.json['code'] == 'plugin_unavailable'
    config.save_config({'plugins': {'enabled': {'video': True}}})
    assert app.test_client().get(route).status_code == 200


def test_video_bank_registration_uses_main_tables_without_decoding_sources(host):
    activate(host, {'video'})
    app, _, root = host
    sources = root / 'rushes'
    sources.mkdir()
    source = sources / 'fixture.mp4'
    original = b'Inventory only: this is deliberately not a decodable video.'
    source.write_bytes(original)
    response = app.test_client().post('/api/video-bank/create',
                                     json={'name': 'Fixture bank', 'folder': str(sources)})
    assert response.status_code == 200, response.json
    assert response.json['added'] == 1
    bank_id = response.json['id']
    with app.app_context():
        row = db.session.get(models.VideoBank, bank_id)
        assert row.name == 'Fixture bank'
        source_row = models.VideoSource.query.filter_by(bank_id=bank_id).one()
        assert source_row.relpath == 'fixture.mp4'
        assert source_row.duration_s is None
        from lds_video.video_bank_service import get_bank
        assert get_bank('someone-else', bank_id) is None
    assert source.read_bytes() == original
    listing = app.test_client().get('/api/video-banks')
    assert listing.status_code == 200 and listing.json['banks'][0]['id'] == bank_id


def test_image_dataset_becomes_video_stills_and_caption_sidecar_changes(host):
    activate(host, {'video'})
    app = host[0]
    from app.services import face_dataset_service as fds
    with app.app_context():
        dataset = fds.create_dataset('local', 'Fixture images', 'fixture')
        parent = Path(fds._dataset_dir(dataset.id))
        parent.mkdir(parents=True, exist_ok=True)
        source = parent / 'source.png'
        Image.new('RGB', (64, 64), 'red').save(source)
        original = source.read_bytes()
        db.session.add(models.FaceDatasetImage(dataset_id=dataset.id, filename='source.png',
                       status='keep', caption='a portrait', source='import'))
        db.session.commit()
        image_dataset_id = dataset.id
    response = app.test_client().post('/api/video-datasets/from-dataset',
                                      json={'dataset_id': image_dataset_id, 'name': 'Fixture stills'})
    assert response.status_code == 201, response.json
    assert response.json['clips'] == 1
    dataset_id = response.json['id']
    with app.app_context():
        video = db.session.get(models.VideoDataset, dataset_id)
        clip = models.VideoDatasetClip.query.filter_by(dataset_id=dataset_id).one()
        clip_id = clip.id
        output = Path(video.output_dir) / clip.filename
        sidecar = output.with_suffix('.txt')
        assert video.frames == 1 and video.trigger_word == 'fixture'
        assert output.is_file() and 'fixture' in sidecar.read_text(encoding='utf-8')
        from lds_video.video_bank_service import get_video_dataset
        assert get_video_dataset('someone-else', dataset_id) is None
    response = app.test_client().post(f'/api/video-dataset/{dataset_id}/clip/{clip_id}/caption',
                                     json={'caption': 'new caption'})
    assert response.status_code == 200, response.json
    assert sidecar.read_text(encoding='utf-8').count('fixture') == 1
    assert 'new caption' in sidecar.read_text(encoding='utf-8')
    assert source.read_bytes() == original
    assert app.test_client().get(f'/api/video-dataset/{dataset_id}').status_code == 200
    assert app.test_client().get(f'/api/video-dataset/{dataset_id}/clip/{clip_id}/media').status_code == 200


def test_shared_host_models_are_the_same_main_classes():
    from lds_sdk.video_host import models as shared
    for name in shared.__all__:
        assert getattr(shared, name) is getattr(models, name)


def test_video_runtime_bounds_shared_admission_state(host, monkeypatch):
    activate(host, {'video'})
    from app import config
    from app.job_queue import queue_manager
    from lds_sdk.video_runtime import queue
    with host[0].app_context():
        queue._set_system_state('training_error', 'fixture', ttl_seconds=30)
        assert queue._get_system_state('training_error') == 'fixture'
        with pytest.raises(ValueError):
            queue._get_system_state('unrelated_state')
        with pytest.raises(ValueError):
            queue._set_system_state('vision_in_progress', True)
        with pytest.raises(ValueError):
            queue._set_system_state('training_dataset_table', 'face_dataset')
        with pytest.raises(ValueError):
            queue._set_system_state('training_train_type', 'image')
        monkeypatch.setattr(queue_manager, 'has_comfyui_work', lambda: True)
        assert queue.has_comfyui_work() is True
        config.save_config({'plugins': {'enabled': {'video': False}}})
        with pytest.raises(ValueError, match='Enable video'):
            queue._set_system_state('training_error', None)


def test_video_local_progress_ignores_face_training_with_the_same_id(host):
    activate(host, {'video'})
    from app import config
    from app.job_queue import queue_manager
    app = host[0]
    config.save_config({'aitoolkit': {'dir': str(host[2] / 'empty-toolkit')}})
    with app.app_context():
        ds = models.VideoDataset(name='Fixture', target_profile='minimax_h3', output_dir='',
                                 fps=24, frames=1, width=768, height=768)
        db.session.add(ds)
        db.session.commit()
        dataset_id = ds.id
        queue_manager._set_system_state('training_dataset_id', dataset_id)
        queue_manager._set_system_state('training_dataset_table', 'face_dataset')
        queue_manager._set_system_state('training_in_progress', True)
    response = app.test_client().get(f'/api/video-dataset/{dataset_id}/train/progress')
    assert response.status_code == 200, response.json
    assert response.json['active'] is False
    assert response.json['checkpoints'] == []


def test_api_engines_register_callbacks_and_readiness_without_a_paid_request(host):
    activate(host, {'api_engines'})
    assert set(engines.ids()) == {'nanobanana', 'chatgpt', 'openrouter'}
    for spec in engines.all_specs():
        assert spec.plugin == 'api_engines'
        assert callable(engines.generate_fn(spec.id))
        assert spec.probe()['ok'] is False
    with host[0].app_context():
        assert engines.generate_kwargs('chatgpt') == {'force_lane': 'api'}


@pytest.mark.parametrize('engine,key', [('nanobanana', 'GEMINI_API_KEY'),
                                      ('chatgpt', 'OPENAI_API_KEY'),
                                      ('openrouter', 'OPENROUTER_API_KEY')])
@pytest.mark.parametrize('status', [200, 401])
def test_api_dispatch_uses_real_sdk_and_shared_fatal_errors(host, monkeypatch, engine, key, status):
    activate(host, {'api_engines'})
    monkeypatch.setenv(key, 'test-only-provider-fixture')
    encoded = base64.b64encode(b'fixture-image').decode()
    body = {'data': [{'b64_json': encoded, 'media_type': 'image/png'}]}
    if engine == 'nanobanana':
        body = {'candidates': [{'content': {'parts': [
            {'inlineData': {'mimeType': 'image/png', 'data': encoded}}]}, 'finishReason': 'STOP'}]}
    if status == 401:
        body = {'error': {'message': 'Invalid fixture key', 'code': 401}}
    response = Mock(status_code=status, headers={}, text=json.dumps(body))
    response.json.return_value = body
    post = Mock(return_value=response)
    monkeypatch.setattr('requests.post', post)
    from app.services.engine_errors import EngineFatal
    with host[0].app_context():
        callback = engines.generate_fn(engine)
        kwargs = engines.generate_kwargs(engine)
        if status == 200:
            assert callback([b'ref-a', b'ref-b'], 'fixture', **kwargs) == b'fixture-image'
        else:
            with pytest.raises(EngineFatal) as error:
                callback([b'ref-a', b'ref-b'], 'fixture', **kwargs)
            assert 'test-only-provider-fixture' not in str(error.value)
    assert post.call_count == 1


def test_api_oauth_routes_use_only_the_temporary_data_folder(host):
    activate(host, {'api_engines'})
    from lds_api_engines import chatgpt_oauth
    token_file = host[2] / 'data' / 'chatgpt_oauth.json'
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(json.dumps({'access_token': 'test-only-oauth-fixture'}), encoding='utf-8')
    assert chatgpt_oauth._token_path() == token_file
    client = host[0].test_client()
    response = client.get('/api/settings/chatgpt-oauth/poll')
    assert response.status_code == 200 and response.json['status'] == 'error'
    assert client.post('/api/settings/chatgpt-oauth/logout').json == {'ok': True}
    assert not token_file.exists()
