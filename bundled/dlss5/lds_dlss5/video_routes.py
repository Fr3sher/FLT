"""Optional Video integration routes, owned and admitted by DLSS 5."""
import io
import os
from flask import Blueprint, current_app, jsonify, request, send_file
from lds_sdk import video_media as media, config
from lds_sdk.video_host import bank_jobs
from . import neural_render as nr
bp = Blueprint('dlss5_video', __name__)
LOCAL_USER = config.local_user()

@bp.before_request
def require_video():
    if not media.available():
        return jsonify(error='Enable Video to use its datasets and Studio integration.'), 409

def _missing(dataset_id):
    return jsonify(error='Video dataset not found.'), 404

# ── ✨ Neural render (DLSS 5) — in place, original kept ──────────────────────

@bp.get('/video-dataset/<int:dataset_id>/neural-render')
def video_dataset_neural_render_state(dataset_id):
    """What the ✨ button needs before it is pressed and while it runs: the
    capability's own sentences (``ready`` + ``missing``), the job snapshot of
    the pass on THIS dataset (None when idle), and which clips currently play
    a render — derived from the backup folder, which is the only state there
    is. Polled only while a pass runs; the workspace's own 2 s poll never
    carries this."""
    if not media.dataset_exists(LOCAL_USER, dataset_id):
        return _missing(dataset_id)
    return jsonify({'ok': True, 'status': nr.status(),
                    'job': media.dataset_job(dataset_id),
                    'rendered_ids': media.rendered_clip_ids(LOCAL_USER, dataset_id),
                    # {clip id: the dials that made its render}, for the lightbox.
                    'rendered_params': media.rendered_clip_params(LOCAL_USER, dataset_id)})


@bp.post('/video-dataset/<int:dataset_id>/neural-render')
def video_dataset_neural_render_start(dataset_id):
    """Body {ids: [...] (empty = every clip), tone, structure, automask,
    temporal, scene_cut}. Renders the clips IN PLACE — the folder is the
    dataset, so the render must be the file the trainer reads — after copying
    each original, once, to the backup folder outside the dataset. One job per
    dataset (409 while one runs, like every bank pass); progress is read from
    the GET above."""
    from flask import current_app
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list):
        return jsonify({'error': 'ids must be a list of clip ids'}), 400
    try:
        out = media.start_dataset_render(current_app._get_current_object(), LOCAL_USER,
                                      dataset_id, ids, data)
    except nr.NeuralRenderError as exc:
        return jsonify({'error': str(exc)}), 400
    except bank_jobs.BankJobBusy:
        return jsonify({'error': 'a pass is already running on this dataset'}), 409
    return jsonify({'ok': True, **out})


@bp.post('/video-dataset/<int:dataset_id>/neural-render/cancel')
def video_dataset_neural_render_cancel(dataset_id):
    """Stop the running pass: the clip being rendered keeps its original (the
    replacement is a single ``os.replace`` at the very end), the ones already
    done stay rendered."""
    if not media.dataset_exists(LOCAL_USER, dataset_id):
        return _missing(dataset_id)
    return jsonify({'ok': True, 'cancelled': media.cancel_dataset_job(dataset_id)})


@bp.get('/video-dataset/<int:dataset_id>/clip/<int:clip_id>/original')
def video_dataset_clip_original(dataset_id, clip_id):
    """The ORIGINAL bytes of a neural-rendered clip, for the side-by-side
    player: the clip's own media route now serves the render, this serves
    what it replaced. Range-capable like the media route (the player seeks).
    404 when the clip plays no render — there is nothing to compare with."""
    path = media.original_clip_path(LOCAL_USER, dataset_id, clip_id)
    if path is None:
        return jsonify({'error': 'this clip plays no render — no original to show'}), 404
    return send_file(path, mimetype='video/mp4', conditional=True, max_age=0)


@bp.get('/video-dataset/<int:dataset_id>/clip/<int:clip_id>/comparison')
def video_dataset_clip_comparison(dataset_id, clip_id):
    """⬇ The two clips as ONE mp4, side by side — the picture the ⇔ player
    shows, in a file that can leave the app.

    Same 404 as the original route and for the same reason: without a render
    there are not two things to put next to each other."""
    original = media.original_clip_path(LOCAL_USER, dataset_id, clip_id)
    render = media.dataset_clip_media_path(LOCAL_USER, dataset_id, clip_id)
    if original is None or render is None:
        return jsonify({'error': 'this clip plays no render — nothing to compare'}), 404
    try:
        data = nr.build_comparison(original, render, left_label='Original',
                                   right_label='Neural render (DLSS 5)')
    except nr.ComparisonBusyError as exc:
        # One encode at a time, and the second caller is told to come back —
        # the same answer the timeline GIF gives, for the same reason.
        res = jsonify({'error': str(exc)})
        res.headers['Retry-After'] = '5'
        return res, 429
    except nr.ComparisonTooLargeError as exc:
        return jsonify({'error': str(exc)}), 413
    except nr.NeuralRenderError as exc:
        return jsonify({'error': str(exc)}), 400
    stem = os.path.splitext(os.path.basename(render))[0]
    return send_file(io.BytesIO(data), mimetype='video/mp4', as_attachment=True,
                     download_name=f'{stem}-vs-neural.mp4', max_age=0)


@bp.post('/video-dataset/<int:dataset_id>/neural-render/restore')
def video_dataset_neural_render_restore(dataset_id):
    """🩹 Body {ids: [...] (empty = every rendered clip)}. Moves each original
    back over its render; a restored clip has no backup left and therefore
    reports as not rendered — the file and the fact cannot disagree."""
    data = request.get_json(silent=True) or {}
    ids = data.get('ids') or []
    if not isinstance(ids, list):
        return jsonify({'error': 'ids must be a list of clip ids'}), 400
    try:
        out = media.restore_dataset_clips(LOCAL_USER, dataset_id, ids)
    except nr.NeuralRenderError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'ok': True, **out})



@bp.post('/video-studio/clip/<int:clip_id>/neural-render')
def studio_render(clip_id):
    try:
        result = media.start_studio_render(current_app._get_current_object(), LOCAL_USER,
                                            clip_id, request.get_json(silent=True) or {})
        return jsonify(ok=True, **result)
    except nr.NeuralRenderError as exc:
        return jsonify(error=str(exc)), 400

@bp.get('/video-studio/clip/<int:clip_id>/comparison')
def studio_comparison(clip_id):
    try:
        left, right = media.studio_comparison_paths(LOCAL_USER, clip_id)
        data = nr.build_comparison(left, right, left_label='Original', right_label='DLSS 5')
        return send_file(io.BytesIO(data), mimetype='video/mp4', as_attachment=True,
                         download_name=f'clip-{clip_id}-comparison.mp4', max_age=0)
    except FileNotFoundError as exc:
        return jsonify(error=str(exc)), 404
    except nr.ComparisonBusyError as exc:
        return jsonify(error=str(exc)), 429
    except nr.ComparisonTooLargeError as exc:
        return jsonify(error=str(exc)), 413
    except nr.NeuralRenderError as exc:
        return jsonify(error=str(exc)), 400
