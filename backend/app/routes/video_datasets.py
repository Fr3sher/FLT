"""🎬 Video datasets API — the flat folders the trainers actually read.

A video dataset is a directory of `clip_0001.mp4` files with homonym `clip_0001.txt`
captions, and nothing else. No subfolder is ever created under it: ai-toolkit's
dataset scan is `os.walk` — recursive — and excludes only dotfiles and a directory
literally named `_controls`, so anything we wrote there for our own convenience
would be trained on without a word.

This blueprint also serves the TARGET CATALOGUE, because the frontend must not
hard-code it. Two of its fields are the difference between a good week and a
wasted one: `training_verified` (we know the model's geometry, but no trainer for
it is known to exist) and `licence_note` (MiniMax H3's licence grants no rights at
all in the EU, the UK, South Korea or the USA, and the restriction reaches the
OUTPUTS — a user must not discover that in a forum thread after building a set).
"""
import logging

from flask import Blueprint, jsonify, request, send_file

from ..config import LOCAL_USER
from ..services import video_bank_service as svc
from ..services import video_targets

logger = logging.getLogger(__name__)

bp = Blueprint('video_datasets', __name__, url_prefix='/api')


def _missing(dataset_id):
    return jsonify({'error': f'video dataset {dataset_id} not found'}), 404


@bp.get('/video/targets')
def video_targets_list():
    """The target catalogue, rendered for a picker. GET {'targets': [...]}.

    `default_seconds` is computed here rather than left to the client: "81 frames"
    means nothing to someone choosing clips out of a rush, and the intervals
    arithmetic ((frames-1)/fps, because N frames span N-1 intervals) is exactly the
    off-by-one that decides how much source a cut needs."""
    out = []
    for key in video_targets.PROFILE_KEYS:
        profile = video_targets.get(key)
        default_frames = profile['frame_default']
        out.append({
            'key': key,
            'label': profile['label'],
            'fps': profile['fps'],
            'frame_choices': list(profile['frame_choices']),
            'frame_default': default_frames,
            'default_seconds': (video_targets.clip_seconds(key, default_frames)
                                if default_frames else None),
            'size_multiple': profile['size_multiple'],
            'recommended_sizes': [list(s) for s in profile['recommended_sizes']],
            # Kept as a plain boolean because the picker only ever asks
            # "does this target want sound?"; `audio` carries the format
            # the exporter has to impose (32 kHz stereo for MiniMax H3).
            'keep_audio': profile['audio'] is not None,
            'audio': profile['audio'],
            'aitk_arch': profile['aitk_arch'],
            'max_pixels': profile['max_pixels'],
            'caption_style': profile['caption_style'],
            # Two vocabularies that must not be conflated: the app can know a
            # model's geometry perfectly and still have no way to train it.
            'training_verified': profile['training_verified'],
            'licence_note': profile['licence_note'],
        })
    return jsonify({'targets': out})


@bp.get('/video-datasets')
def video_datasets_list():
    """Every built video training set. GET {'datasets': [...]}"""
    return jsonify({'datasets': svc.list_video_datasets(LOCAL_USER)})


@bp.get('/video-dataset/<int:dataset_id>')
def video_dataset_get(dataset_id):
    """The dataset and its clips, each carrying the source file and the bounds it
    was cut at — so a later re-export to another target is a re-encode from the
    original rather than a re-scan from scratch."""
    payload = svc.video_dataset_payload(LOCAL_USER, dataset_id)
    if payload is None:
        return _missing(dataset_id)
    return jsonify(payload)


@bp.get('/video-dataset/<int:dataset_id>/clip/<int:clip_id>/media')
def video_dataset_clip_media(dataset_id, clip_id):
    """One promoted clip's bytes. A dataset you cannot re-watch is a list of
    filenames, and watching a cut IS how you find out the length was wrong before
    paying for a training run.

    ``conditional=True`` for the same reason as the bank's source route (Range),
    though these files are a few megabytes rather than a rush.

    Cached for a DAY, not a year, and the difference is not caution: SQLite reuses
    rowids after a delete unless the column is AUTOINCREMENT, so
    /video-dataset/7/clip/12/media can legitimately become a different clip. A day
    covers a working session without pinning a stale clip to that URL forever."""
    path = svc.dataset_clip_media_path(LOCAL_USER, dataset_id, clip_id)
    if path is None:
        return jsonify({'error': 'clip file not available'}), 404
    return send_file(path, mimetype='video/mp4', conditional=True, max_age=86400)


@bp.post('/video-dataset/<int:dataset_id>/clip/<int:clip_id>/caption')
def video_dataset_caption(dataset_id, clip_id):
    """Body {caption}. Writes the row AND rewrites the .txt sidecar.

    The disk write is the feature, not the bookkeeping: the trainer never reads
    our database, it reads the file next to the .mp4. A caption saved to one and
    not the other trains the dataset on the previous text while the interface
    shows the new one, with nothing anywhere to reveal it.

    An empty caption empties the file; it never deletes it. A MISSING sidecar
    crashes musubi-tuner (FileNotFoundError out of a worker future, no handler on
    the path) and makes diffusion-pipe drop the clip in silence."""
    data = request.get_json(silent=True) or {}
    out = svc.set_dataset_clip_caption(LOCAL_USER, dataset_id, clip_id,
                                       data.get('caption'))
    if out is None:
        return _missing(dataset_id)
    return jsonify(out)


@bp.delete('/video-dataset/<int:dataset_id>')
def video_dataset_delete(dataset_id):
    """Throw away a badly cut dataset — the ENCODE, never the triage.

    The bank's clips survive untouched; they only stop claiming to have been
    promoted, so the user can re-cut at a different length without re-triaging."""
    if not svc.delete_video_dataset(LOCAL_USER, dataset_id):
        return _missing(dataset_id)
    return jsonify({'ok': True})


