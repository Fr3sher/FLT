"""Real public HTTP restoration refusals, with temporary data and no workers."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from test_public_backend_mount import factory  # noqa: F401
from app import config as cfg
from app.extensions import db
from app.models import BankImage, FaceDatasetImage, ImageBank, ImageGenerationQueue
from app.services import face_dataset_service as fds


def _source_url(app, tmp_path, surface):
    """Seed an owned source without importing, scanning or running inference."""
    with app.app_context():
        if surface == 'bank':
            folder = tmp_path / 'photos'
            folder.mkdir()
            Image.new('RGB', (96, 64)).save(folder / 'source.png')
            bank = ImageBank(user_id=cfg.LOCAL_USER, name='Restoration',
                             source_path=str(folder))
            db.session.add(bank)
            db.session.flush()
            db.session.add(BankImage(bank_id=bank.id, relpath='source.png',
                                     status='keep'))
            db.session.commit()
            return f'/api/bank/{bank.id}/improve'
        dataset = fds.create_dataset(cfg.LOCAL_USER, 'Restoration', 'restoration')
        folder = Path(fds._dataset_dir(dataset.id))
        folder.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (96, 64)).save(folder / 'source.png')
        source = FaceDatasetImage(dataset_id=dataset.id, filename='source.png',
                                  source='import', status='keep')
        db.session.add(source)
        db.session.commit()
        return f'/api/dataset/image/{source.id}/improve'


def _assert_no_render(app, surface):
    with app.app_context():
        assert ImageGenerationQueue.query.count() == 0
        assert FaceDatasetImage.query.count() == (0 if surface == 'bank' else 1)
        assert BankImage.query.filter(BankImage.edit_method.isnot(None)).count() == 0


def _object_info_transport(monkeypatch, classes):
    """Keep the SDK and node preflight real; replace only the HTTP transport."""
    from app.utils import comfyui
    monkeypatch.setattr(comfyui, '_object_info_cache', {
        'data': None, 'timestamp': 0, 'key': None, 'enums': None, 'files': None})
    monkeypatch.setattr(comfyui, '_object_info_last', {
        'status': 'unknown', 'timestamp': 0, 'key': None})
    calls = []

    def request(_session, method, url, **kwargs):
        assert method.lower() == 'get' and url.endswith('/object_info')
        calls.append(url)
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: dict.fromkeys(classes, {}))

    monkeypatch.setattr('requests.sessions.Session.request', request)
    return calls


@pytest.mark.parametrize('surface', ['dataset', 'bank'])
@pytest.mark.parametrize('engine, owner', [('klein', 'image_upscale'), ('seedvr2', 'seedvr2')])
@pytest.mark.parametrize('state', ['absent', 'off', 'pending_disable'])
def test_unavailable_restoration_is_structured_409(factory, tmp_path, monkeypatch,
                                                  surface, engine, owner, state):
    app = factory(None if state == 'absent' else {owner} if state == 'pending_disable' else set())
    url = _source_url(app, tmp_path, surface)
    if state == 'pending_disable':
        spec = app.extensions['lds_plugins'].restore_engines[engine]

        def forbidden(*args, **kwargs):
            pytest.fail('A disabled restoration must not call its provider')

        for callback in ('preflight', 'enqueue', 'error_response'):
            monkeypatch.setitem(spec, callback, forbidden)
        cfg.save_config({'plugins': {'enabled': {owner: False}}})
    response = app.test_client().post(url, json={'engine': engine})
    assert response.status_code == 409, response.get_json()
    body = response.get_json()
    assert body.get('plugin_unavailable') is True
    assert engine in body['error'] and 'Store' in body['error']
    _assert_no_render(app, surface)


@pytest.mark.parametrize('surface', ['dataset', 'bank'])
def test_seedvr2_plugin_missing_assets_reach_http_banner(factory, tmp_path, monkeypatch,
                                                       surface):
    app = factory({'seedvr2'})
    app.config['PROPAGATE_EXCEPTIONS'] = False
    from lds_seedvr2 import seedvr2_helper as seed
    monkeypatch.setattr(seed, '_nodes_ok_until', 0)
    cfg.save_config({'comfyui': {'base_dir': str(tmp_path / 'not-installed')}})
    calls = _object_info_transport(monkeypatch, [])
    url = _source_url(app, tmp_path, surface)
    response = app.test_client().post(url, json={'engine': 'seedvr2'})
    assert response.status_code == 409, response.get_json()
    body = response.get_json()
    missing = body['seedvr2_missing']
    assert missing['assets'] == ['seedvr2_model', 'seedvr2_vae']
    assert missing['nodes'] == sorted(seed.SEEDVR2_NODE_CLASSES)
    assert len(missing['files']) == 2 and missing['node_packs']
    assert all({'path', 'source', 'kind'} <= file.keys() for file in missing['files'])
    assert body['downloading'] == [] and body['ok'] is False
    assert 'SeedVR2' in body['error'] and len(calls) == 1
    _assert_no_render(app, surface)


def test_bank_busy_gpu_keeps_503_after_restoration_mapping(factory, tmp_path, monkeypatch):
    from app.services import image_bank_service as banks
    app = factory({'seedvr2'})
    from lds_seedvr2 import seedvr2_helper as seed
    monkeypatch.setattr(seed, '_nodes_ok_until', 0)
    base = tmp_path / 'comfy'
    models = base / 'models' / 'SEEDVR2'
    models.mkdir(parents=True)
    (base / 'main.py').write_text('# fixture', encoding='utf-8')
    for name in (seed.CANONICAL_DIT, seed.CANONICAL_VAE):
        (models / name).write_bytes(b'fixture weights; inference is forbidden')
    cfg.save_config({'comfyui': {'base_dir': str(base)}})
    calls = _object_info_transport(monkeypatch, seed.SEEDVR2_NODE_CLASSES)
    monkeypatch.setattr(banks, '_gpu_busy_reason', lambda: 'A training run is using the GPU')
    url = _source_url(app, tmp_path, 'bank')
    response = app.test_client().post(url, json={'engine': 'seedvr2'})
    assert response.status_code == 503
    assert response.get_json() == {'error': 'A training run is using the GPU'}
    assert len(calls) == 1
    _assert_no_render(app, 'bank')
