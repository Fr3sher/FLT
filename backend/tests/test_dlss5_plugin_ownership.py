"""The finishing product and Video can be admitted independently or together."""
import pytest


@pytest.mark.parametrize('enabled', [('video',), ('dlss5',), ('video', 'dlss5')])
def test_finishing_ownership_is_disjoint(plugin_app_factory, enabled):
    app = plugin_app_factory(enabled=enabled)
    registry = app.extensions['lds_plugins']
    assert not registry.records['video'].manifest.requires
    assert not registry.records['dlss5'].manifest.requires
    assert 'dlss5nr_bridge' not in registry.records['video'].manifest.owns['install_actions']
    if 'dlss5' in enabled:
        assert registry.install_actions['dlss5nr_bridge']['plugin'] == 'dlss5'
        assert registry.probes['dlss5nr'][0] == 'dlss5'
    else:
        assert 'dlss5nr_bridge' not in registry.install_actions
        assert 'dlss5nr' not in registry.probes
    finishing_routes = [rule for rule in app.url_map.iter_rules()
                        if rule.rule == '/api/video-studio/clip/<int:clip_id>/neural-render']
    assert len(finishing_routes) == int('dlss5' in enabled)
    if finishing_routes:
        assert finishing_routes[0].endpoint.startswith('dlss5_video.')
