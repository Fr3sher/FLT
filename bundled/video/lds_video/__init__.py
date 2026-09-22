"""Public Video Bank, training sets and clip Studio. Live is separate."""
from __future__ import annotations

def _video_test_done(job_id, filename, failed=False, reason=None, metadata=None):
    # A Video Test Studio clip: the mp4 arrives under the history's `images` key
    # like any image does — only the metadata this lane wrote tells it apart.
    from . import video_test_studio
    video_test_studio.link_completed_clip(job_id, filename, failed=failed, reason=reason)

def _unlinked_results(job_ids):
    from .models import VideoTestClip
    return list(job_ids) + [row.job_id for row in VideoTestClip.query.filter(
        VideoTestClip.status == 'pending', VideoTestClip.filename.is_(None),
        VideoTestClip.job_id.isnot(None)).all()]

def _keep_inputs(keep):
    # 🎬 Clips rendered before their frames were kept beside them get their copies
    # now, from what the sweep is about to clear; a frame the backfill could not
    # copy is the only picture left of its clip — untouchable, whatever its age.
    from . import video_test_studio
    _made, not_kept = video_test_studio.keep_frames_of_existing_clips()
    return set(keep) | set(not_kept)

def register(ctx):
    from . import downloads, probes
    from .routes import video_bank, video_datasets, video_studio

    ctx.register_install_action('video', label='Prepare video decoding and analysis',
                                python='capability', requirements=ctx.dir / 'requirements-host.txt')
    ctx.register_install_action('shot_detect', label='Install shot-boundary detection',
                                python='capability', packages=('transnetv2-pytorch', 'av'))
    ctx.register_install_action('video_host', label='Prepare Video tools in LDS',
                                python='app', requirements=ctx.dir / 'requirements-host.txt',
                                verify=probes.video_host_ready)
    ctx.register_blueprint(video_bank.bp, url_prefix='/api')
    ctx.register_blueprint(video_datasets.bp, url_prefix='/api')
    ctx.register_blueprint(video_studio.bp, url_prefix='/api/video-studio')
    ctx.register_job_handler('is_video_test', _video_test_done, presentation={
        'title': 'Video clip', 'surface': 'Video Test Studio',
    })
    ctx.register_hook('job_queue.keep_inputs', _keep_inputs)
    ctx.register_hook('job_queue.unlinked_results', _unlinked_results)
    for key, fn in probes.PROBES.items():
        ctx.register_probe(key, fn)
    for key, spec in downloads.H3_DOWNLOADS.items():
        ctx.register_model_download(
            key, url=spec['url'], dest=spec['dest'], min_free_gb=spec['min_free_gb'],
            min_bytes=spec['min_bytes'], license_url=spec.get('license_url'),
            gated=bool(spec.get('gated')), legacy_names=spec.get('legacy_names', ()),
            expected_bytes=spec.get('expected_bytes'), sha256=spec.get('sha256'),
            companions=spec.get('companions', ()), complete=spec.get('complete'),
            extra_roots=spec.get('extra_roots'))
