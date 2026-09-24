"""Standalone SeedVR2 restoration product: settings, setup and shared image actions."""
from . import seedvr2_helper as svr
from .downloads import DOWNLOADS
from lds_sdk.local_render import comfyui_reachable

SEEDVR2_INSTALL_ORDER = ('seedvr2_nodes', 'seedvr2_model', 'seedvr2_vae')

def _complete(action):
    return (action not in svr.seedvr2_missing_assets()
            and not any(item['asset'] == action and item.get('blocking')
                        for item in svr.seedvr2_invalid_assets()))

def _ready():
    reachable = comfyui_reachable()
    return svr.engine_ready(reachable,
                            nodes_missing=svr.seedvr2_missing_nodes() if reachable else [])

def register(ctx):
    from .routes import bp
    from .errors import error_response
    from . import finishing
    ctx.register_blueprint(bp, url_prefix='/api')
    ctx.register_node_pack('seedvr2_nodes')
    for action, spec in DOWNLOADS.items():
        ctx.register_model_download(action, **spec,
                                    complete=lambda action=action: _complete(action))
    ctx.register_install_group('seedvr2', SEEDVR2_INSTALL_ORDER,
                               missing_key='seedvr2_missing', invalid_key='seedvr2_invalid',
                               nodes_missing_key='seedvr2_nodes_missing',
                               nodes_installed_key='seedvr2_nodes_installed',
                               pack_action='seedvr2_nodes')
    for key, fn in {
        'seedvr2_missing': svr.seedvr2_missing_assets,
        'seedvr2_invalid': svr.seedvr2_invalid_assets,
        'seedvr2_nodes_missing': lambda: svr.seedvr2_missing_nodes() if comfyui_reachable() else [],
        'seedvr2_nodes_installed': svr.seedvr2_node_pack_installed,
        'seedvr2_ready': _ready,
        'seedvr2_tiling_ready': lambda: svr.tiling_available(comfyui_reachable()),
        'seedvr2_tiling_nodes_missing': lambda: svr.ttp_missing_nodes() if comfyui_reachable() else [],
        'seedvr2_ceiling_mp': svr.full_frame_ceiling_mp,
    }.items():
        ctx.register_probe('comfyui.' + key, fn)
    ctx.register_restore_engine('seedvr2', preflight=svr.preflight,
                                enqueue=svr.enqueue_seedvr2_upscale,
                                error_response=error_response, finishing=finishing.profile)
