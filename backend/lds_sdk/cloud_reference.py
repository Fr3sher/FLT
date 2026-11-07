"""Optional Reference contract; absent/old Cloud never loads private modules."""
from .cloud_live import provider, _require_reference
from .plugin_services import ServiceUnavailable

__all__ = ['availability', 'normalize_profile', 'pack_files', 'native_profile', 'native_aspects', 'native_pack_bytes',
           'native_image_limit', 'validate_native_profile', 'validate_native_settings',
           'native_target', 'validate_native_prompt', 'native_image_bytes',
           'validate_native_request', 'clean_diagnostic', 'diagnostic_summary', 'select_hardware']


def _provider():
    module = provider()
    _require_reference(module)
    if not callable(getattr(module, 'reference_operation', None)):
        raise ServiceUnavailable('cloud_training', 'Update Cloud to use the Reference rendering contract.')
    return module


def availability():
    try:
        _provider()
        return {'ok': True, 'detail': ''}
    except ServiceUnavailable as exc:
        return {'ok': False, 'detail': str(exc)}


def _call(name, *args, **kwargs):
    return _provider().reference_operation(name, *args, **kwargs)


def normalize_profile(profile=None):
    return _call('normalize_profile', profile)


def pack_files(profile=None):
    return _call('pack_files', profile)


def native_profile():
    return _call('native_profile')


def native_aspects():
    return _call('native_aspects')


def native_image_limit():
    return _call('native_image_limit')


def native_pack_bytes():
    return _call('native_pack_bytes')


def validate_native_profile(profile):
    return _call('validate_native_profile', profile)


def validate_native_settings(settings):
    return _call('validate_native_settings', settings)


def native_target(*args, **kwargs):
    return _call('native_target', *args, **kwargs)


def validate_native_prompt(prompt):
    return _call('validate_native_prompt', prompt)


def native_image_bytes(value):
    return _call('native_image_bytes', value)


def validate_native_request(value):
    return _call('validate_native_request', value)


def clean_diagnostic(value):
    return _call('clean_diagnostic', value)


def diagnostic_summary(value):
    return _call('diagnostic_summary', value)


def select_hardware(gpu_name, gpus):
    return _call('select_hardware', gpu_name, gpus)
