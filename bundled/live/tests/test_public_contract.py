"""Public Live plugin contracts against SDK fakes, not host qualification."""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import lds_live
from lds_live import live_studio as live, setup


PREFIX = '/api/video-studio/live'


class RecordingContext:
    def __init__(self):
        self.dir = Path(lds_live.__file__).parent.parent
        self.calls = {}

    def __getattr__(self, name):
        if not name.startswith('register_'):
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.calls.setdefault(name, []).append((args, kwargs))
        return record


def test_registration_matches_exact_public_manifest_ownership(app):
    ctx = RecordingContext()
    lds_live.register(ctx)
    manifest = json.loads((ctx.dir / 'plugin.json').read_text(encoding='utf-8'))
    expected_actions = {'live_encoder', 'live_h3_base', 'live_h3_text_encoder',
                        'live_h3_video_vae', 'live_h3_audio_vae', 'live_h3_turbo_lora'}
    actions = {args[0] for method in ('register_install_action', 'register_model_download')
               for args, kwargs in ctx.calls[method]}
    assert actions == expected_actions == set(manifest['owns']['install_actions'])
    assert manifest['requires'] == []
    assert manifest['owns']['config_sections'] == []
    assert set(ctx.calls) == {'register_blueprint', 'register_request_limit', 'register_job_handler',
                              'register_hook', 'register_probe', 'register_install_action',
                              'register_model_download'}
    args, kwargs = ctx.calls['register_blueprint'][0]
    assert len(ctx.calls['register_blueprint']) == 1
    assert args[0].name == 'video_live' and kwargs == {'url_prefix': PREFIX}
    assert ctx.calls['register_request_limit'] == [
        (('video_live.live_lora_import', 1024 * 1024 * 1024), {})]
    assert {args[0] for args, kw in ctx.calls['register_hook']} == {
        'comfyui.restart_blockers', 'system.free_memory_blockers', 'plugin.disable_blockers'}
    assert [args[0] for args, kw in ctx.calls['register_probe']] == manifest['owns']['probes'] == ['live']
    assert [args[0] for args, kw in ctx.calls['register_job_handler']] == manifest['owns']['job_kinds'] == ['is_live']
    assert ctx.calls['register_job_handler'][0][1]['presentation']['cancel_scope'] == 'owner'
    routes = {(rule.rule.removeprefix(PREFIX), tuple(sorted(rule.methods - {'OPTIONS', 'HEAD'})))
              for rule in app.url_map.iter_rules() if rule.endpoint.startswith('video_live.')}
    assert routes == {('/options', ('GET',)), ('/start', ('POST',)), ('/stop', ('POST',)),
                      ('/status', ('GET',)), ('/<sid>/stream.m3u8', ('GET',)),
                      ('/<sid>/seg/<name>', ('GET',)), ('/render-options', ('GET',)),
                      ('/loras', ('GET',)), ('/deploy', ('POST',)), ('/lora/import', ('POST',))}


def test_completion_keeps_origin_session_metadata(monkeypatch):
    calls = []
    monkeypatch.setattr(live, 'link_completed_live_clip', lambda *args, **kwargs: calls.append((args, kwargs)))
    lds_live._live_done('job-a', 'clip.mp4', failed=True, reason='render refused',
                        metadata={'live_session': 'origin', 'live_seq': 2})
    lds_live._live_done('job-b', None)
    assert calls == [(('job-a', 'clip.mp4'), {'failed': True, 'reason': 'render refused', 'session_id': 'origin'}),
                     (('job-b', None), {'failed': False, 'reason': None, 'session_id': None})]


@pytest.mark.parametrize('state,blocked', [('starting', True), ('running', True), ('stopping', True),
                                          ('stopped', False), ('idle', False), (None, False)])
