"""Opening the core must not require a generator, ML packages or a plugin."""
import pytest

from app import capabilities, setup_state
from tests.test_public_plugin_foundation import host as foundation_host  # noqa: F401


@pytest.fixture
def client(foundation_host):
    """The actual state routes with zero plugins and no production workers."""
    app, _csrf, _root = foundation_host
    from app.routes.setup_state import bp
    app.register_blueprint(bp)
    return app.test_client()


@pytest.mark.parametrize('body', [['masks'], 'masks', 1, True])
def test_state_dismiss_rejects_non_object_body_without_probing(client, monkeypatch, body):
    monkeypatch.setattr(capabilities, 'probe', lambda **_kw: pytest.fail('Invalid request must not probe'))
    assert client.post('/api/setup-state/dismiss', json=body).status_code == 400


def test_core_completion_is_durable_without_optional_probes(client, monkeypatch):
    def unexpected_probe(*args, **kwargs):
        raise AssertionError('Opening the workspace must not probe optional tools')
    monkeypatch.setattr(capabilities, 'probe', unexpected_probe)
    response = client.post('/api/setup-state/complete', json={})
    assert response.status_code == 200
    assert response.get_json()['completed'] is True
    first = setup_state.read()
    assert first['completed'] is True
    assert first['verified'] is False
    assert first['checks'] == {}
    # An unrelated capability refresh or dismissal must not undo completion.
    setup_state.observe({'configured': False, 'engines': {}, 'masks': False})
    setup_state.dismiss(['masks'])
    assert setup_state.read()['completed_at'] == first['completed_at']
    assert setup_state.read()['completed'] is True
    assert client.post('/api/setup-state/complete').get_json()['completed_at'] == first['completed_at']


def test_completion_does_not_erase_existing_regression_history(client):
    setup_state.observe({'configured': False, 'masks': True})
    assert client.post('/api/setup-state/complete').status_code == 200
    assert setup_state.compare({'masks': False}) == [{'key': 'masks', 'label': 'Person masks'}]


def test_failed_workspace_write_is_not_reported_as_installed(client, monkeypatch):
    from pathlib import Path
    def denied(*args, **kwargs):
        raise PermissionError('test workspace denied')
    monkeypatch.setattr(Path, 'write_text', denied)
    response = client.post('/api/setup-state/complete')
    assert response.status_code == 503
    assert 'data folder is writable' in response.get_json()['error']
    assert not setup_state.read().get('completed')
    with pytest.raises(PermissionError):
        setup_state.complete_core()


def test_state_api_keeps_core_completion_separate_from_engine_verification(client, monkeypatch):
    monkeypatch.setattr(capabilities, 'probe', lambda **kwargs: {'configured': False, 'engines': {}})
    client.post('/api/setup-state/complete')
    for response in [client.get('/api/setup-state'), client.post('/api/setup-state/recheck')]:
        state = response.get_json()
        assert state['completed'] is True and state['completed_at']
        assert state['verified'] is False
        assert state['regressions'] == []


@pytest.mark.parametrize('mode', ['', 'host', 'docker', 'none'])
def test_core_only_docker_choice_releases_launcher_without_changing_existing_choice(client, monkeypatch, mode):
    from app import config
    monkeypatch.setattr(capabilities, 'setup_is_docker_runtime', lambda: True)
    config.save_config({'ollama': {'deployment_mode': mode}})
    assert client.post('/api/setup-state/complete').status_code == 200
    assert config.get('ollama.deployment_mode') == (mode or 'none')


@pytest.mark.parametrize('base,host,skipped', [(None, '127.0.0.1', True),
                                            ('', 'localhost', True),
                                            ('', '[::1]', True),
                                            ('configured-comfy', '127.0.0.1', False),
                                            ('', 'comfy.example', False)])
def test_dataset_choice_defers_only_an_uninstalled_local_comfy(client, monkeypatch, base, host, skipped):
    from app import config
    def unexpected_probe(*args, **kwargs):
        raise AssertionError('Dataset completion must not contact an optional service')
    monkeypatch.setattr(capabilities, 'probe', unexpected_probe)
    comfy = {'base_dir': base, 'api_url': f'http://{host}:58188', 'setup_skipped': False,
             'models_dir': 'configured-models'}
    config.save_config({'comfyui': comfy})
    assert client.post('/api/setup-state/complete', json={'goal': 'dataset'}).status_code == 200
    assert config.get('comfyui.setup_skipped') is skipped
    for key, value in comfy.items():
        if key != 'setup_skipped':
            assert config.get('comfyui.' + key) == value
    assert setup_state.read()['completed'] is True


@pytest.mark.parametrize('goal', [None, 'images', 'captions', 'plugins', 'unknown'])
def test_other_completion_intents_do_not_defer_comfy(client, goal):
    from app import config
    config.save_config({'comfyui': {'base_dir': '', 'setup_skipped': False}})
    body = {} if goal is None else {'goal': goal}
    assert client.post('/api/setup-state/complete', json=body).status_code == 200
    assert config.get('comfyui.setup_skipped') is False
