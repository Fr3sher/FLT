"""A public product's old setup ids are available only from its loaded owner."""
import pytest

from app import config as cfg, setup_installer as installer
from tests.test_public_sdk_integration import activate, host, no_external_runtime  # noqa: F401


PRODUCT_ACTIONS = {
    'seedvr2': ('seedvr2_model', 'seedvr2_vae'),
    'camera_angles': ('camera_model', 'camera_lora', 'camera_speed_lora', 'camera_text_encoder'),
    'video': ('video', 'shot_detect', 'dlss5nr_bridge', 'h3_base', 'h3_video_vae'),
    'scrape': ('scrape_extras',),
}


def test_empty_install_has_only_core_preparation_actions(host, monkeypatch):
    monkeypatch.setenv('LDS_PLUGIN_DISTRIBUTION', 'store')
    monkeypatch.delenv('LDS_BUNDLED_DIR')
    activate(host, set())
    for actions in PRODUCT_ACTIONS.values():
        for action in actions:
            assert not installer.known_action(action), action
            assert action not in installer.INSTALL_ACTIONS
    assert set(installer.install_groups()) == {'krea'}
    assert installer.plugin_actions_catalog() == {}
    for action in ('face_scoring', 'masks', 'video_text', 'klein_model', 'krea_vae'):
        assert installer.known_action(action), action


@pytest.mark.parametrize('owner', PRODUCT_ACTIONS)
def test_only_the_loaded_owner_can_expose_its_install_actions(host, owner):
    loaded = activate(host, {owner})
    assert loaded.records[owner].state == 'loaded', loaded.records[owner].error
    for action in PRODUCT_ACTIONS[owner]:
        assert installer.known_action(action), action
        spec = installer.plugin_action_spec(action) or installer.model_download_spec(action)
        assert spec['plugin'] == owner
    cfg.save_config({'plugins': {'enabled': {owner: False}}})
    for action in PRODUCT_ACTIONS[owner]:
        assert not installer.known_action(action), action


@pytest.mark.parametrize('owner,group', [('seedvr2', 'seedvr2'), ('camera_angles', 'camera')])
def test_group_members_come_from_the_product_with_core_shared_files_allowed(host, owner, group):
    loaded = activate(host, {owner})
    assert installer.install_groups()[group] == loaded.install_groups[group]['members']
    assert all(installer.known_action(action) for action in installer.install_groups()[group])


@pytest.mark.parametrize('action,worker', [('shot_detect', '_run_shot_detect'), ('video', '_run_ml_capability')])
def test_video_preparation_keeps_managed_host_python_and_off_guard(host, monkeypatch, action, worker):
    activate(host, {'video'})
    calls = []
    monkeypatch.setattr(installer, worker, lambda key: calls.append(key) or 0)
    monkeypatch.setattr(installer, '_run_pip', lambda *_a, **_kw: pytest.fail('No app-pip fallback'))
    assert installer._run_plugin_action(action) == 0
    assert calls == [action]
    cfg.save_config({'plugins': {'enabled': {'video': False}}})
    from app.plugins.environment import EnvironmentError
    with pytest.raises(EnvironmentError):
        installer._run_plugin_action(action)
    assert calls == [action]
