"""Historical telemetry endpoint, available only with this product active."""
from flask import Blueprint, jsonify

from lds_sdk import hardware
from lds_sdk.lifecycle import is_available

bp = Blueprint('resource_monitor', __name__)


@bp.get('/stats')
def stats():
    if not is_available('resource_monitor'):
        return jsonify({'error': 'Resource monitor is disabled. Enable it and restart LDS.',
                        'plugin': 'resource_monitor'}), 409
    return jsonify(hardware.machine_stats())
