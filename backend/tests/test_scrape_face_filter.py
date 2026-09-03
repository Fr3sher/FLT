"""Face-filter route failures stay visible and never leak downloaded temp files."""

import pytest


@pytest.mark.parametrize('payload', [
    {'suggest_best': True, 'urls': ['https://example.invalid/a.jpg']},
    {
        'reference_urls': ['https://example.invalid/ref.jpg'],
        'urls': ['https://example.invalid/a.jpg'],
    },
])
def test_scoring_error_is_returned_and_every_temp_file_is_removed(
        client, tmp_path, monkeypatch, payload):
    created = []

    def fake_fetch(_url):
        path = tmp_path / f'face-{len(created)}.jpg'
        path.write_bytes(b'not-a-real-image')
        created.append(path)
        return str(path)

    monkeypatch.setattr('app.routes.scrape._fetch_image_to_temp', fake_fetch)
    monkeypatch.setattr(
        'app.services.face_similarity.score_faces',
        lambda *args, **kwargs: (
            {}, {'kind': 'gpu_busy', 'detail': 'the GPU is busy'}))

    response = client.post('/api/scrape/face-filter', json=payload)

    assert response.status_code == 502
    assert response.get_json()['error'] == 'the GPU is busy'
    assert created
    assert all(not path.exists() for path in created)
