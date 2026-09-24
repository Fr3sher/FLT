"""Video Bank, video datasets, clip Studio and their complete installation.

Live channels are installed separately starting with Video 1.1.
"""
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
    from . import downloads, probes, video_reference_catalog, video_references
    from .routes import video_bank, video_datasets, video_studio

    ctx.register_install_action('video', label='Install video decoding and analysis dependencies',
                                python='capability', requirements=ctx.dir / 'requirements-host.txt')
    ctx.register_install_action('video_host', label='Install Video tools in the LDS interpreter',
                                python='app', requirements=ctx.dir / 'requirements-host.txt',
                                verify=probes.video_host_ready)

    ctx.register_install_action('shot_detect', label='Install shot-boundary detection',
                                python='capability', packages=('transnetv2-pytorch', 'av'))
    ctx.register_node_pack('h3_refmods_nodes')
    ctx.register_node_pack('h3_clipproj_nodes')
    ctx.register_node_pack('h3_spectrum_nodes')
    from .performance_install import install_writer
    ctx.register_install_action('h3_fast_writer', label='Install the fast synchronous MP4 writer',
                                run=install_writer)

    # The URLs the screens already call.
    ctx.register_blueprint(video_bank.bp, url_prefix='/api')
    ctx.register_blueprint(video_datasets.bp, url_prefix='/api')
    ctx.register_request_limit('video_datasets.video_dataset_import', 1024 * 1024 * 1024)
    ctx.register_blueprint(video_studio.bp, url_prefix='/api/video-studio')

    # The queue routes this lane's finished jobs here by the flags it writes.
    ctx.register_job_handler('is_video_test', _video_test_done, presentation={
        'title': 'Video clip', 'surface': 'Video Test Studio',
    })
    ctx.register_hook('job_queue.keep_inputs', _keep_inputs)
    ctx.register_hook('job_queue.unlinked_results', _unlinked_results)
    # The reference upload is the one request allowed past the ordinary ceiling.
    ctx.register_request_limit('video_studio.video_studio_reference_stage',
                               video_references.MAX_UPLOAD_BYTES + 1024 * 1024)

    # The Studio's readiness, options and packs; the DLSS bridge (9 rows).
    for key, fn in probes.PROBES.items():
        ctx.register_probe(key, fn)

    # The Video Test Studio's weights and the reference videos, under the core's
    # own downloader (streaming, disk precondition, integrity, the 401/403 recovery).
    for key, spec in {**downloads.H3_DOWNLOADS, **video_reference_catalog.reference_downloads()}.items():
        ctx.register_model_download(
            key, url=spec['url'], dest=spec['dest'], min_free_gb=spec['min_free_gb'],
            min_bytes=spec['min_bytes'], license_url=spec.get('license_url'),
            gated=bool(spec.get('gated')), legacy_names=spec.get('legacy_names', ()),
            expected_bytes=spec.get('expected_bytes'), sha256=spec.get('sha256'),
            companions=spec.get('companions', ()), complete=spec.get('complete'),
            extra_roots=spec.get('extra_roots'))
