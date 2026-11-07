"""Host admission for optional product calls and settings scopes."""
from flask import current_app, has_app_context


def plugin_available(plugin_id):
    from . import config
    from .plugins.registry import active
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    record = registry.records.get(plugin_id) if registry else None
    return bool(record is not None and record.enabled and record.state == 'loaded'
                and (config.get('plugins.enabled') or {}).get(plugin_id) is not False)


def require_plugin(plugin_id):
    if not plugin_available(plugin_id):
        raise ValueError(f'{plugin_id} is unavailable. Enable the plugin and restart LDS.')
