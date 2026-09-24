"""Local consent API; inherits LDS access-token and CSRF guards."""
from flask import Blueprint, jsonify, request

from ..usage_statistics import current, FEATURES, POLICY_VERSION

bp = Blueprint('usage_statistics', __name__, url_prefix='/api/usage-statistics')


@bp.get('')
def status():
    return jsonify(current().status())


@bp.put('')
def choose():
    body = request.get_json(silent=True)
    if (not isinstance(body, dict) or set(body) != {'enabled', 'policy_version'}
            or type(body.get('enabled')) is not bool
            or type(body.get('policy_version')) is not int
            or body['policy_version'] != POLICY_VERSION):
        return jsonify({'error': 'Choose whether to share the current usage statistics policy.'}), 400
    try:
        return jsonify(current().set_enabled(body['enabled']))
    except ValueError:
        return jsonify({'error': 'Usage statistics are not available in this build.'}), 409
    except OSError:
        return jsonify({'error': 'Could not save your choice. Check that the LDS data folder is writable.'}), 503


@bp.post('/activity')
def activity():
    service = current()
    if not service.status()['enabled']:
        return '', 204
    body = request.get_json(silent=True)
    if (not isinstance(body, dict) or set(body) != {'feature'}
            or not isinstance(body.get('feature'), str) or body['feature'] not in FEATURES):
        return jsonify({'error': 'Unknown activity category.'}), 400
    try:
        service.activity(body['feature'])
    except OSError:
        pass  # Best effort; never interrupt an interaction.
    return '', 204
