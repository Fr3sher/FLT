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

from flask import Blueprint, jsonify, request

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
            'keep_audio': profile['keep_audio'],
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
