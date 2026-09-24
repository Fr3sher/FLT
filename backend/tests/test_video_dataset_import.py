"""Direct datasets: real CPU encoding, file/web parity and retry safety."""
import io
from pathlib import Path
import shutil
import subprocess
import time

import pytest

import app.models  # noqa: F401
from lds_sdk.video_host import bank_jobs
from lds_video import video_bank_service as svc, video_dataset_import as intake
from lds_video.models import VideoBank

pytestmark = pytest.mark.plugins('video')


def _create(client, **extra):
    return client.post('/api/video-datasets', json={
        'name': 'Motion study', 'target_profile': 'wan22_14b', 'frames': 17,
        'trigger_word': 'motion_token', **extra,
    })


def _wait(client, dataset_id):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        data = client.get(f'/api/video-dataset/{dataset_id}').get_json()
        job = data.get('import_activity')
        if job and job['finished']:
            assert not job['error'], job
            return data
        time.sleep(.03)
    pytest.fail('Import did not finish')


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / 'source.mp4'
    subprocess.run([svc._ffmpeg_or_raise(), '-y', '-f', 'lavfi', '-i',
                    'testsrc2=size=64x64:rate=16:duration=11', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(path)], check=True, capture_output=True)
    return path


def test_create_empty_without_bank_and_reject_bad_geometry(client, app):
    result = _create(client)
    assert result.status_code == 201, result.get_json()
    data = result.get_json()
    assert data['clips'] == 0 and data['frames'] == 17 and data['fps'] == 16
    assert Path(data['output_dir']).is_dir()
    with app.app_context():
        assert VideoBank.query.count() == 0
    assert _create(client, frames=18).status_code == 400
    assert _create(client, name=' ').status_code == 400
    assert _create(client, target_profile='missing').status_code == 400


def test_uploaded_clips_are_trainable_and_reimport_is_idempotent(client, app, clip):
    import av
    dataset_id = _create(client).get_json()['id']
    def upload():
        return client.post(f'/api/video-dataset/{dataset_id}/import', data={
            'files': [(io.BytesIO(clip.read_bytes()), '../../source.mp4') for _ in range(7)],
            'slice_long': 'true',
        })
    result = upload()
    assert result.status_code == 202, result.get_json()
    assert result.get_json()['queued'] == 7
    data = _wait(client, dataset_id)
    assert data['import_activity']['done'] == 7
    assert data['clips'] == 10, data['import_activity']
    assert (data['width'], data['height']) == (64, 64)
    from lds_video import video_training
    with app.app_context():
        ds = svc.get_video_dataset('local', dataset_id)
        config = video_training.build_job_config(ds, ds.output_dir, 1000, training_folder=str(clip.parent))
        assert config['config']['process'][0]['datasets'][0]['num_frames'] == 17
    for row in data['items']:
        path = Path(data['output_dir']) / row['filename']
        assert path.with_suffix('.txt').read_text() == 'motion_token'
        with av.open(str(path)) as container:
            assert len(list(container.decode(video=0))) == 17
        assert row['source_bank_id'] is None
        assert row['src_relpath'] == 'source.mp4'
    assert upload().status_code == 202
    repeated = _wait(client, dataset_id)
    assert repeated['clips'] == 10
    assert 'already imported' in repeated['import_activity']['detail']
    assert all(p.suffix in ('.mp4', '.txt') for p in Path(data['output_dir']).iterdir())


def test_web_import_downloads_selected_videos_and_reports_partial_failure(client, clip, monkeypatch):
    def download(item, staging):
        if item['url'].endswith('bad.mp4'):
            return 'errors', None
        path = Path(staging) / 'download'
        shutil.copyfile(clip, path)
        return 'ok', str(path)
    monkeypatch.setattr(svc, '_download_scrape_video', download)
    dataset_id = _create(client).get_json()['id']
    url = f'/api/video-dataset/{dataset_id}/scrape-import'
    assert client.post(url, json={'items': [{'url': 'https://example.test/photo', 'type': 'image'}]}).status_code == 400
    result = client.post(url, json={'items': [
        {'url': 'https://example.test/bad.mp4', 'type': 'video'},
        *[{'url': f'https://example.test/good-{i}.mp4', 'type': 'video', 'title': 'Not a caption'}
          for i in range(7)],
    ]})
    assert result.status_code == 202
    assert result.get_json()['queued'] == 8
    data = _wait(client, dataset_id)
    assert data['import_activity']['done'] == 8
    assert data['clips'] == 1 and data['items'][0]['caption'] == ''
    assert '1 errors' in data['import_activity']['detail']


def test_import_lease_protects_dataset_and_other_users(client, app):
    dataset_id = _create(client).get_json()['id']
    lease = bank_jobs.reserve(intake.job_key(dataset_id), 'video_import')
    try:
        assert client.delete(f'/api/video-dataset/{dataset_id}').status_code == 409
        with app.app_context():
            from lds_video import video_training
            ds = svc.get_video_dataset('local', dataset_id)
            with pytest.raises(video_training.VideoTrainingUnsupported, match='import to finish'):
                video_training.build_job_config(ds, ds.output_dir, 1000)
            with pytest.raises(ValueError, match='not found'):
                intake.start(app, 'someone-else', dataset_id, items=[])
        assert client.post(f'/api/video-dataset/{dataset_id}/import/cancel').get_json()['ok']
    finally:
        bank_jobs.abort(lease)
    assert client.delete(f'/api/video-dataset/{dataset_id}').status_code == 200
    assert client.get(f'/api/video-dataset/{dataset_id}').status_code == 404


def test_short_or_broken_upload_leaves_no_training_files(client, clip):
    dataset_id = _create(client, frames=193).get_json()['id']
    result = client.post(f'/api/video-dataset/{dataset_id}/import', data={
        'files': [(io.BytesIO(clip.read_bytes()), 'short.mp4'), (io.BytesIO(b'not video'), 'broken.mp4')],
    })
    assert result.status_code == 202
    data = _wait(client, dataset_id)
    assert data['clips'] == 0
    assert 'too short' in data['import_activity']['detail']
    assert 'not video' in data['import_activity']['detail']
    assert list(Path(data['output_dir']).iterdir()) == []
