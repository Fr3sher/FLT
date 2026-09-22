"""The surfaces the provider seam added, and that nothing was testing.

The verification pass that produced this file listed them plainly: the four
`probe_lmstudio*` functions, `GET /api/local-llm/models`, `ensure_ready`, and the
half of the router that is not `describe_image` had no test at all. Two of those
turned out to hold real defects, which is the argument for the file.

What is pinned here is the CONTRACT each surface owes rather than its wording:
a route that always answers 200, probes that never raise, and a readiness step
that acts for Ollama (which it can start) and only reports for LM Studio (which
it cannot).
"""
import pytest

from app import capabilities, config
from app.services import vision_llm, vision_lmstudio


@pytest.fixture
def as_lmstudio(app):
    with app.app_context():
        config.save_config({'local_llm': {'provider': 'lmstudio'},
                            'lmstudio': {'url': 'http://127.0.0.1:1299'}})
    yield


def _listing(**over):
    base = {'ok': True, 'reachable': True, 'surface': 'v1', 'models': [],
            'answered': True, 'refused': False, 'last_status': None, 'last_body': ''}
    base.update(over)
    return base


# --- the route promises 200, whatever the server is doing --------------------

@pytest.mark.parametrize('provider', ['ollama', 'lmstudio'])
def test_the_model_route_always_answers_200(app, client, provider):
    """Its docstring says "never a server fault", and every picker degrades to an
    empty list rather than an error nobody can act on from a dropdown. Both
    providers, because the failure paths are entirely different code."""
    with app.app_context():
        config.save_config({'local_llm': {'provider': provider}})
    r = client.get('/api/local-llm/models')
    assert r.status_code == 200
    body = r.get_json()
    assert body['provider'] == provider
    assert isinstance(body['models'], list)


def test_the_route_stays_200_when_the_lmstudio_server_is_gone(app, client, monkeypatch,
                                                              as_lmstudio):
    def _boom(*a, **kw):
        raise vision_lmstudio.requests.exceptions.ConnectionError('nothing there')

    monkeypatch.setattr(vision_lmstudio.requests, 'get', _boom)
    r = client.get('/api/local-llm/models')
    assert r.status_code == 200
    assert r.get_json() == {'ok': False, 'reachable': False, 'provider': 'lmstudio',
                            'models': []}


@pytest.mark.parametrize('provider', ['ollama', 'lmstudio'])
def test_the_old_ollama_path_answers_exactly_what_the_new_one_does(app, client, provider):
    """`GET /api/ollama/models` is an ALIAS now, and its meaning changed with it.

    It used to list Ollama's models under any configuration; it lists the CONFIGURED
    provider's. That is the sense a stale cached bundle needs -- its picker would
    otherwise offer models the run will never use, and store one of them into
    `caption_options.ollama_model` where the router would hand it to LM Studio.

    The URL stays because it is public surface. The two paths are asserted equal
    rather than each described on its own, so they cannot drift.
    """
    with app.app_context():
        config.save_config({'local_llm': {'provider': provider}})
    new = client.get('/api/local-llm/models')
    old = client.get('/api/ollama/models')
    assert old.status_code == new.status_code == 200
    assert old.get_json() == new.get_json()
    assert old.get_json()['provider'] == provider


@pytest.mark.parametrize('provider', ['ollama', 'lmstudio'])
def test_settings_lists_inactive_provider_at_draft_url_without_saving(
        app, client, monkeypatch, provider):
    other = 'lmstudio' if provider == 'ollama' else 'ollama'
    with app.app_context():
        config.save_config({'local_llm': {'provider': other},
                            'ollama': {'url': 'http://saved.invalid:11434'},
                            'lmstudio': {'url': 'http://saved.invalid:1234'}})
        config.set_secrets({'LMSTUDIO_API_KEY': 'lms-test-draft'})

    def forbidden(*args, **kwargs):
        pytest.fail('Model discovery must not save, start a server or load a model')

    monkeypatch.setattr(config, 'save_config', forbidden)
    monkeypatch.setattr(vision_llm, 'start_server', forbidden)
    monkeypatch.setattr(vision_llm, 'load_model', forbidden)
    calls = []

    class Response:
        status_code = 200

        def json(self):
            if provider == 'ollama':
                return {'models': [{'name': 'custom-vision:latest'}]}
            return {'models': [{'key': 'custom-vision', 'type': 'vlm'},
                               {'key': 'embedding-model', 'type': 'embedding'}]}

    def get(url, **kwargs):
        calls.append((url, kwargs.get('headers')))
        return Response()

    monkeypatch.setattr(vision_lmstudio.requests, 'get', get)
    draft = 'http://draft.invalid:1299'
    typed = draft + ('/v1/' if provider == 'lmstudio' else '/')
    response = client.post('/api/local-llm/models',
                           json={'provider': provider, 'url': typed})
    assert response.status_code == 200
    assert response.get_json() == {
        'ok': True, 'reachable': True, 'provider': provider,
        'models': ['custom-vision:latest' if provider == 'ollama' else 'custom-vision'],
    }
    endpoint = '/api/tags' if provider == 'ollama' else '/api/v1/models'
    assert calls and all(url == draft + endpoint for url, _ in calls)
    if provider == 'lmstudio':
        assert calls[0][1] == {'Authorization': 'Bearer lms-test-draft'}
    assert 'lms-test-draft' not in response.get_data(as_text=True)
    with app.app_context():
        assert config.get('local_llm.provider') == other
        assert config.get(f'{provider}.url').startswith('http://saved.invalid:')


