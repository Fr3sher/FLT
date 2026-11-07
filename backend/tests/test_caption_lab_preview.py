"""🧪 Caption Lab — per-candidate preview endpoint. Runs ONE caption config on ONE
image and returns the text WITHOUT persisting it (ephemeral A/B probe). The Ollama
vision seam is mocked so the pass is hermetic, exactly like the image-bank tests."""
import json
import os

import pytest
from PIL import Image


def _use_ollama_backend(app):
    """Force the Ollama backend so JoyCaption (ai-toolkit) is skipped in the preview."""
    with app.app_context():
        import app.config as cfg
        cfg.save_config({'captioning': {'backend': 'ollama'}})


def _mock_vision(monkeypatch, caption='a plain description', capture=None):
    """Mock describe_image_ollama; when `capture` is a dict, record the prompt it saw
    so a test can assert the vocabulary/instructions were appended."""
    from app.services import vision_ollama

    def fake_describe(image_bytes, prompt, *a, **k):
        if capture is not None:
            capture['prompt'] = prompt
            capture['model'] = k.get('model')
        return caption

    monkeypatch.setattr(vision_ollama, 'describe_image_ollama', fake_describe)
    monkeypatch.setattr(vision_ollama, 'unload_vision_model', lambda *a, **k: True)


def _dataset_with_image(client, app, filename='a.png', caption=''):
    """Create a dataset + one kept image, writing the file to the dataset dir so the
    preview's on-disk check passes. Returns (dataset_id, image_id)."""
    ds_id = client.post('/api/dataset/create',
                        json={'name': 'Lab', 'trigger_word': 'lab'}).get_json()['id']
    with app.app_context():
        from app.models import FaceDatasetImage
        from app.services import face_dataset_service as svc
        from app.services.dataset_storage import ensure_dataset_dir
        Image.new('RGB', (64, 64), (128, 128, 128)).save(
            os.path.join(ensure_dataset_dir(ds_id), filename))
        img = FaceDatasetImage(dataset_id=ds_id, status='keep', source='upload',
                               filename=filename, caption=caption)
        svc.db.session.add(img)
        svc.db.session.commit()
        return ds_id, img.id


def _preview(client, ds_id, img_id, **body):
    return client.post(
        f'/api/dataset/{ds_id}/image/{img_id}/caption/preview', json=body)


# --- happy path ---------------------------------------------------------------
def test_preview_returns_caption_without_persisting(client, app, monkeypatch):
    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app, caption='ORIGINAL')
    _mock_vision(monkeypatch, caption='a candidate caption')

    r = _preview(client, ds_id, img_id)
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body['ok'] is True
    assert body['caption'] == 'a candidate caption'
    assert body['chars'] == len('a candidate caption')
    assert 'duration_ms' in body and body['cancelled'] is False

    # The stored caption must be untouched — a preview never writes.
    with app.app_context():
        from app.models import FaceDatasetImage
        from app.services import face_dataset_service as svc
        assert svc.db.session.get(FaceDatasetImage, img_id).caption == 'ORIGINAL'


def test_preview_appends_vocabulary_and_instructions(client, app, monkeypatch):
    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app)
    capture = {}
    _mock_vision(monkeypatch, capture=capture)

    r = _preview(client, ds_id, img_id, vocabulary='explicit',
                 instructions='Name the visible clothing colors.')
    assert r.status_code == 200, r.get_json()
    # Both the vocabulary preset register and the free instructions ride in the prompt.
    assert 'crude anatomical terms' in capture['prompt']
    assert 'Name the visible clothing colors.' in capture['prompt']


def test_preview_default_backend_leaves_prompt_clean(client, app, monkeypatch):
    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app)
    capture = {}
    _mock_vision(monkeypatch, capture=capture)

    r = _preview(client, ds_id, img_id)
    assert r.status_code == 200
    # No vocabulary, no instructions → the dataset prompt is not augmented.
    assert 'crude anatomical terms' not in capture['prompt']


