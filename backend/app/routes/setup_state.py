"""Setup state API: has this install already been checked out, and is it still OK?

Deliberately a separate blueprint from routes/setup.py — that one owns the
wizard's detection and the one-click installers, this one owns the "we already
did this, don't make the user watch it again" memory.
"""
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, request

from .. import capabilities
from .. import setup_state
from .. import config

bp = Blueprint('setup_state', __name__, url_prefix='/api/setup-state')


def _payload(state, caps, regressions):
    return {
        'verified': state['verified'],
        'verified_at': state['verified_at'],
        'completed': state.get('completed', False),
        'completed_at': state.get('completed_at'),
        'checks': state['checks'],
        'regressions': regressions,
        'capabilities': caps,
    }


@bp.post('/complete')
def complete():
    """Open the core workspace without requiring any optional engine or plugin."""
    try:
        body = request.get_json(silent=True)
        if (isinstance(body, dict) and body.get('goal') == 'dataset'
                and not config.get('comfyui.base_dir')):
            # Choosing the dataset-only journey explicitly defers generators.
            # Preserve configured local installs and remote connections. This
            # records intent without probing or declaring any service ready;
            # plugin restart still verifies its queue, including after a skip.
            try:
                address = urlsplit(str(config.get('comfyui.api_url') or ''))
            except ValueError:
                address = None
            if (address and address.scheme in ('http', 'https')
                    and address.hostname in ('localhost', '127.0.0.1', '::1')):
                config.save_config({'comfyui': {'setup_skipped': True}})
        if (capabilities.setup_is_docker_runtime()
                and not config.get('ollama.deployment_mode', '')):
            # Opening the core is also an explicit choice to defer optional
            # Ollama. Let the Docker launcher finish without starting a service.
            config.save_config({'ollama': {'deployment_mode': 'none'}})
        state = setup_state.complete_core()
    except OSError:
        return jsonify({'error': 'LDS could not save its workspace. Check that '
                        'its data folder is writable, then try again.'}), 503
    return jsonify({'completed': state['completed'],
                    'completed_at': state['completed_at']})


@bp.get('')
def get_state():
    """Whether the app may skip the onboarding redirect and re-check in the
    background instead.

    Uses the CACHED probe: this is read on every page load, right after
    /api/capabilities has already warmed it, so it costs nothing. The honest
    re-check is the POST below.
    """
    caps = capabilities.probe()
    state = setup_state.observe(caps)
    return jsonify(_payload(state, caps, setup_state.compare(caps, state)))


@bp.post('/recheck')
def recheck():
    """The background re-verification: the SAME full probe the Setup wizard runs
    (force=True, no cache), compared against what this install has proven it can
    do. `regressions` non-empty is the only thing worth interrupting the user
    for — everything else is a discreet "checked, all good"."""
    caps = capabilities.probe(force=True)
    state = setup_state.observe(caps)
    return jsonify(_payload(state, caps, setup_state.compare(caps, state)))


@bp.post('/dismiss')
def dismiss():
    """"I removed that on purpose" — stop reporting the named capabilities as
    regressions. Unknown keys are ignored rather than rejected: a stale tab
    dismissing a key this build no longer tracks should be a no-op, not a 400."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({'error': 'Expected a JSON object'}), 400
    keys = body.get('keys')
    if not isinstance(keys, list):
        return jsonify({'error': 'keys must be a list'}), 400
    state = setup_state.dismiss([k for k in keys if isinstance(k, str)])
    caps = capabilities.probe()
    return jsonify(_payload(state, caps, setup_state.compare(caps, state)))
