"""Public HTTP ownership used by the inline Improve editor; no inference."""
from test_public_backend_mount import factory  # noqa: F401
from app import config as cfg


def test_improve_instruction_requires_owner_while_model_library_stays_core(factory, monkeypatch):
    app = factory({'image_upscale'})
    monkeypatch.setattr('app.routes.settings._lan_ip', lambda: None)
    monkeypatch.setattr('app.routes.settings._tailscale_ip', lambda: None)
    cfg.save_config({'identity_prompts': {'klein_improve': 'before'},
                     'klein': {'unet': 'base.safetensors', 'generation_lora_presets': []}})
    client = app.test_client()
    patch = {'config': {'identity_prompts': {'klein_improve': 'after'}}}
    # This was the old inline editor request: rejected without changing data.
    assert client.put('/api/settings', json=patch).status_code == 400
    assert cfg.get('identity_prompts.klein_improve') == 'before'
    response = client.put('/api/settings?plugin=image_upscale', json=patch)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()['config']['identity_prompts']['klein_improve'] == 'after'
    shared = {'config': {'klein': {'unet': 'other.safetensors'}}}
    assert client.put('/api/settings?plugin=image_upscale', json=shared).status_code == 400
    assert cfg.get('klein.unet') == 'base.safetensors'
    assert client.put('/api/settings', json=shared).status_code == 200
    assert cfg.get('klein.unet') == 'other.safetensors'
    core = client.get('/api/settings').get_json()['config']
    owned = client.get('/api/settings?plugin=image_upscale').get_json()['config']
    assert 'klein_improve' not in core.get('identity_prompts', {})
    assert 'unet' not in owned.get('klein', {})
    assert owned['identity_prompts']['klein_improve'] == 'after'
