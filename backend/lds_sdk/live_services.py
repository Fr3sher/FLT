"""Live integration with legacy combined-Video support (SDK 1.10).

The installed job owner decides the provider. Explicitly disabled Live never
falls back to another product. Legacy Video is accepted only while it actually
owns is_live; Video 1.1 has no such ownership.
"""
import importlib
from flask import current_app, has_app_context
from app.plugins.optional import ServiceUnavailable


def provider_id():
    from app.plugins.registry import active
    from .lifecycle import is_available
    registry = current_app.extensions.get('lds_plugins') if has_app_context() else active()
    if registry is None:
        raise ServiceUnavailable('live', 'Live is not installed')
    owner = registry.job_handlers.get('is_live', (None, None))[0]
    if owner not in ('live', 'video') or not is_available(owner):
        raise ServiceUnavailable('live', 'Live is not enabled')
    return owner


def available():
    try:
        provider_id()
        return True
    except ServiceUnavailable:
        return False


def session():
    try:
        owner = provider_id()
    except ServiceUnavailable:
        return None
    module = importlib.import_module('lds_live.public_api_v1' if owner == 'live' else 'lds_video.public_api_v1')
    if module.API_VERSION != 1:
        raise ServiceUnavailable('live', 'The Live integration API is incompatible')
    return module.session()


def deployment_spec():
    provider_id()
    from . import h3_render as render
    return {'base_workflow': render.load_base_workflow(), 'sage_class': render.SAGE_CLASS,
            'block_attention_class': render.BLOCK_ATTN_CLASS,
            'option_node_packs': dict(render.OPTION_NODE_PACKS)}


def block_attention_backends(node_info):
    provider_id()
    from . import h3_render
    return h3_render.block_attention_backends(node_info)


__all__ = ['provider_id', 'available', 'session', 'deployment_spec', 'block_attention_backends']
