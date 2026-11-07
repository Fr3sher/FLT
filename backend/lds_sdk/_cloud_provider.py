"""Resolve the declared Cloud API, with separate recovery admission."""


def provider(*, recovery=False):
    import importlib
    from flask import current_app, has_app_context
    from app.plugins.optional import ServiceUnavailable
    from app.plugins.registry import active
    from app import config
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    record = registry.records.get('cloud_training') if registry is not None else None
    ready = record is not None and record.state == 'loaded'
    if recovery:
        ready = ready or (record is not None and getattr(record, 'recovery_active', False))
    elif (not getattr(record, 'enabled', False)
          or (config.get('plugins.enabled') or {}).get('cloud_training') is False):
        ready = False
    if not ready:
        raise ServiceUnavailable('cloud_training', 'Cloud is not enabled')
    module = importlib.import_module('lds_cloud_training.public_api_v1')
    if module.API_VERSION != 1:
        raise ServiceUnavailable('cloud_training', 'The Cloud API is incompatible')
    return module
