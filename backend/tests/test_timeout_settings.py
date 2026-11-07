"""Long repairs and network overrides reach the actual wait/transport boundary."""
import io
import math
from types import SimpleNamespace

import pytest
from PIL import Image

from app import config as cfg, generation_limits, job_queue
from app.extensions import db
from app.models import ImageGenerationQueue
from app.timeout_settings import network_timeout, processing_timeout


@pytest.mark.parametrize('raw', [None, 'bad', True, float('nan'), float('inf'), {}])
def test_bad_multipliers_preserve_budgets(monkeypatch, raw):
    monkeypatch.setattr(cfg, 'get', lambda key: {
        'network_multiplier': raw, 'processing_multiplier': raw})
    assert network_timeout((3, 45)) == (3, 45)
    assert processing_timeout(300) == 300


def test_independent_multipliers_keep_unlimited_and_separate_connect_from_inference(app):
    cfg.save_config({'timeouts': {'network_multiplier': 3, 'processing_multiplier': 2}})
    assert network_timeout((10, 300), processing=True) == (30, 600)
    assert network_timeout((10, 300)) == (30, 900)
    assert network_timeout(20, processing=True) == (60, 40)
    assert network_timeout((10, None)) == (30, None)
    assert network_timeout(None) is None
    assert processing_timeout(None) is None
    assert generation_limits.repair_timeout_seconds() == 600
    assert generation_limits.improve_timeout_seconds() == 3600
    assert generation_limits.generation_timeout_seconds() == 1800
    # Metadata already carries the resolved budget. Never multiply it twice.
    assert generation_limits.generation_timeout_seconds({'processing_timeout_seconds': 2400}) == 2400
    assert math.isinf(generation_limits.generation_timeout_seconds({'processing_timeout_seconds': 0}))


@pytest.mark.parametrize('override', [True, -1, '1200', float('inf'), float('nan'), 8640001])
def test_invalid_job_budget_cannot_remove_worker_limit(app, override):
    assert generation_limits.generation_timeout_seconds({'processing_timeout_seconds': override}) == 900


def test_civitai_upload_scales_at_transport_once(app, monkeypatch):
    from app.services import civitai_publish
    cfg.save_config({'timeouts': {'network_multiplier': 3}})
    seen = {}
    def request(*args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(status_code=200, headers={}, content=b'ok')
    monkeypatch.setattr(civitai_publish.requests, 'request', request)
    civitai_publish._transport('PUT', 'https://example.invalid/upload',
                              timeout=civitai_publish._UPLOAD_TIMEOUT)
    assert seen['timeout'] == (6.1 * 3, 1800)


def test_ollama_response_budget_is_independent_of_connection_budget(app, monkeypatch):
    from app.services import vision_ollama as vo
    cfg.save_config({'timeouts': {'network_multiplier': 3, 'processing_multiplier': 2}})
    monkeypatch.setattr(vo, '_admit_local_ollama', lambda *a, **k: None)
    seen = {}
    def post(*args, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'response': 'ok'})
    monkeypatch.setattr(vo.requests, 'post', post)
    assert vo.generate_text_ollama('write a caption', model='test') == 'ok'
    assert seen['timeout'] == (30, 240)


def test_encoder_whole_read_budget_is_not_scaled_twice(app, monkeypatch):
    from app.services import clip_text_encoder as encoder
    cfg.save_config({'timeouts': {'processing_multiplier': 2}})
    waits = []
    class Reader:
        def __init__(self, target, **_kw):
            self.target = target
        def start(self):
            self.target()
        def join(self, timeout):
            waits.append(timeout)
        def is_alive(self):
            return False
    monkeypatch.setattr(encoder.threading, 'Thread', Reader)
    monkeypatch.setattr(encoder.time, 'monotonic', lambda: 0)
    proc = SimpleNamespace(stdout=io.StringIO('loading\n{"ready": true}\n'))
    assert encoder._read_json_with_timeout(proc, 300) == {'ready': True}
    assert waits == [600, 600]


@pytest.mark.parametrize('masked', [False, True])
@pytest.mark.parametrize(('minutes', 'factor', 'succeeds'), [
    (5, 1, False), (10, 1, True), (5, 2, True), (0, 1, True), (20, 2, True),
])
def test_eight_minute_klein_repair_respects_config_on_both_lanes(
        app, tmp_path, monkeypatch, masked, minutes, factor, succeeds):
    from app.services import watermark_klein as wk, lanpaint_helper
    cfg.save_config({'comfyui': {'repair_timeout_minutes': minutes},
                     'timeouts': {'processing_multiplier': factor}})
    monkeypatch.setattr(wk, '_comfy_input_dir', lambda: str(tmp_path))
    monkeypatch.setattr(wk, '_comfy_output_dir', lambda: None)
    monkeypatch.setattr(wk.keh, 'unet_for_job', lambda *a: 'klein.safetensors')
    monkeypatch.setattr(wk.keh, '_unet_weight_dtype', lambda *a: 'fp8_e4m3fn')
    monkeypatch.setattr(wk.keh, 'resolve_klein_vae', lambda: 'vae.safetensors')
    monkeypatch.setattr(wk.keh, 'resolve_klein_text_encoder', lambda: 'te.safetensors')
    monkeypatch.setattr(wk.keh, 'klein_missing_assets', lambda: [])
    monkeypatch.setattr(lanpaint_helper, 'lanpaint_missing_nodes', lambda: [])
    data = io.BytesIO()
    Image.new('RGB', (64, 64)).save(data, 'PNG')
    monkeypatch.setattr(wk, '_read_comfy_output', lambda name: data.getvalue())
    clock = [0]
    monkeypatch.setattr(wk.time, 'monotonic', lambda: clock[0])
    seen = {}
    original_add = wk.queue_manager.add_job
    def enqueue(**kwargs):
        seen.update(kwargs)
        return original_add(**kwargs)
    monkeypatch.setattr(wk.queue_manager, 'add_job', enqueue)
    def sleep(_seconds):
        clock[0] += 60
        if clock[0] >= 480:
            row = ImageGenerationQueue.query.filter_by(job_id=seen['job_id']).one()
            row.update_status('completed', result_filename='out.png')
            db.session.commit()
    monkeypatch.setattr(wk.time, 'sleep', sleep)
    with app.app_context():
        frame = Image.new('RGB', (64, 64))
        out, error = (wk._run_klein_mask_job('local', frame, Image.new('L', frame.size, 255), seed=1)
                      if masked else wk._run_klein_job('local', frame, seed=1))
    assert (out is not None) is succeeds
    assert (error is None) is succeeds
    effective = minutes * 60 * factor
    assert seen['metadata']['processing_timeout_seconds'] == effective
    worker_budget = generation_limits.generation_timeout_seconds(seen['metadata'])
    assert worker_budget >= effective if effective else math.isinf(worker_budget)
    assert clock[0] == (480 if succeeds else 300)


@pytest.mark.parametrize('status', ['stalled', 'cancel_requested', 'cancelled'])
def test_unlimited_repair_and_improve_waits_return_when_worker_is_stopped(app, status):
    from app.services import watermark_klein, image_bank_service
    with app.app_context():
        jid = job_queue.queue_manager.add_job(workflow_data={'1': {}})
        row = ImageGenerationQueue.query.filter_by(job_id=jid).one()
        row.update_status(status)
        db.session.commit()
        assert watermark_klein._wait_for_job(jid, float('inf'))[0] == status
        assert image_bank_service._await_queue_job(jid, float('inf'))[0] == status
