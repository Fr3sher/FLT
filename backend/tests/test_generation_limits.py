"""Long local jobs stay owned and cancellable without touching a real worker."""
import pytest

from app import config as cfg, generation_limits, job_queue
from app.extensions import db
from app.models import ImageGenerationQueue
from app.utils import comfyui


@pytest.mark.parametrize(('raw', 'expected'), [
    (None, 900), ('bad', 900), (float('nan'), 900), (float('inf'), 900),
    (True, 900), (30, 1800), (0, float('inf')), (2000, 86400),
])
def test_timeout_config_is_bounded_and_invalid_values_keep_the_default(monkeypatch, raw, expected):
    monkeypatch.setattr(cfg, 'get', lambda key: raw)
    assert generation_limits.generation_timeout_seconds() == expected


@pytest.mark.parametrize(('raw', 'expected'), [(None, 1000), ('bad', 1000), (0, 1), (50000, 10000), (300, 300)])
def test_local_queue_config_stays_bounded(monkeypatch, raw, expected):
    monkeypatch.setattr(cfg, 'get', lambda key: raw)
    assert generation_limits.local_queue_limit() == expected


@pytest.mark.parametrize(('minutes', 'elapsed'), [(30, 1200), (0, 100000)])
def test_slow_generation_can_finish_past_the_old_fifteen_minute_deadline(app, monkeypatch, minutes, elapsed):
    cfg.save_config({'comfyui': {'generation_timeout_minutes': minutes}})
    clock = [0]
    monkeypatch.setattr(job_queue.time, 'monotonic', lambda: clock[0])

    class Wait:
        def is_set(self):
            return False

        def wait(self, _seconds):
            clock[0] = elapsed

    monkeypatch.setattr(job_queue, '_cancel_event', lambda _prompt: Wait())
    probes = iter([
        comfyui.ComfyHistoryProbe(comfyui.ComfyHistoryHealth.NOT_READY),
        comfyui.ComfyHistoryProbe(comfyui.ComfyHistoryHealth.READY, history={
            'slow': {'outputs': {'out': {'images': [{'filename': 'finished.png'}]}}}}),
    ])
    monkeypatch.setattr(comfyui, 'get_comfyui_history_probe', lambda _prompt: next(probes))
    with app.app_context():
        assert job_queue._poll_outputs('slow') == ('finished.png', False)


@pytest.mark.parametrize('unhealthy', [False, True])
@pytest.mark.parametrize('network_factor', [1, 3])
def test_no_time_limit_keeps_cancellation_and_worker_health_protection(app, monkeypatch, unhealthy, network_factor):
    cfg.save_config({'comfyui': {'generation_timeout_minutes': 0},
                     'timeouts': {'network_multiplier': network_factor}})
    clock = [0]
    cancelled = [False]
    monkeypatch.setattr(job_queue.time, 'monotonic', lambda: clock[0])

    class Wait:
        def is_set(self):
            return cancelled[0]

        def wait(self, _seconds):
            clock[0] += job_queue.COMFYUI_UNHEALTHY_GRACE_SECONDS + 1
            cancelled[0] = not unhealthy

    monkeypatch.setattr(job_queue, '_cancel_event', lambda _prompt: Wait())
    health = comfyui.ComfyHistoryHealth.UNHEALTHY if unhealthy else comfyui.ComfyHistoryHealth.NOT_READY
    monkeypatch.setattr(comfyui, 'get_comfyui_history_probe', lambda _prompt: comfyui.ComfyHistoryProbe(health))
    with app.app_context():
        jid = job_queue.queue_manager.add_job(workflow_data={'1': {}})
        row = ImageGenerationQueue.query.filter_by(job_id=jid).one()
        row.update_status('sent_to_comfy', comfyui_prompt_id='slow')
        db.session.commit()
        assert job_queue._poll_outputs('slow') == (None, job_queue.POLL_STALLED if unhealthy else True)
        if unhealthy:
            assert clock[0] == (job_queue.COMFYUI_UNHEALTHY_GRACE_SECONDS + 1) * network_factor
            assert job_queue.queue_manager.get_comfyui_stalled_barrier()['prompt_id'] == 'slow'
