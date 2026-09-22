"""Canvas-owned routes; historical paths remain stable across installation."""
from flask import Blueprint, jsonify, request, g
from lds_sdk import config as cfg
from lds_sdk import canvas as host
from lds_sdk.http import map_error as _map_error
from lds_sdk.lifecycle import is_available, state_change_lock
from . import canvas_state as cs

LOCAL_USER = cfg.local_user()
bp = Blueprint('canvas', __name__)

@bp.before_request
def _admit_canvas():
    lock = state_change_lock
    lock.acquire()
    g.canvas_admission_lock = lock
    # Pending disable must close existing browser tabs before any read or write.
    if not is_available('canvas'):
        return jsonify({'error': 'Canvas is disabled. Enable it and restart the app.',
                        'plugin': 'canvas'}), 409
    if request.is_json and not isinstance(request.get_json(silent=True), dict):
        return jsonify({'error': 'Expected a JSON object.'}), 400

@bp.teardown_request
def _release_admission(_error):
    lock = g.pop('canvas_admission_lock', None)
    if lock is not None:
        lock.release()

@bp.get('/train/canvas/datasets')
def train_canvas_datasets():
    """◉ LoRA Canvas index: which datasets have runs worth drawing, how many, and
    in which families. Cheap by design (no checkpoints, no disk) — the canvas
    fetches each selected dataset's genealogy separately, so the board and its
    filter appear immediately instead of after a full-library disk scan."""
    return jsonify(host.history_dataset_index(LOCAL_USER))


@bp.post('/train/canvas/generate')
def train_canvas_generate():
    """◉ Generate from the LoRA Canvas — the same Test-Studio engine, driven by
    the checkpoints ticked on the board instead of by a picker. Body:
    {selections:[{dataset_id, checkpoint, record_id, step}], external_loras,
    …every Studio setting}. Selections MAY span several datasets (that is the
    point of the canvas); they may NOT span several families — the engine
    refuses, and the reason travels back so the button can say it. Same gates
    as the other launch routes: ComfyUI not set up → 409/503, missing
    models/nodes → the actionable 409 the Studio already returns.

    🧬 `combine: true` (the board's Blend toggle) switches from one pass per
    ticked checkpoint to ONE generation loading them all, each at the `weight`
    its selection carries, with every dataset's trigger word injected. It is the
    Test Studio's own Blend mode — the same engine argument, so the two screens
    cannot drift into two answers for one word."""
    from lds_sdk.canvas import (require_comfyui as _require_comfyui,
                                studio_arch_mismatch_response as _studio_arch_mismatch_response,
                                studio_missing_response as _studio_missing_response)
    gate = _require_comfyui()
    if gate:
        return gate
    d = request.get_json(silent=True) or {}
    try:
        from lds_sdk.canvas import StudioGenSettings
        res = host.generate_checkpoint_comparison(
            LOCAL_USER, d.get('selections') or [],
            d.get('strengths') or [1.0],
            # Shared settings use the Studio's wire keys; 📝 batches run once
            # per selected prompt. ◉ The base model is an AXIS (z_models).
            StudioGenSettings.from_payload(d),
            prompts=d.get('prompts'),
            external_loras=d.get('external_loras'), combine=d.get('combine'))
    except Exception as e:
        from lds_sdk.canvas import StudioArchMismatch, StudioAssetsMissing
        if isinstance(e, StudioArchMismatch):
            return _studio_arch_mismatch_response(e)
        if isinstance(e, StudioAssetsMissing):
            return _studio_missing_response(e)
        return _map_error(e)
    return jsonify({'ok': True, **{k: res[k]
                                   for k in ('created', 'seed', 'count', 'run_id')}})


@bp.get('/train/canvas/positions')
def train_canvas_positions():
    """◉ LoRA Canvas: every remembered card position, grouped by dataset id.
    One request for the whole board — the lanes need their overrides before the
    first paint, and N round-trips for a few dozen tiny rows would cost more
    than the genealogy fetches they precede."""
    return jsonify(cs.canvas_positions(LOCAL_USER))


@bp.put('/dataset/<int:dataset_id>/canvas/positions')
def dataset_canvas_positions_save(dataset_id):
    """Remember where cards sit in ONE lane. Body: {positions:[{record_id,x,y}]}.
    Upsert, so re-sending the same coordinates is a no-op — the canvas re-pins a
    lane whenever it gains a run."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(cs.save_canvas_positions(
            LOCAL_USER, dataset_id, data.get('positions')))
    except LookupError:
        return jsonify({'error': 'not found'}), 404


@bp.delete('/dataset/<int:dataset_id>/canvas/positions')
def dataset_canvas_positions_clear(dataset_id):
    """✦ Tidy up one lane: forget every dragged position and fall back to the
    automatic tree."""
    try:
        return jsonify(cs.clear_canvas_positions(LOCAL_USER, dataset_id))
    except LookupError:
        return jsonify({'error': 'not found'}), 404


@bp.get('/train/canvas/lanes')
def train_canvas_lanes():
    """◉ LoRA Canvas: every arranged LANE — where it sits and how much room it
    keeps. Travels with the card positions above and for the same reason: the
    board must know before its first paint, or it lays itself out twice."""
    return jsonify(cs.canvas_lane_placements(LOCAL_USER))


@bp.put('/dataset/<int:dataset_id>/canvas/lane')
def dataset_canvas_lane_save(dataset_id):
    """Remember one lane's placement. Body: {x?, y?, h?}.
    A MERGE — the client sends only what its gesture changed, so moving a lane
    keeps the height it was given and resizing it keeps where it was put."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(cs.save_canvas_lane_placement(LOCAL_USER, dataset_id, data))
    except LookupError:
        return jsonify({'error': 'not found'}), 404


