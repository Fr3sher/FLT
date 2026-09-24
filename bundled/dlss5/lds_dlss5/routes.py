"""Standalone DLSS studio and owned settings."""
import io
import os
from flask import Blueprint, current_app, jsonify, request, send_file
from lds_sdk.lifecycle import state_change_lock
from . import jobs, neural_render as nr, runtime

bp = Blueprint('dlss5', __name__)


@bp.errorhandler(nr.NeuralRenderError)
def refusal(error):
    return jsonify(error=str(error)), 400


@bp.get('/status')
def status():
    return jsonify(status=nr.status(), environment=runtime.context().plugin_environment())


@bp.route('/settings', methods=['GET', 'POST'])
def settings():
    with state_change_lock:
        ctx = runtime.context()
        if request.method == 'POST':
            data = request.get_json(silent=True)
            if not isinstance(data, dict) or set(data) != {'python'} or not isinstance(data['python'], str):
                return jsonify(error='Expected a Python interpreter path.'), 400
            selected = data['python'].strip().strip('"')
            if len(selected) > 2048 or any(ord(char) < 32 for char in selected):
                return jsonify(error='Choose a valid Python interpreter path.'), 400
            if jobs.busy() or runtime.running():
                return jsonify(error='Let the DLSS render finish before changing its interpreter.'), 409
            ctx.config.update_own({'python': selected, 'python_migrated': True})
            runtime._CACHE.clear()
        return jsonify(python=ctx.config.own('python') or '',
                       environment=ctx.plugin_environment())


@bp.get('/clips')
def clips():
    return jsonify(clips=jobs.listing())


@bp.post('/clips')
def upload():
    file = request.files.get('file')
    if file is None:
        return jsonify(error='Choose a video file.'), 400
    return jsonify(clip=jobs.imported(file)), 201


@bp.get('/clips/<ident>')
def clip(ident):
    return jsonify(clip=jobs.read(ident))


@bp.post('/clips/<ident>/open-folder')
def open_folder(ident):
    # Resolve only an existing clip's owned directory, never a client-supplied path.
    jobs.read(ident)
    directory = jobs.folder(ident)
    try:
        os.startfile(str(directory))
    except (AttributeError, OSError):
        return jsonify(error='Could not open the video folder on the computer running LDS.'), 500
    return jsonify(ok=True)


@bp.post('/clips/<ident>/render')
def render(ident):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='Expected render settings.'), 400
    return jsonify(clip=jobs.start(current_app._get_current_object(), ident, data)), 202


@bp.post('/clips/<ident>/cancel')
def cancel(ident):
    return jsonify(cancelled=jobs.cancel(ident))


@bp.get('/clips/<ident>/media/<kind>')
def media(ident, kind):
    if kind not in ('original', 'result'):
        return jsonify(error='Unknown clip media.'), 404
    path = jobs.media_path(ident, result=kind == 'result')
    return send_file(path, conditional=True, max_age=0,
                     as_attachment=request.args.get('download') == '1',
                     download_name=f'{ident}-{kind}{path.suffix}')


@bp.get('/clips/<ident>/comparison')
def comparison(ident):
    try:
        data = nr.build_comparison(jobs.media_path(ident), jobs.media_path(ident, result=True),
                                   left_label='Original', right_label='DLSS 5')
        return send_file(io.BytesIO(data), mimetype='video/mp4', as_attachment=True,
                         download_name=f'{ident}-comparison.mp4', max_age=0)
    except nr.ComparisonBusyError as exc:
        return jsonify(error=str(exc)), 429
    except nr.ComparisonTooLargeError as exc:
        return jsonify(error=str(exc)), 413
