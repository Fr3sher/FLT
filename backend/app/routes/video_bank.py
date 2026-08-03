"""🎬 Video bank API — triage a folder of rushes before it becomes a training set.

Deliberately the same surface as the 🗃️ image bank: heavy passes return 202 and
run in ONE background thread per bank, the UI polls GET /video-bank/<id> whose
payload embeds the live job, and 409 means a pass already owns this bank. A user
does not know there are two services behind the app and should not be able to
tell — so the status codes, the `busy_kind` field and the payload shape are
copied rather than reinvented.

The one place the two lanes differ is promotion, and it differs because of the
architecture rather than the API: promoting is where the video lane finally
ENCODES something, so it takes a target profile and a clip length, and everything
that could be refused is refused synchronously before a dataset exists.
"""
import logging
import os

from flask import Blueprint, current_app, jsonify, request, send_file

from ..config import LOCAL_USER
from ..services import bank_jobs
from ..services import video_bank_service as svc

logger = logging.getLogger(__name__)

bp = Blueprint('video_bank', __name__, url_prefix='/api')


def _app():
    return current_app._get_current_object()


def _busy(e):
    """The ONE shape of a "this bank is occupied" refusal, identical to the image
    lane's: `error` stays an English sentence for anything that only knows how to
    print a message, and `busy_kind` names the pass so the UI can refuse the click
    in the user's own vocabulary."""
    return jsonify({'error': str(e), 'busy_kind': e.kind}), 409


def _missing(bank_id):
    """404, not 400. "Bank not found" is not something the user can fix by editing
    the body — it means the bank was deleted in another tab."""
    return jsonify({'error': f'video bank {bank_id} not found'}), 404


def _start(bank_id, fn, *args, **kwargs):
    """Start-a-pass envelope: 404 unknown, 409 busy, 400 bad input, 503 missing
    tool, 202 on launch."""
    if svc.get_bank(LOCAL_USER, bank_id) is None:
        return _missing(bank_id)
    try:
        fn(*args, **kwargs)
    except bank_jobs.BankJobBusy as e:
        return _busy(e)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    return jsonify({'ok': True}), 202


# --- banks ---------------------------------------------------------------------

@bp.get('/video-banks')
def video_banks_list():
    """Every video bank with its counters. GET {'banks': [...]}"""
    return jsonify({'banks': svc.list_banks(LOCAL_USER)})


@bp.post('/video-bank/create')
def video_bank_create():
    """Body {name, folder}. Instant — no decode, no detection: those are passes.
    200 {'ok', 'id', 'added'}; 400 on a folder that is missing, unreadable, or
    that would make a bank share bytes with a dataset."""
    data = request.get_json(silent=True) or {}
    try:
        bank, added = svc.create_bank(LOCAL_USER, data.get('name'),
                                      data.get('folder'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'id': bank.id, 'added': added})


@bp.get('/video-bank/<int:bank_id>')
def video_bank_get(bank_id):
    """The workspace payload AND the 2 s job poll. ?refresh=1 re-walks the source
    folder first (the workspace sends it when the bank is opened), because a bank
    points at a LIVE folder people keep dropping files into."""
    sync = None
    if request.args.get('refresh') == '1':
        sync = svc.refresh_bank(LOCAL_USER, bank_id, force=True)
    payload = svc.bank_payload(LOCAL_USER, bank_id)
    if payload is None:
        return _missing(bank_id)
    payload['folder_sync'] = sync
    return jsonify(payload)


@bp.delete('/video-bank/<int:bank_id>')
def video_bank_delete(bank_id):
    """Drops the bank, its sources, its clips and its thumbnails. Never the
    datasets built out of it — that provenance is deliberately not a foreign key."""
    if not svc.delete_bank(LOCAL_USER, bank_id):
        return _missing(bank_id)
    return jsonify({'ok': True})


@bp.post('/video-bank/<int:bank_id>/refresh')
def video_bank_refresh(bank_id):
    """Re-inventory the folder on demand. Strictly additive; vanished files are
    counted, never removed. 200 {'ok', 'added', 'missing', 'unavailable', 'error'}."""
    sync = svc.refresh_bank(LOCAL_USER, bank_id, force=True)
    if sync is None:
        return _missing(bank_id)
    return jsonify({'ok': True, **sync})


@bp.get('/video-bank/<int:bank_id>/sources')
def video_bank_sources(bank_id):
    """The per-FILE view: duration, native rate, geometry, probe and detect state.
    GET {'sources': [...]}"""
    if svc.get_bank(LOCAL_USER, bank_id) is None:
        return _missing(bank_id)
    return jsonify({'sources': svc.sources_payload(LOCAL_USER, bank_id)})


# --- clips ---------------------------------------------------------------------

@bp.get('/video-bank/<int:bank_id>/clips')
def video_bank_clips(bank_id):
    """One page of the gallery. ?status= ?source_id= ?offset= ?limit=, and
    ?ids_only=1 which answers {'ids', 'total'} for the WHOLE filter in one request
    — what "select all in filter" needs, sharing this function so the two answers
    can never disagree about what the filter holds."""
    args = request.args

    def _int(name):
        try:
            return int(args.get(name)) if args.get(name) else None
        except ValueError:
            return None

    payload = svc.list_clips(
        LOCAL_USER, bank_id,
        status=args.get('status') or None,
        source_id=_int('source_id'),
        ids_only=args.get('ids_only') == '1',
        offset=_int('offset') or 0, limit=_int('limit') or 200)
    if payload is None:
        return _missing(bank_id)
    return jsonify(payload)


