"""Pixels, retry cache keys and safe refusals for bank edit history."""
import io

from PIL import Image
import pytest

from test_bank_crop_and_improve import _fingerprint, _ids, _mkbank, _photo


def _crop(client, bank_id, image_id, size=200):
    response = client.post(f'/api/bank/{bank_id}/image/{image_id}/crop',
                           json={'x': 0, 'y': 0, 'w': size, 'h': size})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def _undo(client, bank_id, ids):
    response = client.post(f'/api/bank/{bank_id}/edits/undo', json={'image_ids': ids})
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def test_cached_review_tracks_crop_undo_and_recrop(client, app, tmp_path):
    bank_id, _ = _mkbank(client, tmp_path, {'a.jpg': _photo(400, 300)})
    image_id = _ids(app, bank_id)[0]
    url = f'/api/bank/{bank_id}/review-file/{image_id}'

    def review_size():
        response = client.get(url)
        assert response.status_code == 200
        with Image.open(io.BytesIO(response.data)) as image:
            return image.size

    assert review_size() == (400, 300)
    _crop(client, bank_id, image_id, 200)
    assert review_size() == (200, 200)
    _crop(client, bank_id, image_id, 100)
    assert review_size() == (100, 100)
    _undo(client, bank_id, [image_id])
    assert review_size() == (200, 200)
    _undo(client, bank_id, [image_id])
    assert review_size() == (400, 300)
    _crop(client, bank_id, image_id, 150)
    assert review_size() == (150, 150)


def test_crop_upscale_compare_undo_and_retry(client, app, tmp_path, monkeypatch):
    from app.extensions import db
    from app.models import BankImage
    from app.services import image_bank_service as banks, face_dataset_service as fds

    bank_id, src = _mkbank(client, tmp_path, {'a.jpg': _photo()})
    image_id = _ids(app, bank_id)[0]
    original = _fingerprint(src / 'a.jpg')
    crop = _crop(client, bank_id, image_id)
    assert crop['edit_history_count'] == 1
    cropped_bytes = client.get(f'/api/bank/{bank_id}/file/{image_id}').data
    output = io.BytesIO()
    Image.new('RGB', (400, 400), 'blue').save(output, 'PNG')
    monkeypatch.setattr(fds, '_enqueue_improve', lambda *a, **kw: 'test-job')
    monkeypatch.setattr(banks, '_await_queue_job', lambda *a, **kw: ('completed', 'result', None))
    monkeypatch.setattr(banks, '_fetch_comfy_result', lambda *a: output.getvalue())
    monkeypatch.setattr(banks, '_finish_improved_blob', lambda *a: None)
    with app.app_context():
        job = {'cancelled': False, 'done': 0, 'total': 0}
        banks._improve_job(bank_id, 'seedvr2')(job)
        row = db.session.get(BankImage, image_id)
        assert row.edit_method == 'improve'
        assert row.edit_generation == 2
    before = client.get(f'/api/bank/{bank_id}/file/{image_id}?previous=1')
    assert before.status_code == 200
    assert before.data == cropped_bytes
    restored = _undo(client, bank_id, [image_id])
    assert restored['restored'] == 1
    assert restored['images'][0]['edit_method'] == 'crop'
    assert restored['images'][0]['width'] == 200
    assert client.get(f'/api/bank/{bank_id}/file/{image_id}').data == cropped_bytes
    with app.app_context():
        assert banks._improve_pool_query(bank_id).count() == 1
        assert not banks.edited_image_path(bank_id, image_id, 2).exists()
    # A different edit after undo must never reuse the old upscale's cache key.
    assert _crop(client, bank_id, image_id, 100)['edit_generation'] == 3
    assert _undo(client, bank_id, [image_id])['restored'] == 1
    assert _undo(client, bank_id, [image_id])['images'][0]['edit_method'] is None
    assert _fingerprint(src / 'a.jpg') == original
    assert client.get(f'/api/bank/{bank_id}/file/{image_id}?previous=1').status_code == 404


