import json
import pytest
import app.models  # noqa: F401 -- declare shared mappings before plugin models
from lds_video import video_test_studio as vts
from lds_video import h3_performance as perf

pytestmark = pytest.mark.plugins('video')


@pytest.mark.parametrize('mode', ['t2v', 'i2v', 'ref2va'])
def test_performance_chain_and_recipe(mode):
    refs = [{'kind': 'image', 'name': 'lds_vref_' + 'a' * 32 + '.png'}]
    built = vts.build_workflow(prompt='A dancer follows the reference choreography.',
        mode=mode, image='start.png' if mode == 'i2v' else None,
        references=refs if mode == 'ref2va' else None,
        fused=mode != 'ref2va', ref_base='fused' if mode == 'ref2va' else 'official',
        h3_attention='sage', h3_spectrum=True, h3_video_vae='int8', h3_video_writer='fast',
        performance_classes={perf.FAST_WRITER, vts.BLOCK_ATTN_CLASS})
    wf = built['workflow']
    assert wf[vts.N_UNET]['inputs']['unet_name'] == perf.FUSED_MODEL
    assert wf[vts.N_GUIDER]['inputs']['model'] == wf[vts.N_SCHEDULER]['inputs']['model'] == ['1302', 0]
    assert wf['1302']['inputs']['model'] == ['1301', 0]
    assert wf['1301']['inputs']['model'] == ['1300', 0]
    assert wf['1300']['inputs']['shift_video'] == 12.0
    assert wf[vts.N_VAE_VIDEO]['inputs']['vae_name'] == vts.VIDEO_VAE_INT8
    assert wf[vts.N_SAVE]['class_type'] == perf.FAST_WRITER
    assert wf[vts.N_SAVE]['inputs']['async_write'] is False
    assert wf[vts.N_SAVE]['inputs']['audio'] == wf[vts.N_CREATE_VIDEO]['inputs']['audio']
    assert built['steps'] == 8 and built['accel'] == ''
    assert built['generation_settings']['fused'] is True
    assert built['generation_settings']['h3_spectrum'] is True
    assert '600' not in wf
    if mode == 'ref2va':
        assert built['generation_settings']['ref_base'] == 'fused'
        assert 'first_frame' not in wf[vts.N_COND]['inputs']
        assert not any(n['class_type'] == 'MiniMaxH3AddGuide' for n in wf.values())


@pytest.mark.parametrize('options', [
    {'fused': True, 'accel': 'turbo'}, {'ref_base': 'fused', 'accel': 'ref8'},
    {'h3_attention': 'sage', 'sparse': 'max'}, {'h3_spectrum': True, 'accel': 'vdn'},
    {'h3_spectrum': 'true'}, {'h3_video_vae': 'missing'}, {'h3_attention': 'invalid'},
])
def test_invalid_performance_combinations_fail_before_render(options):
    with pytest.raises(ValueError):
        vts.build_workflow(prompt='A dancer moves.', mode='t2v', **options)


def test_media_recovers_only_after_the_correct_file_arrives(app, client, monkeypatch, tmp_path):
    from app.extensions import db
    from app.models import ImageGenerationQueue
    from lds_video.models import VideoTestClip
    from lds_video import video_result_recovery as recovery
    from lds_sdk.video_host import config as cfg
    from types import SimpleNamespace
    old = 'lds_vref_' + 'a' * 32 + '.mp4'
    history = {'p': {'status': {'status_str': 'success', 'completed': True}, 'outputs': {
        '902': {'images': [{'filename': old, 'type': 'input'}]},
        '92': {'images': [{'filename': 'saved.mp4', 'type': 'output'}]}}}}
    monkeypatch.setattr(recovery.requests, 'get', lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: history))
    monkeypatch.setattr(cfg, 'get', lambda *a, **k: 'http://comfy.test:8188')
    monkeypatch.setattr(vts, 'clips_dir', lambda: tmp_path)
    monkeypatch.setattr(vts, '_bring_clip_home', lambda name: None)
    with app.app_context():
        job = ImageGenerationQueue(job_id='recovery', user_id='local', status='completed',
            comfyui_prompt_id='p', result_filename=old,
            workflow_data=json.dumps({'92': {'class_type': 'SaveVideo'}}))
        clip = VideoTestClip(job_id='recovery', user_id='local', status='done', filename=old,
                             prompt='A dancer moves.', mode='ref2va')
        db.session.add_all([job, clip]); db.session.commit()
        cid = clip.id
        assert recovery.recover(clip) is False
        assert clip.filename == old
        monkeypatch.setattr(vts, '_bring_clip_home', lambda name: (tmp_path / name).write_bytes(b'correct mp4'))
    response = client.get(f'/api/video-studio/clip/{cid}/video')
    assert response.status_code == 200 and response.data == b'correct mp4'
    with app.app_context():
        assert db.session.get(VideoTestClip, cid).filename == 'saved.mp4'
        assert ImageGenerationQueue.query.filter_by(job_id='recovery').one().result_filename == 'saved.mp4'


def test_route_records_the_selected_performance_controls(client, app, monkeypatch):
    from app.job_queue import queue_manager
    from app.extensions import db
    from lds_video.models import VideoTestClip
    monkeypatch.setattr('app.capabilities.probe_comfyui', lambda: {'ok': True})
    monkeypatch.setattr(vts, 'registered_classes', lambda: {perf.FAST_WRITER, vts.BLOCK_ATTN_CLASS})
    monkeypatch.setattr(vts, 'preflight', lambda wf: None)
    monkeypatch.setattr(queue_manager, 'add_job', lambda **kw: kw['job_id'])
    selected = dict(fused=True, h3_attention='sage', h3_spectrum=True,
                    h3_video_vae='int8', h3_video_writer='fast')
    reply = client.post('/api/video-studio/generate', json={
        'prompt': 'A dancer follows the choreography.', 'mode': 't2v', **selected})
    assert reply.status_code == 200, reply.get_json()
    with app.app_context():
        clip = db.session.get(VideoTestClip, reply.get_json()['clip_id'])
        settings = json.loads(clip.generation_settings)
        assert {key: settings[key] for key in selected} == selected


def test_writer_install_is_owned_and_repeatable(monkeypatch, tmp_path):
    from pathlib import Path
    from urllib.parse import urlsplit
    from lds_video.performance_install import install_writer
    from lds_sdk.video_host import config as cfg
    monkeypatch.setattr(cfg, 'comfyui_dir', lambda: str(tmp_path))
    source = Path(__file__).resolve().parents[2] / 'bundled/video/authoring/comfy_nodes/lds_h3_fast_writer'
    def fetch(url):
        return (source / urlsplit(url).path.rsplit('/', 1)[-1]).read_bytes().replace(b'\r\n', b'\n')
    custom = tmp_path / 'custom_nodes'; custom.mkdir()
    target = custom / 'lds_h3_fast_writer'; target.mkdir()
    foreign = target / '__init__.py'; foreign.write_text('foreign content')
    assert install_writer(log=lambda _: None, fetch=fetch) == 1
    assert foreign.read_text() == 'foreign content'
    foreign.unlink(); target.rmdir()
    assert install_writer(log=lambda _: None, fetch=lambda _: b'wrong source') == 1
    assert not target.exists()
    assert install_writer(log=lambda _: None, fetch=fetch) == 0
    assert install_writer(log=lambda _: None, fetch=fetch) == 0
    assert 'LDSH3FastWriteVideo' in foreign.read_text()
    assert (target / 'LICENSE').is_file() and (target / 'NOTICE').is_file()
