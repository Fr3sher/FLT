"""Every Quality card installs into a usable managed runtime, not the host ABI."""
import subprocess

import pytest

from app import capabilities, config, setup_installer as si


def test_ocr_on_new_host_uses_managed_quality_python(app, monkeypatch):
    calls = []
    with app.app_context():
        managed = si._venv_python(si._quality_env_dir())
        monkeypatch.setattr(si, '_ensure_managed_ml_env', lambda *a: managed)
        monkeypatch.setattr(si, '_run_pip', lambda a, cmd: calls.append(cmd) or 0)
        monkeypatch.setattr(si, '_verify_capability_import', lambda *a, **kw: True)
        monkeypatch.setattr(si, '_onnxruntime_provided', lambda p: False)
        assert si._run_ml_capability('video_text') == 0
        assert calls[0][0] == managed
        assert '--only-binary=:all:' in calls[0]
        assert config.get('video_text.python') == managed


@pytest.mark.parametrize('key,action', [
    ('face_scoring', 'face_scoring'), ('masks', 'masks'), ('video_text', 'video_text'),
    ('watermark', 'watermark_inpaint'), ('bank_scoring', 'bank_scoring'),
    ('bank_semantic', 'bank_siglip2'), ('watermark_detect', 'watermark_detect'),
])
def test_broken_borrowed_selection_cannot_claim_a_successful_repair(app, monkeypatch, key, action):
    with app.app_context():
        config.save_config({key: {'python': '/borrowed/broken-python'}})
        calls = []
        monkeypatch.setattr(si, '_verify_capability_import',
                            lambda a, p, **kw: calls.append((a, p)) or False)
        assert si._select_managed_python(action, key, '/managed/python') is False
        assert config.get(f'{key}.python') == '/borrowed/broken-python'
        assert calls == [(action, '/borrowed/broken-python')]


def test_healthy_borrowed_selection_is_checked_and_preserved(app, monkeypatch):
    with app.app_context():
        config.save_config({'masks': {'python': '/borrowed/working-python'}})
        monkeypatch.setattr(si, '_verify_capability_import', lambda *a, **kw: True)
        assert si._select_managed_python('masks', 'masks', '/managed/python')
        assert config.get('masks.python') == '/borrowed/working-python'


def test_watermark_detector_waits_for_download_before_selecting_runtime(app, monkeypatch):
    with app.app_context():
        managed = si._bank_scoring_env_python()
        monkeypatch.setattr(si, '_ensure_bank_scoring_env', lambda *a, **kw: managed)
        monkeypatch.setattr(si, '_install_cpu_torch_pair', lambda *a, **kw: 0)
        monkeypatch.setattr(si, '_run_pip', lambda *a, **kw: 0)
        monkeypatch.setattr(si, '_verify_watermark_detect_import', lambda *a: True)
        monkeypatch.setattr(si, '_download_watermark_detect_models', lambda *a: 1)
        assert si._run_watermark_detect('watermark_detect') == 1
        assert not config.get('watermark_detect.python')


def test_detector_import_failure_never_becomes_success(tmp_path, monkeypatch):
    python = tmp_path / 'python'
    python.touch()
    monkeypatch.setattr(si.subprocess, 'run', lambda *a, **kw:
                        (_ for _ in ()).throw(subprocess.TimeoutExpired('python', 1)))
    assert si._verify_watermark_detect_import('watermark_detect', str(python)) is False


def test_detector_install_preserves_borrowed_selection_and_never_pips_into_it(app, monkeypatch):
    with app.app_context():
        config.save_config({'watermark_detect': {'python': '/borrowed/working-python'}})
        managed = si._bank_scoring_env_python()
        calls = []
        monkeypatch.setattr(si, '_ensure_bank_scoring_env', lambda *a, **kw: managed)
        monkeypatch.setattr(si, '_install_cpu_torch_pair', lambda a, p, **kw: calls.append(p) or 0)
        monkeypatch.setattr(si, '_run_pip', lambda a, cmd: calls.append(cmd[0]) or 0)
        monkeypatch.setattr(si, '_verify_capability_import', lambda *a, **kw: True)
        monkeypatch.setattr(si, '_download_watermark_detect_models', lambda *a: 0)
        assert si._run_watermark_detect('watermark_detect') == 0
        assert config.get('watermark_detect.python') == '/borrowed/working-python'
        assert calls and set(calls) == {managed}


def test_ocr_probe_and_real_worker_share_the_selected_interpreter(app, monkeypatch):
    from app.services import infer_stream, text_fill, video_safe_zone
    with app.app_context():
        config.save_config({'video_text': {'python': '/managed/quality/python'}})
        seen = []
        monkeypatch.setattr(capabilities, '_cached_import',
                            lambda key, python, expr: seen.append((python, expr)) or True)
        assert capabilities.probe_video_text()['ok']
        assert seen == [('/managed/quality/python', capabilities.CAPABILITY_IMPORTS['video_text'])]
        calls = []
        monkeypatch.setattr(infer_stream, 'run_infer_script',
                            lambda python, *a, **kw: calls.append(python)
                            or ('{"ok":true,"boxes":{},"results":{}}', [], 0, False))
        assert video_safe_zone.read_text_boxes([{'key': 'sample', 'path': '/fixture.png'}]) == {}
        assert text_fill.fill_batch([{'image_path': '/fixture.png', 'regions': []}]) == {}
        assert calls == ['/managed/quality/python', '/managed/quality/python']


@pytest.mark.parametrize('action,environment', [
    ('bank_scoring', 'bank_scoring'), ('bank_siglip2', 'bank_scoring'),
    ('watermark_detect', 'bank_scoring'), ('watermark_inpaint', 'watermark'),
])
def test_every_heavy_quality_card_uses_the_compatible_managed_environment(app, monkeypatch, action, environment):
    calls = []
    monkeypatch.setattr(si, '_ensure_managed_ml_env',
                        lambda a, directory: calls.append(directory.name) or '')
    monkeypatch.setattr(si, '_run_pip', lambda *a, **kw: pytest.fail('no host pip fallback'))
    with app.app_context():
        assert si._WORKERS[action](action) == 1
    assert calls == [environment]


def test_detector_manual_recipe_never_targets_a_borrowed_interpreter(app):
    with app.app_context():
        config.save_config({'watermark_detect': {'python': '/borrowed/python'}})
        command = si.manual_command('watermark_detect')
        assert '/borrowed/python' not in command
        assert si._bank_scoring_env_python() in command