def test_lifecycle_blockers_only_cover_live_active_sessions(monkeypatch, state, blocked):
    monkeypatch.setattr(live, 'current', lambda: SimpleNamespace(state=state, params={'gpu': 'local'}) if state else None)
    reasons = ['Existing blocker']
    assert len(lds_live._restart_blockers(reasons)) == 1 + blocked
    assert len(lds_live._disable_blockers(reasons, 'live')) == 1 + blocked
    assert len(lds_live._free_memory_blockers(reasons)) == 1 + blocked
    assert lds_live._disable_blockers(reasons, 'unrelated') == reasons
    assert reasons == ['Existing blocker'], 'Hooks must not mutate the host list.'


@pytest.mark.parametrize('state,start,end,expected', [
    ('completed', 0, 2.34, 2.3), ('failed', 0, 2.36, 2.4), ('pending', 0, 2, None),
    ('completed', None, 2, None), ('completed', 0, None, None), ('completed', 2, 1, None),
])
def test_render_duration_uses_mocked_queue_snapshot(monkeypatch, sdk_fakes, state, start, end, expected):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    row = SimpleNamespace(status=state, started_at=None if start is None else origin + timedelta(seconds=start),
                          completed_at=None if end is None else origin + timedelta(seconds=end))
    seen = []
    monkeypatch.setattr(sdk_fakes.runtime, 'job', lambda job_id: seen.append(job_id) or row)
    assert live._render_seconds('job-a') == expected
    assert seen == ['job-a']


def test_queue_snapshot_missing_and_error_are_unknown(app, monkeypatch, sdk_fakes):
    session = live.LiveSession(app, 'local', {'scenes': 'scripted scene', 'frames': 124})
    assert live._render_seconds('unknown') is None
    assert session._job_status('unknown') is None

    def failed_read(job_id):
        raise RuntimeError('snapshot unavailable')
    monkeypatch.setattr(sdk_fakes.runtime, 'job', failed_read)
    assert live._render_seconds('failed-read') is None
    assert session._job_status('failed-read') is None


def test_setup_reports_missing_h3_and_encoder_separately(monkeypatch, sdk_fakes):
    h3 = sdk_fakes.h3
    source = [{'action': 'h3_base', 'filename': 'base.safetensors'},
              {'action': 'private_only', 'filename': 'not-shipped.safetensors'}]
    monkeypatch.setattr(h3, 'missing_weights', lambda: source)
    assert setup.facts()['missing'] == [{'action': 'live_h3_base', 'filename': 'base.safetensors'}]
    assert source[0]['action'] == 'h3_base'
    facts = setup.facts()
    assert facts['ready'] is False and facts['encoder'] is False
    monkeypatch.setattr(h3, 'missing_weights', lambda: [])
    monkeypatch.setattr(setup, 'ffmpeg_ready', lambda force=False: {'ok': True})
    assert setup.facts()['encoder'] is True and setup.facts()['ready'] is True
    monkeypatch.setattr(sdk_fakes.local_render, 'comfyui_reachable', lambda: False)
    assert setup.facts()['ready'] is False


def test_encoder_registration_defers_install_and_checks_afterwards(monkeypatch):
    checked = []
    monkeypatch.setattr(setup, 'ffmpeg_ready', lambda force=False: checked.append(force) or {'ok': True})
    ctx = RecordingContext()
    setup.register(ctx)
    assert checked == []
    args, spec = ctx.calls['register_install_action'][0]
    assert args == ('live_encoder',) and spec['python'] == 'app'
    assert spec['requirements'] == ctx.dir / 'requirements-host.txt'
    assert spec['verify']() is True and checked == [True]


@pytest.mark.parametrize('method,path', [('GET', '/options'), ('GET', '/render-options'), ('GET', '/loras'),
                                        ('GET', '/status'), ('POST', '/start'), ('POST', '/stop'),
                                        ('POST', '/deploy'), ('POST', '/lora/import'),
                                        ('GET', '/abcd1234/stream.m3u8'), ('GET', '/abcd1234/seg/seg_000001.ts')])
def test_disabled_live_admission_precedes_each_endpoint(client, monkeypatch, sdk_fakes, method, path):
    monkeypatch.setattr(sdk_fakes.lifecycle, 'is_available', lambda plugin: False)
    response = client.open(PREFIX + path, method=method, json={})
    assert response.status_code == 409 and response.get_json()['code'] == 'plugin_unavailable'