@pytest.mark.parametrize('provider', ['ollama', 'lmstudio'])
@pytest.mark.parametrize('url', ['', 'file:///tmp/model', 'http://user:password@host',
                                 'http://host:invalid', 'http://[invalid'])
def test_settings_rejects_invalid_model_server_without_requesting_it(
        client, monkeypatch, provider, url):
    monkeypatch.setattr(vision_llm, 'list_models',
                        lambda **kw: pytest.fail('Invalid URL reached model discovery'))
    response = client.post('/api/local-llm/models',
                           json={'provider': provider, 'url': url})
    assert response.status_code == 400
    assert response.get_json()['error']


@pytest.mark.parametrize('provider', ['', 'unsupported'])
def test_settings_rejects_unknown_model_provider(client, monkeypatch, provider):
    monkeypatch.setattr(vision_llm, 'list_models',
                        lambda **kw: pytest.fail('Invalid provider reached model discovery'))
    response = client.post('/api/local-llm/models', json={'provider': provider})
    assert response.status_code == 400


@pytest.mark.parametrize('provider', ['ollama', 'lmstudio'])
@pytest.mark.parametrize('reachable', [False, True])
def test_settings_model_discovery_distinguishes_empty_from_unreachable(
        client, monkeypatch, provider, reachable):
    class Response:
        status_code = 200

        def json(self):
            return {'models': []}

    def get(*args, **kwargs):
        if not reachable:
            raise vision_lmstudio.requests.exceptions.ConnectionError('not running')
        return Response()

    monkeypatch.setattr(vision_lmstudio.requests, 'get', get)
    response = client.post('/api/local-llm/models', json={
        'provider': provider, 'url': 'http://draft.invalid:1299'})
    assert response.status_code == 200
    assert response.get_json() == {
        'ok': reachable, 'reachable': reachable, 'provider': provider, 'models': [],
    }


def test_draft_model_url_cannot_be_requested_through_get(client, monkeypatch):
    monkeypatch.setattr(vision_llm, 'list_models',
                        lambda **kw: pytest.fail('GET must not forward saved credentials'))
    response = client.get('/api/local-llm/models', query_string={
        'provider': 'lmstudio', 'url': 'https://other.invalid'})
    assert response.status_code == 400


def test_draft_model_discovery_requires_csrf(app, client, monkeypatch):
    app.config['WTF_CSRF_ENABLED'] = True
    calls = []
    monkeypatch.setattr(vision_llm, 'list_models', lambda **kw: calls.append(kw) or {
        'ok': True, 'reachable': True, 'provider': 'lmstudio', 'models': []})
    body = {'provider': 'lmstudio', 'url': 'https://draft.invalid/v1'}
    rejected = client.post('/api/local-llm/models', json=body)
    assert rejected.status_code == 400
    assert calls == [], 'A CSRF-less request reached model discovery'

    token = client.get('/api/csrf-token').get_json()['csrf_token']
    allowed = client.post('/api/local-llm/models', json=body,
                          headers={'X-CSRFToken': token})
    assert allowed.status_code == 200
    assert calls == [{'name': 'lmstudio', 'url': 'https://draft.invalid'}]


# --- the probes never raise, and say the real reason ------------------------

def test_a_server_that_answers_and_refuses_is_not_reported_as_switched_off(
        app, monkeypatch, as_lmstudio):
    """A 401 from a mistyped token used to read as "not answering — press Start
    Server", sending the user to restart a process that is already running while
    the real cause was thrown away."""
    monkeypatch.setattr(vision_lmstudio, 'list_models',
                        lambda **kw: _listing(ok=False, reachable=False,
                                              surface=None, last_status=401,
                                              last_body='unauthorized'))
    with app.app_context():
        verdict = capabilities.probe_lmstudio()
    assert verdict['ok'] is False
    assert 'HTTP 401' in verdict['detail']
    assert 'Start Server' not in verdict['detail']


