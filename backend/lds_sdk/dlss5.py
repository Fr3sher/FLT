"""API 1.21: admitted calls to the separately installed DLSS 5 engine."""
from importlib import import_module
from .lifecycle import is_available, state_change_lock


class NeuralRenderError(ValueError):
    """A refusal which can be shown by any optional integration."""


class ComparisonBusyError(NeuralRenderError):
    pass


class ComparisonTooLargeError(NeuralRenderError):
    pass


def _call(operation, *args, **kwargs):
    with state_change_lock:
        if not is_available('dlss5'):
            raise NeuralRenderError('Enable DLSS 5 in Plugins and restart LDS before rendering.')
        api = import_module('lds_dlss5.public_api_v1')
        if getattr(api, 'API_VERSION', None) != 1:
            raise NeuralRenderError('Update the DLSS 5 plugin to use this integration.')
        function = getattr(api, operation)
        if operation != 'render_video':
            return function(*args, **kwargs)
    # The engine takes its own product worker lease before spawning. Do not
    # hold a global configuration mutex for the duration of a native render.
    return function(*args, **kwargs)


def status():
    with state_change_lock:
        if not is_available('dlss5'):
            return {'available': False, 'ready': False,
                    'missing': ['Install and enable the DLSS 5 plugin.']}
        return _call('status')


def normalize_params(raw):
    return _call('normalize_params', raw)


def render_video(src, dst, params, **kwargs):
    return _call('render_video', src, dst, params, **kwargs)


def render_record(params, result=None):
    return _call('render_record', params, result)


def build_comparison(left, right, **kwargs):
    return _call('build_comparison', left, right, **kwargs)


__all__ = ['NeuralRenderError', 'ComparisonBusyError', 'ComparisonTooLargeError',
           'status', 'normalize_params', 'render_video', 'render_record', 'build_comparison']
