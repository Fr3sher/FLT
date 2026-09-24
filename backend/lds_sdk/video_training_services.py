"""Enabled Video API v1; no product import is performed while it is absent/OFF."""

__all__ = ['build_job_config', 'image_supports_training_adapter', 'image_supports_ref2va',
           'job_name_for', 'training_controls', 'get_target', 'record', 'harvested_steps',
           'reference_dirs', 'deployment_spec', 'session', 'block_attention_backends',
           'video_training', 'video_targets', 'video_run_lineage', 'video_bank_service']

def _provider():
    import importlib
    from flask import current_app, has_app_context
    from app.plugins.optional import ServiceUnavailable
    from app.plugins.registry import active
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    record = registry.records.get('video') if registry else None
    from app import config
    flags = (config.get('plugins') or {}).get('enabled') or {}
    if (record is None or not record.enabled or record.state != 'loaded'
            or flags.get('video') is False):
        raise ServiceUnavailable('video', 'Video is not enabled')
    try:
        module = importlib.import_module('lds_video.public_api_v1')
    except ImportError as exc:
        raise ServiceUnavailable('video', 'Video is unavailable') from exc
    if module.API_VERSION != 1:
        raise ServiceUnavailable('video', 'The Video integration API is incompatible')
    return module

def build_job_config(*args, **kwargs):
    return _provider().build_job_config(*args, **kwargs)


def image_supports_training_adapter(*args, **kwargs):
    return _provider().image_supports_training_adapter(*args, **kwargs)


def image_supports_ref2va(*args, **kwargs):
    return _provider().image_supports_ref2va(*args, **kwargs)


def job_name_for(*args, **kwargs):
    return _provider().job_name_for(*args, **kwargs)


def training_controls(*args, **kwargs):
    return _provider().training_controls(*args, **kwargs)


def get_target(*args, **kwargs):
    return _provider().get_target(*args, **kwargs)


def record(*args, **kwargs):
    return _provider().record(*args, **kwargs)


def harvested_steps(*args, **kwargs):
    return _provider().harvested_steps(*args, **kwargs)


def reference_dirs(*args, **kwargs):
    return _provider().reference_dirs(*args, **kwargs)


def deployment_spec(*args, **kwargs):
    from . import live_services
    if live_services.available():
        return live_services.deployment_spec(*args, **kwargs)
    return _provider().deployment_spec(*args, **kwargs)


def session():
    from . import live_services
    if live_services.available():
        return live_services.session()
    from app.plugins.optional import ServiceUnavailable
    try:
        provider = _provider()
    except ServiceUnavailable:
        return None
    return provider.session()



class _Training:
    build_job_config = staticmethod(build_job_config)
    image_supports_training_adapter = staticmethod(image_supports_training_adapter)
    image_supports_ref2va = staticmethod(image_supports_ref2va)
    job_name_for = staticmethod(job_name_for)
    training_controls = staticmethod(training_controls)


class _Targets:
    get = staticmethod(get_target)


class _RunLineage:
    record = staticmethod(record)
    harvested_steps = staticmethod(harvested_steps)


class _Bank:
    reference_dirs = staticmethod(reference_dirs)


video_training, video_targets = _Training(), _Targets()
video_run_lineage, video_bank_service = _RunLineage(), _Bank()


def block_attention_backends(node_info):
    from . import live_services
    if live_services.available():
        return live_services.block_attention_backends(node_info)
    return _provider().block_attention_backends(node_info)