@bp.delete('/dataset/<int:dataset_id>/canvas/lane')
def dataset_canvas_lane_clear(dataset_id):
    """✦ Tidy up one lane: back to the automatic stack."""
    try:
        return jsonify(cs.clear_canvas_lane_placement(LOCAL_USER, dataset_id))
    except LookupError:
        return jsonify({'error': 'not found'}), 404


@bp.get('/train/canvas/external-loras')
def canvas_external_loras_get():
    """🔌 The board's external LoRA plugin nodes, as persisted."""
    return jsonify({'loras': cfg.get('canvas.external_loras', []) or []})


@bp.put('/train/canvas/external-loras')
def canvas_external_loras_put():
    """Replace the board's external LoRA nodes. Sanitizes: dedupe by filename,
    reject path-traversal/absolute/drive-letter names (dropped, not erred —
    this is a save-what-survives sanitizer, same spirit as the sibling
    `save_canvas_positions`), cap 16, strength clamped [0..2] (default 1.0),
    x/y coerced to floats."""
    from lds_sdk.video_host.studio import is_unsafe_external_lora_name as _is_unsafe_external_lora_name
    data = request.get_json(silent=True) or {}
    raw = data.get('loras')
    cleaned, seen = [], set()
    for e in (raw if isinstance(raw, list) else []):
        if not isinstance(e, dict):
            continue
        fn = str(e.get('filename') or '').strip()
        if not fn or fn in seen or _is_unsafe_external_lora_name(fn):
            continue
        seen.add(fn)
        try:
            st = max(0.0, min(2.0, round(float(e.get('strength', 1.0)), 2)))
        except (TypeError, ValueError):
            st = 1.0

        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0
        cleaned.append({'filename': fn, 'strength': st,
                        'x': _f(e.get('x')), 'y': _f(e.get('y'))})
        if len(cleaned) >= 16:
            break
    host.save_external_loras(cleaned)
    return jsonify({'ok': True, 'loras': cleaned})


@bp.get('/train/canvas/images')
def train_canvas_images():
    """🖼 Every image pinned on the ◉ LoRA Canvas, grouped by dataset id, with
    the image row alongside its geometry — one request for the whole board, like
    the card positions it sits next to. Rows whose image is gone are pruned
    server-side rather than answered."""
    return jsonify(cs.canvas_image_nodes(LOCAL_USER))


@bp.put('/dataset/<int:dataset_id>/canvas/images')
def dataset_canvas_images_save(dataset_id):
    """Remember pinned images of ONE lane.
    Body: {nodes:[{image_id,x,y,w,h,visible}]}.

    Closing a pinned image is this call with ``visible: false`` — the geometry
    stays, so re-opening puts the picture back exactly where and at the size it
    was closed at."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(cs.save_canvas_image_nodes(
            LOCAL_USER, dataset_id, data.get('nodes')))
    except LookupError:
        return jsonify({'error': 'not found'}), 404


@bp.delete('/dataset/<int:dataset_id>/canvas/images')
def dataset_canvas_images_clear(dataset_id):
    """Forget every pinned image of one lane, geometry included. Deliberately
    NOT what ✦ Tidy up calls — see clear_canvas_image_nodes."""
    try:
        return jsonify(cs.clear_canvas_image_nodes(LOCAL_USER, dataset_id))
    except LookupError:
        return jsonify({'error': 'not found'}), 404


@bp.get('/train/canvas/layouts')
def train_canvas_layouts():
    """💾 The named board arrangements this install has kept."""
    return jsonify(cs.canvas_layout_presets(LOCAL_USER))


@bp.post('/train/canvas/layouts')
def train_canvas_layouts_save():
    """Keep the board's current arrangement under a name.
    Body: {name, positions:{ds:[{record_id,x,y}]}, images:{ds:[{image_id,...}]},
    lanes:{ds:{x?,y?,h?}}}.

    Saving under an existing name overwrites it — "save" on a board you have
    just adjusted means "this is the arrangement now"."""
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(cs.save_canvas_layout_preset(
            LOCAL_USER, data.get('name'),
            positions=data.get('positions'), images=data.get('images'),
            lanes=data.get('lanes')))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@bp.post('/train/canvas/layouts/<int:preset_id>/apply')
def train_canvas_layouts_apply(preset_id):
    """Put a remembered arrangement back. Everything travels through the live
    writers, so anything that no longer exists is simply not restored."""
    try:
        return jsonify(cs.apply_canvas_layout_preset(LOCAL_USER, preset_id))
    except LookupError:
        return jsonify({'error': 'not found'}), 404


@bp.delete('/train/canvas/layouts/<int:preset_id>')
def train_canvas_layouts_delete(preset_id):
    try:
        return jsonify(cs.delete_canvas_layout_preset(LOCAL_USER, preset_id))
    except LookupError:
        return jsonify({'error': 'not found'}), 404
