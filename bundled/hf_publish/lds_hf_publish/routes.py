"""The three routes of the dataset publisher — the URLs the screen already
calls, under the core's ``/api`` prefix (the façade registers the blueprint
there). The slow upload runs in a daemon thread; the screen polls ``status``."""
from flask import Blueprint, current_app, jsonify, request

from lds_sdk import config as cfg
from lds_sdk.dataset_exports import DatasetExports

from . import publish as hf_publish

bp = Blueprint('hf_publish', __name__)


@bp.get('/dataset/<int:dataset_id>/publish-hf/whoami')
def dataset_publish_hf_whoami(dataset_id):
    """Prefill helper for the Publish modal: the token owner's username and the
    suggested `<username>/<slug>` repo id. Best-effort — a missing/invalid token
    just yields username=null (the modal degrades to a free-text field)."""
    ds = DatasetExports(cfg.local_user()).get_dataset(dataset_id)
    if not ds:
        return jsonify({'error': 'not found'}), 404
    username = hf_publish.hf_namespace(cfg.secret('HF_TOKEN'))
    return jsonify({'ok': True, 'username': username,
                    'default_repo_id': hf_publish.default_repo_id(username, ds),
                    'licenses': list(hf_publish.LICENSE_CHOICES)})


@bp.post('/dataset/<int:dataset_id>/publish-hf')
def dataset_publish_hf(dataset_id):
    """Kick off the background upload of this dataset to the HF Hub. Server-side
    guards: HF_TOKEN must exist, `consent` MUST be true (not merely a UI checkbox),
    dataset must exist. The slow upload runs in a daemon thread; the UI polls the
    status route. Structured preflight errors (read-only token, repo exists) also
    surface via the status poll."""
    if not DatasetExports(cfg.local_user()).get_dataset(dataset_id):
        return jsonify({'error': 'not found'}), 404
    token = cfg.secret('HF_TOKEN')
    if not token:
        return jsonify({'error': 'no Hugging Face token configured — paste an '
                        'HF_TOKEN in Plugins → Publish to Hugging Face → Settings'}), 400
    data = request.get_json(silent=True) or {}
    if data.get('consent') is not True:
        return jsonify({'error': 'you must confirm you have the right to share these '
                        'images and the consent of any identifiable person'}), 400
    repo_id = (data.get('repo_id') or '').strip()
    if not repo_id:
        return jsonify({'error': 'repo id is required'}), 400
    license = (data.get('license') or '').strip().lower()
    if license not in hf_publish.LICENSE_CHOICES:
        return jsonify({'error': f'unsupported license: {license or "(empty)"}'}), 400
    out = hf_publish.start_publish(
        current_app._get_current_object(), dataset_id, repo_id,
        private=bool(data.get('private', True)), nfaa=bool(data.get('nfaa', True)),
        license=license, include_ref=bool(data.get('include_ref', False)), token=token)
    return jsonify({'ok': True, **out})


@bp.get('/dataset/<int:dataset_id>/publish-hf/status')
def dataset_publish_hf_status(dataset_id):
    """Poll: {state: idle|running|done|error, repo_url, error, error_code, count}."""
    return jsonify(hf_publish.publish_status(dataset_id))
