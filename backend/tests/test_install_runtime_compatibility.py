"""V2 distribution files and lifecycle ownership across supported launchers."""
from pathlib import Path

import pytest

from app.plugins.routes import restart_payload
from app.services import updater


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('name', ['Dockerfile', 'Dockerfile.gpu'])
def test_images_include_the_public_store_trust_files(name):
    # Copy only the two public bootstrap files, never an operator's store tree.
    source = (ROOT / name).read_text(encoding='utf-8')
    assert 'COPY store/bootstrap.json store/public-root.json store/' in source
    for name in ('bootstrap.json', 'public-root.json'):
        assert (ROOT / 'store' / name).is_file()


@pytest.mark.parametrize(('runtime', 'supervisor', 'mode'), [
    ('docker', '', 'container'),
    ('docker-external-comfy', '', 'container'),
    ('docker-gpu', '', 'container'),
    ('docker-gpu', 'supervisor', 'self'),
    ('pinokio', '', 'pinokio'),
    ('pinokio', 'supervisor', 'pinokio'),
    ('', 'supervisor', 'self'),
    ('', '', 'manual'),
])
def test_plugin_restart_belongs_to_the_launcher(monkeypatch, runtime, supervisor, mode):
    monkeypatch.setenv('LDS_RUNTIME', runtime)
    monkeypatch.setenv('LDS_RESTART_MODE', supervisor)
    payload = restart_payload()
    assert payload['mode'] == mode
    assert payload['can_apply'] is (mode == 'self')


@pytest.mark.parametrize(('runtime', 'command'), [
    ('docker', 'docker compose up -d --build'),
    ('docker-gpu', 'docker compose -f docker-compose.gpu.yml up -d --build'),
    ('docker-external-comfy', 'docker compose -f docker-compose.yml '
     '-f docker-compose.external-comfy.yml '
     '-f .docker-compose.external-comfy.override.yml up -d --build'),
])
def test_all_docker_lanes_refuse_in_place_code_updates(client, monkeypatch, runtime, command):
    monkeypatch.setenv('LDS_RUNTIME', runtime)

    def forbidden(*args, **kwargs):
        raise AssertionError('A Docker update must not download or replace live code.')

    monkeypatch.setattr(updater, 'is_git_checkout', forbidden)
    monkeypatch.setattr(updater, 'apply_update', forbidden)
    monkeypatch.setattr(updater, 'start_zip_update', forbidden)
    response = client.post('/api/update/apply')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['install_mode'] == 'docker'
    assert payload['ok'] is False and payload['can_apply'] is False
    assert payload['instructions'][-1] == command


@pytest.mark.parametrize('busy', [False, True])
def test_gpu_plugin_apply_checks_work_before_supervised_restart(client, app, monkeypatch, busy):
    from app import setup_installer
    from app.plugins import restart, routes
    from app.plugins import environment

    # These process-wide registries can contain fake jobs left by other test
    # modules. This case owns an idle installation and varies only ComfyUI work.
    monkeypatch.setattr(setup_installer, '_runs', {})
    monkeypatch.setattr(setup_installer, '_pip_current', None)
    monkeypatch.setattr(setup_installer, '_pip_queue', [])
    monkeypatch.setattr(environment, '_RUNNING', {})
    monkeypatch.setenv('LDS_RUNTIME', 'docker-gpu')
    monkeypatch.setenv('LDS_RESTART_MODE', 'supervisor')
    monkeypatch.setattr(routes, 'lifecycle_payload', lambda registry: {
        'pending_restart': True, 'boot_id': 'test-boot'})
    checked = []

    def comfy_idle():
        checked.append('comfy')
        if busy:
            raise restart.RestartBlocked('ComfyUI is still running or queuing work.')

    def schedule(**kwargs):
        checked.append('restart')
        assert kwargs == {'block_during_update': True}

    monkeypatch.setattr(restart, '_require_comfy_idle', comfy_idle)
    monkeypatch.setattr(updater, 'schedule_restart', schedule)
    gate = app.extensions['lds_plugin_restart_gate']
    try:
        response = client.post('/api/plugins/apply')
        assert response.status_code == (409 if busy else 200), response.get_json()
        assert checked == (['comfy'] if busy else ['comfy', 'restart'])
        if busy:
            assert response.get_json()['code'] == 'restart_blocked'
    finally:
        gate.release()
        gate.finished.set()