@bp.post('/video-bank/<int:bank_id>/triage')
def video_bank_triage(bank_id):
    """Body {ids: [], status: 'keep'|'reject'|'pending', reason?}.

    An EMPTY/absent ids list means every clip of the bank — the same "no selection
    = all of it" convention promotion uses. The fresh counters ride back on the
    response so the gallery updates without a second round trip; a triage click is
    the most repeated gesture in this lane."""
    if svc.get_bank(LOCAL_USER, bank_id) is None:
        return _missing(bank_id)
    data = request.get_json(silent=True) or {}
    try:
        out = svc.set_clip_status(LOCAL_USER, bank_id, data.get('ids'),
                                  data.get('status'), reason=data.get('reason'))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, **out})


@bp.get('/video-bank/<int:bank_id>/clip/<int:clip_id>/thumb')
def video_bank_clip_thumb(bank_id, clip_id):
    """The one image a bank serves. 404 when the thumbnail pass has not run — the
    gallery renders a placeholder on that, whereas a 500 would fill the console
    with errors for a perfectly ordinary state."""
    if svc.get_bank(LOCAL_USER, bank_id) is None:
        return _missing(bank_id)
    path = svc.thumb_path(bank_id, clip_id)
    if not path.is_file():
        return jsonify({'error': 'no thumbnail for this clip yet'}), 404
    return send_file(str(path), mimetype='image/jpeg')


# --- passes --------------------------------------------------------------------

@bp.post('/video-bank/<int:bank_id>/probe')
def video_bank_probe(bank_id):
    """Read what each source file IS. Body {reprobe?: bool}. 202/404/409."""
    data = request.get_json(silent=True) or {}
    return _start(bank_id, svc.start_probe, _app(), LOCAL_USER, bank_id,
                  reprobe=bool(data.get('reprobe')))


@bp.post('/video-bank/<int:bank_id>/detect')
def video_bank_detect(bank_id):
    """Find the shot boundaries — the expensive pass. Body {redetect?: bool},
    which re-cuts only the clips nobody has promoted. 202/404/409."""
    data = request.get_json(silent=True) or {}
    return _start(bank_id, svc.start_detect, _app(), LOCAL_USER, bank_id,
                  redetect=bool(data.get('redetect')))


@bp.post('/video-bank/<int:bank_id>/thumbs')
def video_bank_thumbs(bank_id):
    """One frame per shot, taken from its MIDDLE. Body {rethumb?: bool}."""
    data = request.get_json(silent=True) or {}
    return _start(bank_id, svc.start_thumbs, _app(), LOCAL_USER, bank_id,
                  rethumb=bool(data.get('rethumb')))


@bp.post('/video-bank/<int:bank_id>/pipeline')
def video_bank_pipeline(bank_id):
    """Probe → detect → thumbnails, chained. Body {steps?: [...]} (canonical order
    is enforced whatever order they arrive in). What a user actually wants on a
    fresh bank, because each pass's input is the previous one's output."""
    data = request.get_json(silent=True) or {}
    return _start(bank_id, svc.start_pipeline, _app(), LOCAL_USER, bank_id,
                  steps=data.get('steps'))


@bp.post('/video-bank/<int:bank_id>/cancel')
def video_bank_cancel(bank_id):
    """Stop the live pass. 200 {'ok', 'cancelled'} — false simply means there was
    nothing running, which is not an error worth a red toast."""
    if svc.get_bank(LOCAL_USER, bank_id) is None:
        return _missing(bank_id)
    return jsonify({'ok': True, 'cancelled': svc.cancel(bank_id)})


@bp.post('/video-bank/<int:bank_id>/promote')
def video_bank_promote(bank_id):
    """Encode the KEPT clips into a new video dataset.

    Body {name, target_profile, frames?, width?, height?, ids?}. `frames` defaults
    to the profile's own default length; width+height are optional and mean "cut at
    this size" (omitted = keep the source's). `ids` empty/absent = every kept clip.

    202 {'ok', 'id', 'name', 'output_dir', 'clips'} — the id rides back so the UI
    can navigate straight to the dataset being filled. 400 names a legal frame
    count or a valid size; 503 means ffmpeg is missing; 409 means a pass is running.

    This is the ONLY route in the lane that writes media, by design: a bank stores
    bounds, and encoding 340 clips to keep 128 is what that design avoids."""
    if svc.get_bank(LOCAL_USER, bank_id) is None:
        return _missing(bank_id)
    data = request.get_json(silent=True) or {}
    width, height = data.get('width'), data.get('height')
    size = (width, height) if width and height else None
    try:
        out = svc.start_promote(_app(), LOCAL_USER, bank_id,
                                ids=data.get('ids'), name=data.get('name'),
                                target_profile=data.get('target_profile'),
                                frames=data.get('frames'), size=size)
    except bank_jobs.BankJobBusy as e:
        return _busy(e)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    return jsonify({'ok': True, **out}), 202
