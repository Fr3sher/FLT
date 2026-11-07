"""Live channels, independently installed from Video Bank and clip Studio."""


def _live_done(job_id, filename, failed=False, reason=None, metadata=None):
    from . import live_studio
    live_studio.link_completed_live_clip(
        job_id, filename, failed=failed, reason=reason,
        session_id=(metadata or {}).get('live_session'))


def _restart_blockers(reasons):
    from . import live_studio
    live = live_studio.current()
    if (live is not None and live.state in ('starting', 'running', 'stopping')):
        return list(reasons) + ['Stop the local Live channel before restarting ComfyUI.']
    return reasons


def _disable_blockers(reasons, plugin_id):
    from . import live_studio
    live = live_studio.current()
    if plugin_id == 'live' and live is not None and live.state in ('starting', 'running', 'stopping'):
        return list(reasons) + ['Stop the Live channel and let its clips finish before disabling Live.']
    return reasons


def _free_memory_blockers(reasons):
    from . import live_studio
    live = live_studio.current()
    if (live is not None and live.state in ('starting', 'running', 'stopping')
            and live.params.get('gpu', 'local') != 'rented'):
        return list(reasons) + [
            'Stop the local Live channel and let its current clips finish before freeing the memory.']
    return reasons


def register(ctx):
    from . import setup
    from .routes import video_live
    ctx.register_blueprint(video_live.bp, url_prefix='/api/video-studio/live')
    # H3 LoRAs commonly exceed the ordinary 64 MiB form limit.
    ctx.register_request_limit('video_live.live_lora_import', 1024 * 1024 * 1024)
    ctx.register_job_handler('is_live', _live_done, presentation={
        'title': 'Live clip', 'surface': 'Live channels', 'engine': 'MiniMax H3',
        'cancel_scope': 'owner', 'stop_label': 'the Live channel',
    })
    ctx.register_hook('comfyui.restart_blockers', _restart_blockers)
    ctx.register_hook('system.free_memory_blockers', _free_memory_blockers)
    ctx.register_hook('plugin.disable_blockers', _disable_blockers)
    setup.register(ctx)
