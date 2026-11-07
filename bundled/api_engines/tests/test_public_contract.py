"""The image-engine package contributes exactly its documented public surfaces."""
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def test_registration_keeps_the_three_historical_engines_and_oauth_routes(app):
    from lds_api_engines import register
    specs, probes = [], {}
    ctx = SimpleNamespace(register_engine=lambda **spec: specs.append(spec),
                          register_probe=lambda key, fn: probes.update({key: fn}),
                          register_blueprint=app.register_blueprint)
    register(ctx)
    assert [spec['id'] for spec in specs] == ['nanobanana', 'chatgpt', 'openrouter']
    assert [spec['file_tag'] for spec in specs] == ['NBFace', 'GPTFace', 'ORFace']
    assert all(spec['kind'] == 'api' and spec['remote'] for spec in specs)
    assert set(probes) == {'chatgpt_subscription'}
    actual = {(rule.rule, tuple(sorted(rule.methods - {'OPTIONS', 'HEAD'})))
              for rule in app.url_map.iter_rules() if rule.endpoint != 'static'}
    prefix = '/api/settings/chatgpt-oauth/'
    assert actual == {(prefix + 'start', ('POST',)), (prefix + 'poll', ('GET',)),
                      (prefix + 'models', ('GET',)),
                      (prefix + 'import-codex', ('POST',)), (prefix + 'logout', ('POST',))}


def test_probes_check_only_local_credentials_and_never_contact_a_provider(monkeypatch):
    from lds_api_engines import probes
    assert probes.probe_gemini() == {'ok': False, 'detail': 'key missing'}
    assert probes.probe_openrouter() == {'ok': False, 'detail': 'key missing'}
    assert probes.probe_openai() == {'ok': False, 'detail': 'key missing'}
    monkeypatch.setenv('GEMINI_API_KEY', 'unit-test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'unit-test-key')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'unit-test-key')
    assert probes.probe_gemini()['ok'] is True
    assert probes.probe_openrouter()['ok'] is True
    assert probes.probe_openai()['ok'] is True


def test_subscription_mode_is_pinned_once_for_the_run(monkeypatch, sdk_adapter):
    from lds_api_engines import _chatgpt_kwargs, chatgpt_image
    monkeypatch.setattr(chatgpt_image, '_use_subscription', lambda: True)
    assert _chatgpt_kwargs() == {'force_lane': 'subscription'}
    monkeypatch.setattr(chatgpt_image, '_use_subscription', lambda: False)
    assert _chatgpt_kwargs() == {'force_lane': 'api'}
    assert chatgpt_image.SubscriptionQuotaExceeded is sdk_adapter.engine_errors.SubscriptionQuotaExceeded
    assert chatgpt_image.SubscriptionUnavailable is sdk_adapter.engine_errors.SubscriptionUnavailable


def test_package_metadata_matches_its_image_settings_and_files():
    import lds_api_engines
    manifest = json.loads((ROOT / 'plugin.json').read_text(encoding='utf-8'))
    package = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))
    assert manifest['version'] == package['version'] == lds_api_engines.__version__
    assert manifest['requires'] == []
    assert manifest['owns']['config_keys_in_shared_sections'] == {'engines': [
        'chatgpt_auth', 'chatgpt_subscription_model', 'openrouter_model',
        'nanobanana_model', 'chatgpt_image_model']}
    assert {path.name for path in (ROOT / 'lds_api_engines').glob('*.py')} == {
        '__init__.py', 'chatgpt_image.py', 'chatgpt_oauth.py', 'chatgpt_models.py', 'nanobanana.py',
        'openrouter.py', 'probes.py', 'routes.py'}
