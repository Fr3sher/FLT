"""Prepare a selected plugin's components through the existing Setup workers.

This is a bounded batch, not a second installer. All membership and initial
preconditions are checked before the first run; each worker retains its normal
admission, FIFO, progress and retry rules.
"""
from __future__ import annotations

from .. import setup_installer as installer
from . import environment, storage
from .lifecycle import state_change_lock

MAX_ACTIONS = 64


class PreparationError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _selection(payload):
    if not isinstance(payload, dict) or set(payload) != {'actions'}:
        raise PreparationError('Select this plugin’s components before starting preparation.')
    actions = payload['actions']
    if (not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS
            or any(not isinstance(action, str) or not action or len(action) > 120 for action in actions)
            or len(set(actions)) != len(actions)):
        raise PreparationError('Select between 1 and 64 distinct installation actions.')
    return actions


def _allowed(record, registry, action):
    for catalog in (registry.install_actions, registry.model_downloads):
        spec = catalog.get(action)
        if spec is not None:
            return spec.get('plugin') == record.id
    if action == environment.action_id(record.id):
        return environment.action_spec(action, registry) is not None
    return False


def start(plugin_id, payload, *, registry, root):
    actions = _selection(payload)
    with state_change_lock:
        record = registry.records.get(plugin_id) if registry else None
        if record is None:
            raise PreparationError('This plugin is not installed.', 404)
        if installer._plugin_registry() is not registry:
            raise PreparationError('The active plugin registry changed. Reload LDS before preparing components.', 409)
        try:
            operations, errors = storage.pending(root)
        except (OSError, ValueError) as exc:
            raise PreparationError('The pending plugin changes could not be checked. Retry before preparing components.', 409) from exc
        if errors or plugin_id in operations:
            raise PreparationError('Apply the pending plugin changes and restart LDS before preparing components.', 409)
        try:
            environment.check_enabled(record, loaded=True)
        except environment.EnvironmentError as exc:
            raise PreparationError(str(exc), 409) from exc
        # Reject the WHOLE selection before any worker or environment is created.
        if any(not _allowed(record, registry, action) or not installer.known_action(action) for action in actions):
            raise PreparationError('The selection contains a component that does not belong to this plugin.')
        for action in actions:
            with installer._lock:
                active = installer._runs.get(action, {}).get('state') in ('running', 'queued')
            if not active:
                try:
                    installer.check_start_preconditions(action)
                    spec = registry.install_actions.get(action) or {}
                    preflight = spec.get('node_preflight')
                    if callable(preflight):
                        preflight()
                except (installer.Precondition, ValueError) as exc:
                    raise PreparationError(str(exc)) from exc
        statuses = {}
        for action in actions:
            try:
                statuses[action] = installer.start(action)
            except installer.AlreadyRunning:
                statuses[action] = installer.status(action)
            except (installer.Precondition, ValueError) as exc:
                # A runtime precondition can change after the initial checks;
                # report that member's failure without substituting another plan.
                statuses[action] = {'state': 'error', 'returncode': None, 'log': [str(exc)]}
            with installer._lock:
                run = installer._runs.get(action)
                if run and run.get('state') in ('running', 'queued'):
                    run.setdefault('preparation_plugins', set()).add(plugin_id)
        return {'plan': actions, 'statuses': statuses}