def test_told_it_is_unreachable_the_model_probe_does_not_ask_again(
        app, monkeypatch, as_lmstudio):
    """`reachable=False` exists to spare the second round-trip; paying it anyway
    made a configured-but-down server block twice."""
    calls = []
    monkeypatch.setattr(vision_lmstudio, 'list_models',
                        lambda **kw: calls.append(1) or _listing())
    with app.app_context():
        verdict = capabilities.probe_lmstudio_model(reachable=False)
    assert verdict['ok'] is False
    assert calls == [], 'the probe asked the network it was told not to ask'


def test_the_documented_remedy_works_on_the_openai_only_surface(
        app, monkeypatch, as_lmstudio):
    """That surface reports no residency, so judged against it the very fix the
    docs give — "name a model in Settings" — could never succeed, leaving the user
    with no move at all."""
    monkeypatch.setattr(vision_lmstudio, 'list_models',
                        lambda **kw: _listing(surface='openai',
                                              models=[{'id': 'my/model', 'type': '',
                                                       'loaded': None}]))
    with app.app_context():
        ok = capabilities.probe_lmstudio_model(model='my/model')
        missing = capabilities.probe_lmstudio_model(model='other/model')
    assert ok['ok'] is True and 'trust' in ok['detail']
    assert missing['ok'] is False


def test_the_diagnostic_names_the_provider_and_describes_both(app, client):
    """A pasted report that mentions only Ollama says `reachable: false` about a
    daemon nobody uses and nothing about the one in charge — on the one artefact
    a remote diagnosis is made from."""
    body = client.get('/api/diagnostic').get_json()
    assert body['local_llm']['provider'] in ('ollama', 'lmstudio')
    assert 'lmstudio' in body and 'ollama' in body


# --- ensure_ready acts for one provider and reports for the other -----------

def test_ensure_ready_recovers_each_provider_with_its_own_gestures(app, monkeypatch):
    """Each provider heals its own way, and neither reaches for the other's tools.

    This test used to pin a REFUSAL for LM Studio — "only reports", on the
    written premise that it had no reliable launch. Both halves of that premise
    fell (the Start button, then the auto-load), and the pinned refusal is
    exactly what a user hit on ✨ Enhance. What must still hold is the boundary:
    an LM Studio install must never start an Ollama daemon, and an empty disk is
    the one state nothing can heal — the sentence hands back downloading, the
    single gesture that stays with the user.
    """
    started = []
    from app.services import ollama_control
    monkeypatch.setattr(ollama_control, 'ensure_captioning_ready',
                        lambda model=None: started.append(model) or {'ok': True})
    with app.app_context():
        config.save_config({'local_llm': {'provider': 'ollama'}})
        assert vision_llm.ensure_ready()['ok'] is True
    assert started == [None]

    monkeypatch.setattr(vision_lmstudio, 'list_models',
                        lambda **kw: _listing(models=[]))
    with app.app_context():
        config.save_config({'local_llm': {'provider': 'lmstudio'}})
        verdict = vision_llm.ensure_ready()
    assert verdict['ok'] is False
    assert 'download' in verdict['error'].lower(), (
        'nothing is downloaded, and the error must hand back the one gesture left')
    assert started == [None], 'LM Studio must not try to start Ollama'


# --- the rest of the router's dispatch --------------------------------------

def test_unload_and_probe_model_follow_the_provider(app, monkeypatch):
    seen = {}
    from app.services import vision_ollama
    monkeypatch.setattr(vision_ollama, 'unload_vision_model',
                        lambda **kw: seen.setdefault('who', 'ollama') is None or True)
    monkeypatch.setattr(vision_lmstudio, 'unload_vision_model',
                        lambda **kw: seen.setdefault('who', 'lmstudio') is None or True)
    with app.app_context():
        config.save_config({'local_llm': {'provider': 'lmstudio'}})
        vision_llm.unload_vision_model()
    assert seen['who'] == 'lmstudio'

    seen.clear()
    with app.app_context():
        config.save_config({'local_llm': {'provider': 'ollama'}})
        vision_llm.unload_vision_model()
    assert seen['who'] == 'ollama'


def test_probe_model_keeps_the_call_shape_the_gates_use(app, monkeypatch):
    """The six readiness gates call it with NO arguments, and two tests in this
    suite double `probe_ollama_model` with a zero-argument lambda — which is
    exactly how the old call site looked. Routing has to be invisible to them."""
    got = {}
    monkeypatch.setattr(capabilities, 'probe_ollama_model',
                        lambda **kw: got.update(kw) or {'ok': True, 'detail': ''})
    with app.app_context():
        config.save_config({'local_llm': {'provider': 'ollama'}})
        vision_llm.probe_model()
    assert got == {}, 'the router invented keyword arguments the old callers never passed'
