"""Exercise recovery through the real plugin, SDK, transaction and media route."""
import copy
import json
from types import SimpleNamespace

import pytest
import requests

pytestmark = pytest.mark.plugins('video')
PREFIX = 'local_lds_video_test_1234abcd'
FILENAME = PREFIX + '_00001_.mp4'
INPUT = 'lds_vref_' + 'a' * 32 + '.mp4'
WORKFLOW = {
    '1': {'class_type': 'LoadVideo', 'inputs': {'file': 'reference.mp4'}},
    '2': {'class_type': 'SaveVideo', 'inputs': {'video': ['1', 0], 'filename_prefix': PREFIX}},
}


def _mp4(path, workflow):
    av = pytest.importorskip('av')
    with av.open(str(path), 'w', options={'movflags': 'use_metadata_tags'}) as container:
        container.metadata['prompt'] = json.dumps(workflow)
        stream = container.add_stream('libx264', rate=24)
        stream.width = stream.height = 16
        stream.pix_fmt = 'yuv420p'
        frame = av.VideoFrame(16, 16, 'yuv420p')
        for plane in frame.planes:
            plane.update(bytes([128]) * plane.buffer_size)
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


@pytest.fixture()
def recovery_clip(app, tmp_path, monkeypatch):
    from app.extensions import db
    from app.models import ImageGenerationQueue
    from lds_sdk.video_host.config import LOCAL_USER
    from lds_video.models import VideoTestClip
    from lds_sdk.video_host import studio
    directory = tmp_path / 'comfy-output'
    directory.mkdir()
    monkeypatch.setattr(studio, 'comfy_output_dir', lambda: str(directory))
    with app.app_context():
        job = ImageGenerationQueue(job_id='recovery-job', user_id=LOCAL_USER, status='completed',
                                   comfyui_prompt_id='render-id', workflow_data=json.dumps(WORKFLOW),
                                   result_filename=INPUT)
        clip = VideoTestClip(job_id=job.job_id, user_id=LOCAL_USER, status='done',
                             filename=INPUT, mode='ref2va', prompt='A neutral test scene.')
        db.session.add_all([job, clip])
        db.session.commit()
        return clip.id, directory


def _history(monkeypatch, mode):
    from lds_video import video_result_recovery as recovery
    entry = {'status': {'status_str': 'success', 'completed': True},
             'outputs': {'1': {'images': [{'filename': INPUT, 'type': 'input'}]},
                         '2': {'images': [{'filename': FILENAME, 'type': 'output'}]}}}
    if mode == 'failed':
        entry['status']['status_str'] = 'error'
    def get(*args, **kwargs):
        if mode == 'offline':
            raise requests.ConnectionError('ComfyUI is stopped')
        return SimpleNamespace(raise_for_status=lambda: None,
                               json=lambda: {} if mode == 'cleared' else {'render-id': entry})
    monkeypatch.setattr(recovery.requests, 'get', get)


@pytest.mark.parametrize('history', ['available', 'cleared', 'offline'])
def test_playback_recovers_and_commits_the_saved_mp4(client, app, recovery_clip, monkeypatch, history):
    from app.extensions import db
    from app.models import ImageGenerationQueue
    from lds_video.models import VideoTestClip
    cid, output = recovery_clip
    embedded = copy.deepcopy(WORKFLOW)
    embedded['1']['is_changed'] = 'comfy-cache-value'
    _mp4(output / FILENAME, embedded)
    expected = (output / FILENAME).read_bytes()
    _history(monkeypatch, history)
    response = client.get(f'/api/video-studio/clip/{cid}/video', headers={'Range': 'bytes=0-63'})
    assert response.status_code == 206
    assert response.data == expected[:64]
    response.close()
    with app.app_context():
        assert db.session.get(VideoTestClip, cid).filename == FILENAME
        assert ImageGenerationQueue.query.filter_by(job_id='recovery-job').one().result_filename == FILENAME
    # A later request works from LDS's file, without ComfyUI history or output.
    response = client.get(f'/api/video-studio/clip/{cid}/video')
    assert response.status_code == 200 and response.data == expected
    response.close()


@pytest.mark.parametrize('failure', ['other_owner', 'wrong_graph', 'ambiguous', 'invalid_mp4', 'failed'])
def test_recovery_never_claims_an_unproven_file(client, app, recovery_clip, monkeypatch, failure):
    from app.extensions import db
    from app.models import ImageGenerationQueue
    from lds_video.models import VideoTestClip
    cid, output = recovery_clip
    embedded = copy.deepcopy(WORKFLOW)
    if failure == 'wrong_graph':
        embedded['1']['inputs']['file'] = 'another-reference.mp4'
    if failure == 'invalid_mp4':
        (output / FILENAME).write_bytes(b'incomplete')
    else:
        _mp4(output / FILENAME, embedded)
    if failure == 'ambiguous':
        _mp4(output / (PREFIX + '_00002_.mp4'), embedded)
    if failure == 'other_owner':
        with app.app_context():
            ImageGenerationQueue.query.filter_by(job_id='recovery-job').one().user_id = 'another-user'
            db.session.commit()
    _history(monkeypatch, 'failed' if failure == 'failed' else 'cleared')
    response = client.get(f'/api/video-studio/clip/{cid}/video')
    assert response.status_code == 404
    with app.app_context():
        assert db.session.get(VideoTestClip, cid).filename == INPUT
        assert ImageGenerationQueue.query.filter_by(job_id='recovery-job').one().result_filename == INPUT
    assert (output / FILENAME).is_file()
