"""Versioned finishing engine API, accessed through lds_sdk.dlss5."""
from . import neural_render

API_VERSION = 1


def status():
    return neural_render.status()


def normalize_params(raw):
    return neural_render.normalize_params(raw)


def render_video(src, dst, params, **kwargs):
    return neural_render.render_video(src, dst, params, **kwargs)


def render_record(params, result=None):
    return neural_render.render_record(params, result)


def build_comparison(left, right, **kwargs):
    return neural_render.build_comparison(left, right, **kwargs)


__all__ = ['API_VERSION', 'status', 'normalize_params', 'render_video',
           'render_record', 'build_comparison']
