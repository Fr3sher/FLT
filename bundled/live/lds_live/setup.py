"""Live's own installation actions reuse H3 files without installing Video."""
from lds_sdk import h3_render as h3
from lds_sdk.h3_downloads import H3_DOWNLOADS
from lds_sdk.video_host.ffmpeg_tools import ffmpeg_ready

MODEL_ACTIONS = ('h3_base', 'h3_text_encoder', 'h3_video_vae', 'h3_audio_vae',
                 'h3_turbo_lora')


def missing_weights():
    return [{**row, 'action': 'live_' + row['action']}
            for row in h3.missing_weights() if row.get('action') in MODEL_ACTIONS]


def encoder_ready(force=False):
    return bool(ffmpeg_ready(force=force).get('ok'))


def facts():
    from lds_sdk.lifecycle import is_available
    if not is_available('live'):
        return {}
    from lds_sdk.local_render import comfyui_reachable
    missing = missing_weights()
    reachable = comfyui_reachable()
    return {'missing': missing, 'ready': reachable and h3.studio_ready(missing),
            'encoder': encoder_ready(), 'options': h3.option_availability(),
            'sage': {**h3.SAGE_PACK, 'present': h3.sage_available()}}


def register(ctx):
    ctx.register_probe('live', facts)
    ctx.register_install_action('live_encoder', label='Install Live stream encoder',
                                python='app', requirements=ctx.dir / 'requirements-host.txt',
                                verify=lambda: encoder_ready(force=True))
    for key in MODEL_ACTIONS:
        action = f'live_{key}'
        ctx.register_model_download(action, **H3_DOWNLOADS[key])