def test_render_options_and_loras_are_owned_by_live(client, monkeypatch, sdk_fakes):
    h3 = sdk_fakes.h3
    monkeypatch.setattr(h3, 'deployed_loras', lambda: [{'filename': 'deployed.safetensors'}])
    monkeypatch.setattr(h3, 'trained_loras', lambda: [{'run_id': 12, 'filename': 'trained.safetensors'}])
    assert client.get(PREFIX + '/loras').get_json() == {
        'deployed': [{'filename': 'deployed.safetensors'}],
        'trained': [{'run_id': 12, 'filename': 'trained.safetensors'}]}
    data = client.get(PREFIX + '/render-options').get_json()
    assert data['ready'] is True and data['missing_weights'] == []
    assert data['frame_choices'] == [124, 244, 364]
    assert data['megapixels'] == {'min': 0.1, 'max': 2.0, 'default': 0.3}
    assert data['turbo_steps'] == 4 and data['eros_available'] is False
    monkeypatch.setattr(sdk_fakes.local_render, 'comfyui_reachable', lambda: False)
    assert client.get(PREFIX + '/render-options').get_json()['ready'] is False


def test_deploy_forwards_selection_without_starting_render(client, monkeypatch, sdk_fakes):
    calls = []
    monkeypatch.setattr(sdk_fakes.h3, 'deploy_checkpoint', lambda run, name: calls.append((run, name)) or 'deployed.safetensors')
    response = client.post(PREFIX + '/deploy', json={'run_id': 12, 'filename': 'checkpoint.safetensors'})
    assert response.get_json() == {'ok': True, 'filename': 'deployed.safetensors'}
    assert calls == [(12, 'checkpoint.safetensors')] and sdk_fakes.queued == []


def test_import_forwards_either_path_or_upload_to_sdk(client, monkeypatch, sdk_fakes):
    calls = []

    def import_lora(**values):
        upload = values.pop('upload')
        calls.append({**values, 'bytes': upload.read() if upload is not None else None})
        return {'filename': 'imported.safetensors'}
    monkeypatch.setattr(sdk_fakes.h3, 'import_external_lora', import_lora)
    assert client.post(PREFIX + '/lora/import', json={'path': 'models/source.safetensors'}).get_json() == {
        'ok': True, 'filename': 'imported.safetensors'}
    assert client.post(PREFIX + '/lora/import', data={'file': (io.BytesIO(b'mocked weights'), 'upload.safetensors')}).status_code == 200
    assert calls == [{'src_path': 'models/source.safetensors', 'filename': None, 'bytes': None},
                     {'src_path': None, 'filename': 'upload.safetensors', 'bytes': b'mocked weights'}]
    assert sdk_fakes.queued == []


@pytest.mark.parametrize('endpoint,method', [('/deploy', 'deploy_checkpoint'), ('/lora/import', 'import_external_lora')])
@pytest.mark.parametrize('error_type', [ValueError, TypeError, OSError])
def test_lora_sdk_errors_become_client_errors(client, monkeypatch, sdk_fakes, endpoint, method, error_type):
    def refused(*args, **kwargs):
        raise error_type('Invalid fixture input')
    monkeypatch.setattr(sdk_fakes.h3, method, refused)
    response = client.post(PREFIX + endpoint, json={})
    assert response.status_code == 400
    assert response.get_json() == {'ok': False, 'error': 'Invalid fixture input'}


@pytest.mark.parametrize('payload', [[], ['not-settings'], False, 0, 'not-settings', None])
def test_start_rejects_non_object_json_without_starting(client, monkeypatch, payload):
    def unexpected_start(*args, **kwargs):
        pytest.fail('Malformed settings reached the render session.')
    monkeypatch.setattr(live, 'start', unexpected_start)
    response = client.post(PREFIX + '/start', data=json.dumps(payload), content_type='application/json')
    assert response.status_code == 400