def test_preview_accepts_valid_or_empty_ollama_model(client, app, monkeypatch):
    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app)
    capture = {}
    _mock_vision(monkeypatch, capture=capture)

    model = 'registry.example:5000/team/' + ('a' * 160) + ':latest'
    assert len(model) <= 200
    r = _preview(client, ds_id, img_id, ollama_model=f'  {model}  ')
    assert r.status_code == 200, r.get_json()
    assert capture['model'] == model

    r = _preview(client, ds_id, img_id, ollama_model='')
    assert r.status_code == 200, r.get_json()
    assert capture['model'] is None


# --- guards -------------------------------------------------------------------
def test_preview_409_when_batch_in_progress(client, app, monkeypatch):
    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app)
    _mock_vision(monkeypatch)
    from app.services import dataset_activity
    dataset_activity.begin(ds_id, 'caption', total=5)  # a real pass owns the GPU
    try:
        r = _preview(client, ds_id, img_id)
        assert r.status_code == 409
        assert 'batch' in r.get_json()['error'].lower()
    finally:
        dataset_activity.reset()


def test_preview_400_on_unknown_image(client, app):
    _use_ollama_backend(app)
    ds_id, _ = _dataset_with_image(client, app)
    r = _preview(client, ds_id, 999999)
    assert r.status_code == 400


def test_preview_400_on_invalid_backend(client, app):
    ds_id, img_id = _dataset_with_image(client, app)
    r = _preview(client, ds_id, img_id, backend='nonsense')
    assert r.status_code == 400


def test_preview_route_400_on_invalid_ollama_model(client, app):
    ds_id, img_id = _dataset_with_image(client, app)
    invalid = (None, 123, False, [], {}, 'bad model!', '/leading',
               'valid:tag\n', 'valid:tag\r\nsecond:tag', 'valid:tag\u2028',
               'a' * 201)
    for model in invalid:
        r = _preview(client, ds_id, img_id, ollama_model=model)
        assert r.status_code == 400, (model, r.get_json())
        assert 'ollama_model' in r.get_json()['error']


def test_preview_route_400_on_non_object_body(client, app):
    ds_id, img_id = _dataset_with_image(client, app)
    url = f'/api/dataset/{ds_id}/image/{img_id}/caption/preview'
    for body in ([], ['model'], 123, False, 'model'):
        r = client.post(url, json=body)
        assert r.status_code == 400, (body, r.get_json())
        assert 'object' in r.get_json()['error']


def test_preview_service_rejects_non_string_ollama_model(client, app):
    ds_id, img_id = _dataset_with_image(client, app)
    with app.app_context():
        from app.config import LOCAL_USER
        from app.services import face_dataset_service as svc
        for model in (None, 123, False, [], {}):
            with pytest.raises(ValueError, match='ollama_model'):
                svc.preview_caption(
                    LOCAL_USER, ds_id, img_id, ollama_model=model)


def test_preview_404_on_unknown_dataset(client, app):
    r = client.post('/api/dataset/424242/image/1/caption/preview', json={})
    assert r.status_code == 404


# --- cancel (service level: the stop path the route wires to Stop) ------------
def test_preview_cancel_returns_empty_flagged(client, app, monkeypatch):
    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app)
    _mock_vision(monkeypatch, caption='should never be reached')
    with app.app_context():
        from app.config import LOCAL_USER
        from app.services import face_dataset_service as svc
        result = svc.preview_caption(LOCAL_USER, ds_id, img_id, backend='ollama',
                                     should_cancel=lambda: True)
    assert result['caption'] == ''
    assert result['cancelled'] is True


def test_preview_appends_length_preset(client, app, monkeypatch):
    """The Lab compares length presets too - the preview appends the same text the
    dataset pass would, and refuses an unknown value with a 400."""
    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app)
    capture = {}
    _mock_vision(monkeypatch, capture=capture)

    r = _preview(client, ds_id, img_id, length='concise')
    assert r.status_code == 200, r.get_json()
    assert 'Keep the caption SHORT' in capture['prompt']

    assert _preview(client, ds_id, img_id, length='epic').status_code == 400


