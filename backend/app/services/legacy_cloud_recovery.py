"""Keep pre-plugin rentals supervised without enabling Cloud Training."""
from __future__ import annotations

import threading

from flask import current_app, has_app_context

_STATE = 'lds_legacy_cloud_recovery'


def recovery_only() -> bool:
    """This host may finish existing rentals, but must never rent a new pod."""
    return has_app_context() and _STATE in current_app.extensions


def start(app) -> bool:
    """Bridge a V1 database to an empty/disabled V2 plugin installation.

    Normal plugin workers retain ownership when registered. The fallback adds
    no routes, features or configuration; its marker also blocks the legacy
    monitor's automatic replacement rentals. Existing runtime/retention limits
    still apply, including to terminal rows with deliberately kept pods. Any
    historical rental intent needs reconciliation: a failed provider DELETE
    can outlive a terminal row, or even the persistence of its instance ID.
    """
    registry = app.extensions.get('lds_plugins')
    if registry is not None:
        record = registry.records.get('cloud_training')
        if record is not None and (record.state == 'loaded' or record.recovery_active):
            return False
        if (any(owner == 'cloud_training' for owner, _ in registry.boot_hooks)
                or any(owner == 'cloud_training' for owner, _, _ in registry.workers)):
            return False
    if app.extensions.get(_STATE, {}).get('started'):
        return False

    from . import cloud_training
    from ..models import CloudTrainingRun

    try:
        with app.app_context():
            if CloudTrainingRun.query.first() is None:
                return False
        # Set before either worker can run: boot and monitor error recovery
        # both consult this app-specific mode before admitting another rental.
        app.extensions[_STATE] = {'started': False}
        cloud_training.start_supervisor(app)
        worker = threading.Thread(target=cloud_training.boot_recover, args=(app,),
                                  daemon=True, name='legacy-cloud-boot-recover')
        worker.start()
        app.extensions[_STATE]['started'] = True
        app.logger.warning('Existing cloud rentals are supervised in recovery-only mode. '
                           'Install Cloud Training to access their controls.')
        return True
    except Exception:
        app.logger.exception('Legacy cloud rental recovery could not start')
        return False