@bp.post('/video-dataset/<int:dataset_id>/train')
def video_dataset_train_local(dataset_id):
    """Train a LoRA on this video dataset with the ai-toolkit installed here.

    Its own endpoint, and not the face lane's `/dataset/<id>/train`, for the same
    reason the cloud one is separate: that route's id means a `face_dataset`, and
    the two tables share one integer space.

    Three refusals get their own status because the UI has to say three different
    things: an uncatalogued or unsupported target is a 400 (a choice the user can
    change), no ai-toolkit and a card already taken are 409s (the request is fine,
    the machine is not), and absent weights are a 409 carrying the repository and
    the size so the panel can ask for a yes instead of just saying no."""
    from ..services import video_training
    from ..services import video_training_local as vtl
    from ..gpu_window import GpuBusyError
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(vtl.start_video_training(
            LOCAL_USER, dataset_id,
            steps=body.get('steps') or 1000,
            base_model=(body.get('base_model') or '').strip() or None,
            low_vram=bool(body.get('low_vram', True)),
            accept_download=bool(body.get('accept_download', False))))
    except vtl.VideoWeightsMissing as e:
        return jsonify({'error': str(e), 'needs_download': True,
                        'repo': e.repo, 'gigabytes': e.gigabytes}), 409
    except video_training.VideoTrainingUnsupported as e:
        return jsonify({'error': str(e)}), 400
    except GpuBusyError as e:
        return jsonify({'error': str(e)}), 409
    except ValueError as e:
        if 'not found' in str(e):
            return _missing(dataset_id)
        # 'a training is already in progress' is a state refusal, not a malformed
        # request — the same 409 the face lane's launch route returns for it.
        if 'in progress' in str(e):
            return jsonify({'error': str(e)}), 409
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 409


@bp.get('/video-dataset/<int:dataset_id>/train/progress')
def video_dataset_train_progress(dataset_id):
    """The local run's live progress, for the card to poll.

    Reports `active` only for a run whose fence names THIS dataset AND the video
    table — a face training of the colliding id must not drive this bar."""
    from ..services import video_training_local as vtl
    try:
        progress = vtl.video_training_progress(dataset_id, LOCAL_USER)
    except ValueError:
        return _missing(dataset_id)
    progress['checkpoints'] = vtl.list_run_checkpoints(dataset_id, LOCAL_USER)
    return jsonify(progress)


@bp.post('/video-dataset/<int:dataset_id>/train/stop')
def video_dataset_train_stop(dataset_id):
    """Stop the local run of THIS video dataset.

    Names the table alongside the id, which is what stops this button from
    killing the face dataset of the same number. `ok: false` is the honest answer
    when the fence names another run — the click was refused, not silently
    ignored."""
    from ..services import cloud_run_dataset as crd
    from ..services import lora_training as lt
    stopped = lt.stop_training(expected_dataset_id=dataset_id,
                               expected_dataset_table=crd.VIDEO)
    return jsonify({'ok': bool(stopped)})


@bp.post('/video-dataset/<int:dataset_id>/train/cloud')
def video_dataset_train_cloud(dataset_id):
    """Rent a pod and train a LoRA on this video dataset.

    Deliberately its own endpoint rather than the face lane's
    `/dataset/<id>/train/cloud`: that route's id means a `face_dataset`, and the
    two tables share one integer space — the same URL shape for both would make
    the id alone ambiguous at the outermost layer, which is precisely the
    confusion the run's `dataset_table` column exists to end.

    A target we have no verified base for is a 400, not a 500: the user picked a
    model this build cannot train unattended, and that is a choice they can
    correct — the message names what to do."""
    from ..services import cloud_video_training as cvt
    from ..services import video_training
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(cvt.launch_cloud_video_training(
            LOCAL_USER, dataset_id,
            steps=body.get('steps') or 1000,
            base_model=(body.get('base_model') or '').strip() or None,
            low_vram=bool(body.get('low_vram', False)),
            gpu_name=body.get('gpu_name')))
    except video_training.VideoTrainingUnsupported as e:
        return jsonify({'error': str(e)}), 400
    except ValueError as e:
        # 'video dataset not found' is the only ValueError that is a 404; the
        # rest ('no clips on disk') are things about THIS dataset the user can
        # act on, and a 404 would tell them the dataset does not exist.
        if 'not found' in str(e):
            return _missing(dataset_id)
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        # The launch guard: already running, fleet limit, budget. 409 — the
        # request was well-formed, the state refuses it.
        return jsonify({'error': str(e)}), 409


@bp.get('/video-dataset/<int:dataset_id>/train/cloud/progress')
def video_dataset_train_cloud_progress(dataset_id):
    """The newest cloud run OF THIS VIDEO DATASET, for the page to poll.

    Scoped to the video table explicitly. Resolved by integer alone it would
    return the face dataset of the same id's run — the same phase, cost and
    progress bar, for a training the user is not watching."""
    from ..services import cloud_run_dataset as crd
    from ..services import cloud_training as ct
    run = ct.latest_run_for(dataset_id, dataset_table=crd.VIDEO)
    if run is None:
        return jsonify({'run_id': None, 'status': None})
    return jsonify({
        'run_id': run.id, 'status': run.status,
        'phase_detail': run.phase_detail or '',
        'gpu': run.gpu_name, 'price_per_hour': run.price_per_hour,
        'error': run.error,
        'steps': ct._run_param(run, 'steps'),
        'saves': len(ct.run_checkpoint_files(run)),
        'created_at': run.created_at.isoformat() if run.created_at else None,
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
    })
