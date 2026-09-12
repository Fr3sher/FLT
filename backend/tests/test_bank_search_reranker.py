"""Search contracts at the API, worker-result and installer boundaries."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from tests.test_image_bank_text_search import _emb, _fake_encoder, _mkbank, _write_score_cache


@pytest.fixture
def indexed_bank(client, app, tmp_path, monkeypatch):
    names = [f'image-{i:02}.jpg' for i in range(25)]
    bank_id, _ = _mkbank(client, tmp_path, names)
    _write_score_cache(app, bank_id, {name: _emb(1, i / 25) for i, name in enumerate(names)})
    _fake_encoder(monkeypatch, _emb(1, 0))
    return bank_id


@pytest.mark.parametrize('n', [3, 25])
def test_refinement_reorders_only_top_twenty(client, indexed_bank, monkeypatch, n):
    from app.services import bank_search_reranker as service
    url = f'/api/bank/{indexed_bank}/search-text'
    initial = client.post(url, json={'query': 'a landscape', 'n': 25}).get_json()
    seen = []

    def refine(query, images):
        seen.extend(images)
        ids = [r['id'] for r in images][::-1]
        return ids, {'count': len(ids), 'model_key': 'test-reranker',
                     'scores': {image_id: i / 20 for i, image_id in enumerate(ids)}}

    monkeypatch.setattr(service, 'rerank', refine)
    response = client.post(url, json={'query': 'a landscape', 'n': n, 'rerank': True})
    assert response.status_code == 200, response.get_json()
    result = response.get_json()
    assert len(seen) == 20
    expected = initial['image_ids'][:20][::-1] + initial['image_ids'][20:]
    assert result['image_ids'] == expected[:n]
    assert result['reranking']['count'] == 20
    assert result['engine'] == initial['engine']
    original_scores = {r['id']: r['score'] for r in initial['results']}
    assert all(r['score'] == original_scores[r['id']] for r in result['results'])
    assert all('rerank_score' in r for r in result['results'][:20])
    assert all('rerank_score' not in r for r in result['results'][20:])


@pytest.mark.parametrize('value', ['true', 1, None, [], {}])
def test_refinement_requires_a_boolean(client, value):
    response = client.post('/api/bank/1/search-text', json={'query': 'x', 'rerank': value})
    assert response.status_code == 400
    assert 'rerank must' in response.get_json()['error']


@pytest.mark.parametrize('extra', [{'push_down': 'hat'}, {'query': 'portrait -hat'}])
def test_refinement_does_not_silently_undo_exclusions(client, indexed_bank, extra):
    response = client.post(f'/api/bank/{indexed_bank}/search-text',
                           json={'query': 'portrait', 'rerank': True, **extra})
    assert response.status_code == 400
    assert 'Push down' in response.get_json()['error']


def test_failed_refinement_is_not_reported_as_success(client, indexed_bank, monkeypatch):
    from app.services import bank_search_reranker as service
    def fail(*args):
        raise service.RerankError('runtime unavailable')
    monkeypatch.setattr(service, 'rerank', fail)
    response = client.post(f'/api/bank/{indexed_bank}/search-text',
                           json={'query': 'portrait', 'rerank': True})
    assert response.status_code == 503
    assert response.get_json()['reason'] == 'reranker_unavailable'


@pytest.mark.parametrize('rows', [[], [{'id': 1, 'score': float('nan')}],
                                  [{'id': 2, 'score': .2}], [{'id': 1, 'score': True}],
                                  [{'id': 1, 'score': 2}]])
def test_worker_output_is_validated(rows):
    from app.services import bank_search_reranker as service
    with pytest.raises(service.RerankError):
        service.validate_results({'ok': True, 'results': rows}, [{'id': 1}])


def test_cpu_worker_releases_lock_and_detects_replaced_images(app, tmp_path, monkeypatch):
    from PIL import Image
    from app.services import bank_search_reranker as service
    from app.services import bank_reranker_models as assets
    path = tmp_path / 'image.jpg'
    Image.new('RGB', (32, 32), 'red').save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(service, 'status', lambda: {'available': True})
    monkeypatch.setattr(assets, 'device', lambda: 'cpu')
    seen = {}
    def run(argv, **kwargs):
        seen.update(kwargs)
        Image.new('RGB', (32, 32), 'blue').save(path)
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            {'ok': True, 'results': [{'id': 1, 'score': .75}]}))
    monkeypatch.setattr(service.subprocess, 'run', run)
    with app.app_context(), pytest.raises(service.RerankError, match='changed'):
        service.rerank('red image', [{'id': 1, 'path': str(path), 'sha256': digest}])
    assert seen['env']['CUDA_VISIBLE_DEVICES'] == ''
    assert seen['env']['HF_HUB_OFFLINE'] == '1'
    assert not service._lock.locked()


def test_busy_refinement_does_not_start_another_worker():
    from app.services import bank_search_reranker as service
    with service._lock:
        with pytest.raises(service.RerankError, match='Another'):
            service.rerank('x', [{'id': 1}])


def test_missing_weights_never_import_torch(app, monkeypatch):
    from app import capabilities
    from app.services import bank_reranker_models as assets
    monkeypatch.setattr(assets, 'weights_present', lambda: False)
    monkeypatch.setattr(capabilities, '_cached_import', lambda *a: pytest.fail('imported torch'))
    with app.app_context():
        assert capabilities.probe_bank_reranker()['ok'] is False


def test_installation_cannot_succeed_when_verification_times_out(app, monkeypatch):
    import subprocess
    from app import setup_installer as installer
    monkeypatch.setattr(installer, '_bank_scoring_env_python', lambda: '/managed/python')
    monkeypatch.setattr(installer, '_ensure_bank_scoring_env', lambda *a, **k: '/managed/python')
    monkeypatch.setattr(installer, '_install_cpu_torch_pair', lambda *a: 0)
    monkeypatch.setattr(installer, '_run_pip', lambda *a: 0)
    monkeypatch.setattr(installer, '_append', lambda *a: None)
    def timeout(*a, **k):
        raise subprocess.TimeoutExpired('probe', 120)
    monkeypatch.setattr(installer.subprocess, 'run', timeout)
    with app.app_context():
        assert installer._run_bank_reranker('bank_reranker') == 1
