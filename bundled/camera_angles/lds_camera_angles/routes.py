"""The three routes of the lane, at the URLs the screens already call —
registered under ``/api`` by the plugin's ``register``."""
import os

from flask import Blueprint, jsonify, request

from lds_sdk import config as cfg, setup as setup_installer
from lds_sdk.http import map_error as _map_error, require_idle_comfy as _require_no_stalled_comfyui

from . import camera_angles as ca
from . import qwen_camera_helper as qch
from . import views

bp = Blueprint('camera_angles', __name__)


def _camera_missing_response(e):
    """Turn a CameraModelsMissing into a structured 409 that INSTALLS.

    Same contract as the Klein and Krea misses: pressing 📷 with the weights
    absent IS the request to fetch them, so the answer starts the downloads and
    then says what is being fetched — rather than listing four manual gestures
    at someone who just wanted a picture. The manual path survives in the
    message when nothing could be started (no valid ComfyUI folder, a disk
    precondition), because a machine that cannot download is still owed an
    answer.

    The size is stated on purpose. This lane's model is 20 GB — by far the
    largest thing the app has ever offered to fetch on a button press — and a
    download that big must never begin as a surprise."""
    missing = list(getattr(e, 'missing', []) or [])
    dir_valid = setup_installer.resolve_install_folder(cfg.get('comfyui.base_dir') or '')['valid']
    started = []
    if dir_valid:
        for action in missing:
            if not setup_installer.known_action(action):
                continue
            try:
                setup_installer.start(action)
                started.append(action)
            except setup_installer.AlreadyRunning:
                started.append(action)     # in flight still counts as installing
            except Exception:
                pass                       # disk precondition — the text says what to do
    parts = ["Camera angles can't run yet."]
    if not dir_valid:
        parts.append('Point the app at your ComfyUI install folder in Setup ▸ ComfyUI '
                     'and it can install all of this for you.')
    if started:
        gb = sum((setup_installer.model_download_spec(a) or {}).get('min_free_gb', 0)
                 for a in started)
        parts.append('I\'ve started downloading the camera-angle weights into your '
                     f'ComfyUI folder (about {gb} GB of free space needed) — watch '
                     'progress in Setup ▸ ComfyUI.')
    else:
        for action in missing:
            spec = setup_installer.model_download_spec(action)
            if spec:
                parts.append('Missing ' + os.path.join(*spec['dest'])
                             + f" — get it from {spec.get('license_url') or spec['url']}.")
    parts.append('Then press 📷 again.')
    return jsonify({'ok': False, 'error': ' '.join(parts),
                    'camera_missing': missing, 'downloading': started,
                    'camera_required': list(qch.CAMERA_REQUIRED)}), 409


@bp.post('/canvas/image/<int:image_id>/camera')
def canvas_image_camera_angles(image_id):
    """📷 Re-shoot ONE library picture from other CAMERA positions.

    Body: `{poses: ['right/low/medium', …]}` — stable pose ids from
    camera_angles. Answers `{ok, views: [{candidate_id, job_id, pose,
    label}], queued}`.

    Its own route for the same reason ✨ improve has one: `image_id` is a
    `lora_test_image.id`, and the dataset route's id space is a different table.

    WHY THIS IS NOT A VARIATION. The shot catalog can already ask for "profile
    left" — and an edit model answers it by turning the PERSON while the room
    stays put. This lane moves the camera and the backdrop reprojects with it.
    The two produce different pictures from the same sentence, which is why they
    are different verbs rather than one with a checkbox.
    """
    gate = _require_no_stalled_comfyui()
    if gate:
        return gate
    data = request.get_json(silent=True) or {}
    try:
        result = views.camera_views_for_canvas_image(cfg.local_user(), image_id, data.get('poses'))
    except Exception as e:
        if isinstance(e, qch.CameraModelsMissing):
            return _camera_missing_response(e)
        return _map_error(e)
    if result is None:
        return jsonify({'error': ca.SOURCE_GONE}), 404
    return jsonify({'ok': True, **result})


@bp.post('/dataset/image/<int:image_id>/camera')
def dataset_image_camera_angles(image_id):
    """📷 Re-shoot ONE dataset image from other camera positions.

    The dataset twin of the canvas route — its own route because `image_id`
    here is a `face_dataset_image.id` and the two tables have independent id
    spaces (the same reason ✨ improve keeps two routes). Same body, same
    answers, same installing 409. Results arrive as PENDING dataset candidates
    in the ordinary keep/reject cycle, each born with its angle phrase as the
    caption seed."""
    gate = _require_no_stalled_comfyui()
    if gate:
        return gate
    data = request.get_json(silent=True) or {}
    try:
        result = views.camera_views_for_dataset_image(cfg.local_user(), image_id, data.get('poses'))
    except Exception as e:
        if isinstance(e, qch.CameraModelsMissing):
            return _camera_missing_response(e)
        return _map_error(e)
    if result is None:
        return jsonify({'error': ca.SOURCE_GONE}), 404
    return jsonify({'ok': True, **result})


@bp.get('/camera/catalog')
def camera_catalog():
    """The camera vocabulary the picker draws, plus whether the lane can run.

    Served rather than duplicated so the dial's degrees and the model's tokens
    come from ONE table; `cameraCatalogContract.test.js` reads both sides.

    `unet` is the picker's Model row in one read: `setting` is the saved
    `camera.unet` pin ('' = auto), `effective` the file the next run would
    actually load (None while nothing is installed), `default` the name of the
    Setup-installed build — so the row can SAY what "empty" means instead of
    calling it auto-detect — and `distilled` whether that effective build's
    name reads as an already-few-step merge, in which case runs skip the
    chained speed LoRA (the note under the row is where the user learns that
    BEFORE wondering why their run behaved differently)."""
    missing = qch.camera_missing_assets()
    effective = qch.resolve_camera_unet()
    return jsonify({**ca.catalog(),
                    'ready': qch.camera_ready(missing),
                    'missing': missing,
                    'unet': {'setting': (cfg.get('camera.unet') or '').strip(),
                             'effective': effective,
                             'default': qch.camera_default_unet(),
                             'distilled': qch.unet_is_distilled(effective)}})