@pytest.mark.parametrize('kind,train_type,fidelity', [
    ('character', 'zimage', 'face'),
    ('character', 'sdxl', 'body'),
    ('style', 'zimage', 'face'),
    ('style', 'sdxl', 'face'),
    ('concept', 'zimage', 'face'),
])
@pytest.mark.parametrize('backend', ['ollama', 'joycaption'])
def test_lab_sends_the_same_prompt_as_the_dataset_batch(
        client, app, monkeypatch, kind, train_type, fidelity, backend):
    """Issue #68: compare actual inference arguments, not two prompt builders."""
    from app.config import LOCAL_USER
    from app.models import FaceDatasetImage
    from app.services import face_dataset_service as svc, joycaption, vision_ollama

    ds_id, img_id = _dataset_with_image(client, app)
    calls = []
    answer = 'full body shot, wearing a blue jacket beside a window, warm afternoon light'

    def describe(image, prompt, **kwargs):
        calls.append((prompt, kwargs.get('model')))
        return answer

    def joy(paths, prompt, **kwargs):
        calls.append((prompt, None))
        return dict.fromkeys(paths, answer)

    monkeypatch.setattr(vision_ollama, 'describe_image_ollama', describe)
    monkeypatch.setattr(vision_ollama, 'unload_vision_model', lambda **kw: True)
    monkeypatch.setattr(joycaption, 'is_available', lambda: True)
    monkeypatch.setattr(joycaption, 'caption_images_joycaption', joy)
    # No expansion call/cached write is needed to exercise the concept caption prompt.
    monkeypatch.setattr(svc, '_get_concept_terms', lambda *a, **kw: [])
    with app.app_context():
        ds = svc.get_dataset(LOCAL_USER, ds_id)
        ds.kind, ds.train_type, ds.fidelity = kind, train_type, fidelity
        ds.concept_desc = 'holding an umbrella'
        ds.caption_options = json.dumps({
            'backend': backend, 'ollama_model': 'candidate:latest',
            'vocabulary': 'clinical', 'length': 'detailed',
            'instructions': 'Mention visible clothing colors.',
            'appearance': {'hair': 'describe', 'makeup': 'describe',
                           'facial_hair': 'omit', 'glasses': 'describe'},
        })
        svc.db.session.commit()
        original_options = ds.caption_options

    response = _preview(client, ds_id, img_id)
    assert response.status_code == 200, response.get_json()
    preview = response.get_json()
    preview_calls = list(calls)
    assert len(preview_calls) == 1
    assert preview['prompt'] == preview_calls[0][0]
    assert 'Mention visible clothing colors.' in preview['prompt']
    assert bool(preview.get('prompt_note')) == (kind == 'concept')
    calls.clear()
    with app.app_context():
        # Preview must neither write a caption nor change the saved method.
        assert not svc.db.session.get(FaceDatasetImage, img_id).caption
        assert svc.get_dataset(LOCAL_USER, ds_id).caption_options == original_options
        assert svc.caption_images(LOCAL_USER, ds_id) == 1
        assert calls == preview_calls
        assert svc.db.session.get(FaceDatasetImage, img_id).caption == preview['caption']


def test_candidate_can_clear_saved_options_without_changing_them(client, app, monkeypatch):
    from app.config import LOCAL_USER
    from app.services import face_dataset_service as svc

    _use_ollama_backend(app)
    ds_id, img_id = _dataset_with_image(client, app)
    capture = {}
    _mock_vision(monkeypatch, capture=capture)
    with app.app_context():
        saved = svc.set_caption_options(LOCAL_USER, ds_id, {
            'backend': 'joycaption', 'ollama_model': 'saved:latest',
            'vocabulary': 'explicit', 'length': 'detailed', 'instructions': 'Saved steer.',
        })
    r = _preview(client, ds_id, img_id, backend='', ollama_model='',
                 vocabulary='', length='', instructions='')
    assert r.status_code == 200, r.get_json()
    assert capture['model'] is None
    assert 'Saved steer.' not in capture['prompt']
    assert 'crude anatomical terms' not in capture['prompt']
    with app.app_context():
        ds = svc.get_dataset(LOCAL_USER, ds_id)
        assert svc.caption_options(ds) == saved
        assert capture['prompt'] == svc._dataset_caption_recipe(ds, saved)[0]
