"""Provider admission and the host-wide serialized configuration transition."""
from app.plugins.lifecycle import state_change_lock


from flask import current_app, has_app_context


def is_available(plugin_id):
    from app import config
    from app.plugins.registry import active
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    record = registry.records.get(plugin_id) if registry else None
    return ((config.get('plugins.enabled') or {}).get(plugin_id) is not False
            and record is not None and record.enabled and record.state == 'loaded')


__all__ = ['is_available', 'state_change_lock']


def require_plugins(plugin_ids, error_type=RuntimeError):
    for plugin_id in plugin_ids:
        if not is_available(plugin_id):
            raise error_type(f'Cloud training requires the enabled {plugin_id} plugin. '
                             'Enable it and restart the app before renting a GPU.')


def probe():
    from app import capabilities
    return capabilities.probe()
