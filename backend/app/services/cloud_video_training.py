"""Launching a cloud training run on a VIDEO dataset.

Its own module rather than a branch of `launch_cloud_training`, for the same
reason `video_training` is not a branch of `lora_training`: that function is
~250 lines of FACE preflight — image counts, caption quality, rembg masking,
custom VAE/TE overrides, slider prompt pairs, HF custom-base pushes, the
provenance registry — and a video dataset has none of those columns. Threading a
`VideoDataset` through it would mean a flag on every one of those blocks, in a
file two other sessions are editing.

What it DOES reuse is everything after the decision: the reservation lock, the
run row, the provisioning, the monitor thread, the stop path, the harvest. A
video run is an ordinary `cloud_training_run` row carrying
`dataset_table='video_dataset'`; from the monitor's point of view the only
differences are which folder gets uploaded and which builder writes the config,
and both of those are single seams in cloud_training (`_staging_dataset_dir`,
`_build_pod_job_config`).

EVERY REFUSAL HAPPENS BEFORE THE RESERVATION
--------------------------------------------
The point of raising in `video_training.build_job_config` was to fail before a
GPU is rented. That only holds if the config is built BEFORE the run row exists —
otherwise the refusal arrives from the monitor thread, minutes later, with a pod
already on the clock and a `preparing` row wedging the single-run guard. So this
function builds the config first, purely to see it raise, and throws the result
away; the monitor rebuilds it at pod boot from the stamped params, exactly like
the face lane (a rebuild is what keeps a launch from being retargeted mid-flight).
"""
import json
import logging
import os

from ..extensions import db
from ..models import CloudTrainingRun, VideoDataset
from . import cloud_run_dataset as crd
from . import cloud_training as ct
from . import video_training

logger = logging.getLogger(__name__)

# What the pod needs to see in the folder before renting anything. `.mp4` is the
# only extension the exporter writes and the only video extension the upload
# ships; a folder without one uploads captions alone and trains on nothing.
_CLIP_EXT = '.mp4'


def _count_clips(folder) -> int:
    try:
        return sum(1 for f in os.listdir(folder)
                   if f.lower().endswith(_CLIP_EXT))
    except OSError:
        return 0


def _start_pod(run):
    """Hand the run to the shared monitor thread, which rents the pod, uploads
    the folder, builds the job and harvests the saves. A named seam rather than
    an inline pair of calls so a route test can neutralise exactly this step —
    everything before it (the refusals, the reservation, the stamp) then runs for
    real instead of being mocked away with it."""
    ct._stop_event_for(run.id).clear()
    ct._start_monitor(run.id)


def launch_cloud_video_training(user_id, video_dataset_id, steps=1000,
                                base_model=None, low_vram=False, gpu_name=None,
                                _provision=None) -> dict:
    """Rent a pod and train a LoRA on a built video dataset.

    `low_vram` defaults to FALSE here and True in the builder, and the asymmetry
    is the whole point of this lane: on a 24 GB card the flag is mandatory and
    costs 170-185 s a step shuttling the idle expert over PCIe; on the 80 GB pod
    this function rents, leaving it on would pay cloud prices for the local
    machine's handicap.

    `_provision` overrides `_start_pod` for callers that drive provisioning
    themselves; leave it None and the shared monitor takes over, exactly as it
    does for a face run.
    """
    ds = VideoDataset.query.get(int(video_dataset_id))
    if ds is None or str(ds.user_id) != str(user_id):
        raise ValueError('video dataset not found')

    clips = _count_clips(ds.output_dir or '')
    if not clips:
        raise ValueError(
            f'this video dataset has no {_CLIP_EXT} clips on disk — there would '
            'be nothing to train on; rebuild it before launching')

    n_steps = max(100, int(steps or 1000))
    # Built HERE, before the reservation, purely so an unsupported target raises
    # now rather than from the monitor thread with a pod already running. The
    # result is deliberately discarded: the monitor rebuilds it from the stamped
    # params at pod boot.
    video_training.build_job_config(
        ds, str(ds.output_dir), n_steps, training_folder='__POD__',
        base_model=base_model, low_vram=low_vram)

    fam = 'video'
    with ct._launch_reservation_lock:
        ct._assert_launch_guardrails(ds.id, fam, crd.VIDEO)
        run = CloudTrainingRun(
            dataset_id=ds.id, status='preparing',
            dataset_table=crd.VIDEO,
            run_name=video_training.job_name_for(ds),
            train_params=json.dumps({
                'train_type': fam,
                'steps': n_steps,
                'base_model': base_model or '',
                'low_vram': bool(low_vram),
                'target_profile': ds.target_profile,
                'frames': ds.frames,
                'artifact_kind': 'lora',
                **({'requested_gpu': str(gpu_name)} if gpu_name else {}),
            }))
        # Deliberately NO `version` key and no checkpoint_registry call. That
        # registry freezes a manifest of face-dataset IMAGES and their caption
        # hashes; filing a video run under face dataset #N would put it in that
        # dataset's lineage graph forever. A video run stays unversioned rather
        # than borrowing a number that is not its.
        db.session.add(run)
        db.session.commit()
    try:
        ct._set(run, vast_label=f'lds-{run.id}',
                job_name=f'lds{run.id}_{run.run_name}')
        (_provision or _start_pod)(run)
    except Exception as e:
        ct._set(run, status='error', error=f'launch failed: {e}')
        raise
    logger.info('cloud video run %s launched: %s clips, %s steps, profile %s',
                run.id, clips, n_steps, ds.target_profile)
    return {'run_id': run.id, 'status': run.status, 'job_name': run.job_name,
            'steps': n_steps, 'clips': clips}