@pytest.mark.parametrize('damage', ['missing', 'changed'])
def test_unavailable_previous_copy_is_not_replaced_by_original(client, app, tmp_path, damage):
    from app.services import image_bank_service as banks

    bank_id, _ = _mkbank(client, tmp_path, {'a.jpg': _photo()})
    image_id = _ids(app, bank_id)[0]
    _crop(client, bank_id, image_id)
    _crop(client, bank_id, image_id, 100)
    with app.app_context():
        path = banks.edited_image_path(bank_id, image_id, 1)
        if damage == 'missing':
            path.unlink()
        else:
            Image.new('RGB', (200, 200), 'red').save(path)
    current = client.get(f'/api/bank/{bank_id}/file/{image_id}').data
    assert client.get(f'/api/bank/{bank_id}/file/{image_id}?previous=1').status_code == 404
    result = _undo(client, bank_id, [image_id])
    assert result['restored'] == 0 and result['unavailable'] == [image_id]
    assert client.get(f'/api/bank/{bank_id}/file/{image_id}').data == current


def test_selected_undo_and_full_revert_clean_history(client, app, tmp_path):
    from app.extensions import db
    from app.models import BankImage
    from app.services import image_bank_service as banks

    bank_id, _ = _mkbank(client, tmp_path, {'a.jpg': _photo(), 'b.jpg': _photo()})
    a, b = _ids(app, bank_id)
    for image_id in (a, b):
        _crop(client, bank_id, image_id)
        _crop(client, bank_id, image_id, 100)
    assert _undo(client, bank_id, [a])['restored'] == 1
    with app.app_context():
        assert db.session.get(BankImage, b).edit_generation == 2
    result = client.post(f'/api/bank/{bank_id}/edits/revert', json={}).get_json()
    assert result['reverted'] == 2
    with app.app_context():
        assert not list(banks._edited_dir(bank_id).glob('*.webp'))
        assert db.session.get(BankImage, b).edit_history is None
    assert _undo(client, bank_id, [])['restored'] == 0
    assert _crop(client, bank_id, b)['edit_generation'] == 3


def test_first_edit_undo_restores_rotation_and_displayed_dimensions(client, app, tmp_path):
    bank_id, _ = _mkbank(client, tmp_path, {'a.jpg': _photo(400, 300)})
    image_id = _ids(app, bank_id)[0]
    client.post(f'/api/bank/{bank_id}/rotate', json={'ids': [image_id], 'degrees': 90})
    before = client.get(f'/api/bank/{bank_id}/file/{image_id}').data
    _crop(client, bank_id, image_id)
    assert client.get(f'/api/bank/{bank_id}/file/{image_id}?previous=1').data == before
    state = _undo(client, bank_id, [image_id])['images'][0]
    assert (state['width'], state['height'], state['rotation']) == (300, 400, 90)
    assert client.get(f'/api/bank/{bank_id}/file/{image_id}').data == before


def test_legacy_edit_does_not_invent_history(client, app, tmp_path):
    from app.extensions import db
    from app.models import BankImage

    bank_id, _ = _mkbank(client, tmp_path, {'a.jpg': _photo()})
    image_id = _ids(app, bank_id)[0]
    _crop(client, bank_id, image_id)
    with app.app_context():
        row = db.session.get(BankImage, image_id)
        row.edit_history = row.edit_sequence = None
        db.session.commit()
    assert _undo(client, bank_id, [image_id])['restored'] == 0
    assert client.get(f'/api/bank/{bank_id}/file/{image_id}?previous=1').status_code == 404
    _crop(client, bank_id, image_id, 100)
    assert _undo(client, bank_id, [image_id])['images'][0]['edit_generation'] == 1


def test_undo_refuses_an_active_bank_pass(client, app, tmp_path):
    from app.services import bank_jobs

    bank_id, _ = _mkbank(client, tmp_path, {'a.jpg': _photo()})
    image_id = _ids(app, bank_id)[0]
    _crop(client, bank_id, image_id)
    with bank_jobs.mutation_lease(bank_id, 'test'):
        response = client.post(f'/api/bank/{bank_id}/edits/undo',
                               json={'image_ids': [image_id]})
        assert response.status_code == 409
    assert _undo(client, bank_id, [image_id])['restored'] == 1
