"""Provider-routed local LLM API.

One path both surfaces call, so a Bank picker and a Dataset picker can never end
up listing different providers' models — the divergence the repo's Bank/Dataset
parity rule exists to prevent. `/api/ollama/models` survives as an alias of the
same function for older cached bundles.
"""
from flask import Blueprint, jsonify, request

from ..services import vision_llm

bp = Blueprint('local_llm', __name__, url_prefix='/api/local-llm')


@bp.post('/start')
def start_server():
    """Start the configured provider's local server (idempotent).

    Always HTTP 200 — "not installed" / "did not start" are handled OUTCOMES, not
    server faults, and a 5xx would make apiFetch throw AND auto-toast a generic
    error on top of the specific one. The body carries {ok, reachable, error?,
    stderr?} either way; clients read `reachable`.
    """
    return jsonify(vision_llm.start_server()), 200


@bp.post('/load')
def load_model():
    """Load the provider's vision model now (explicit click; probes never do this).

    Always 200 -- "nothing downloaded" is a handled outcome with its remedy in the
    body, and a 5xx would stack a generic toast on top of the specific sentence.
    """
    return jsonify(vision_llm.load_model()), 200


@bp.post('/pull')
def start_pull():
    """Download the named model through the CONFIGURED provider (explicit click).

    One routed path, like /models and /load: the same button works whichever
    server the install runs — Ollama pulls, LM Studio downloads its job, and the
    answer keeps the pull shape both UIs already render. Always 200; the body
    carries {ok, state, model, progress, log, error}.
    """
    data = request.get_json(silent=True) or {}
    model = data.get('model') or ''
    if vision_llm.provider() == 'lmstudio':
        from ..services import lmstudio_download
        return jsonify(lmstudio_download.start_download(model)), 200
    from ..services import ollama_control
    return jsonify(ollama_control.start_pull(model)), 200


@bp.get('/pull')
def pull_status():
    """Poll the current/last download: {state, model, progress, log, error}."""
    if vision_llm.provider() == 'lmstudio':
        from ..services import lmstudio_download
        return jsonify(lmstudio_download.download_status()), 200
    from ..services import ollama_control
    return jsonify(ollama_control.pull_status()), 200


@bp.route('/models', methods=['GET', 'POST'])
def list_models():
    """Models the configured provider, or a Settings draft, can caption with.

    GET keeps the configured-provider contract. A Settings draft uses a
    CSRF-protected POST: LM Studio discovery may forward its saved API key, so
    a cross-site GET must never be able to choose the destination.

    Valid requests answer 200 — {ok, reachable, provider, models:[...]}. An unreachable server
    is a handled outcome (empty list), never a server fault: every picker that
    reads this degrades to "no models" rather than showing an error nobody can act
    on from a dropdown. JSON provider/url overrides only inspect that server;
    they never save settings. Invalid overrides answer 400 before any request.
    """
    if request.method == 'GET':
        if 'url' in request.args:
            return jsonify({'error': 'Use POST to inspect a draft server URL.'}), 400
        return jsonify(vision_llm.list_models()), 200
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected an object with a provider and server URL.'}), 400
    name = data.get('provider')
    if name is not None and name not in vision_llm.PROVIDERS:
        return jsonify({'error': 'Choose Ollama or LM Studio.'}), 400
    url = data.get('url')
    if 'url' in data:
        if (name or vision_llm.provider()) == vision_llm.LMSTUDIO:
            from ..services.vision_lmstudio import _suffix_free
            try:
                url = _suffix_free(url)
            except ValueError:
                url = ''
        else:
            from ..capabilities import _validated_setup_http_base
            url = _validated_setup_http_base(url)
        if not url:
            return jsonify({'error': 'Enter a valid HTTP or HTTPS server URL without credentials.'}), 400
    return jsonify(vision_llm.list_models(name=name, url=url)), 200
