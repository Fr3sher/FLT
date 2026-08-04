"""🎬 Video bank — triage a folder of rushes into a video training set.

The image lane rests on "one row = one file". This one cannot: a two-hour rush is
one file and four hundred training clips. Everything below follows from that.

WHAT A BANK STORES: BOUNDS, NOT MEDIA. A clip is a pair of PTS timestamps until
the moment it is promoted, and the only bytes this module ever writes into the
bank are thumbnails. Encoding at detection time is the obvious design and the
wrong one — cutting 340 shots to keep 128 pays 212 encodes for files nobody asked
for, and it would put media in a container whose contract says it holds decisions.
So `ffmpeg` runs exactly once per KEPT clip, at promotion, and never before.

THE SOURCE FOLDER IS READ-ONLY, LITERALLY. Nothing here opens a file in the user's
rushes folder for writing, ever. Thumbnails go to ``video_banks_root()``, clips go
to ``video_datasets_root()``.

WHY FOUR SEAMS. Probing, shot detection, thumbnailing and encoding each need
something the app cannot assume is installed (PyAV, torch, ffmpeg). They are the
only four places this module touches media, each is one function, and each is
monkeypatched by the tests — so the whole service is testable on an install with
none of the video extras, which is also what CI is.

WHY THE JOB KEY IS NAMESPACED. ``bank_jobs`` keys its registry by bank id, and the
two lanes number their banks independently: image bank 1 and video bank 1 both
exist and are different things. Sharing the raw key makes a video detection pass
refuse a click on an unrelated image bank, with a message naming a pass the user
cannot see. Hence ``job_key()`` — the registry itself is happily reused.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from .. import config as cfg
from ..extensions import db
from ..models import (VideoBank, VideoClip, VideoDataset, VideoDatasetClip,
                      VideoSource)
from . import bank_jobs, video_metrics, ffmpeg_tools, path_guard, video_clip_export, video_targets

logger = logging.getLogger(__name__)

# Lowercase, and every comparison folds the filename's case before testing it.
# `DSC_0001.MOV` is what a camera writes and what much of scraped material carries;
# a case-sensitive match creates the bank, reports zero files and says nothing, so
# the folder simply looks empty. That is a support ticket, not a naming detail.
VIDEO_EXTS = ('.mp4', '.mov', '.mkv', '.webm', '.avi')

# A ceiling on the WALK, not on the bank's history — a bank pointed at a whole
# drive must be refused without being counted to the end. Far lower than the image
# lane's: these are files that each become hundreds of rows.
BANK_MAX_FILES = 5000

# Canonical order. Detection needs the probe's fps and duration; thumbnails need
# the bounds detection produced. Running them out of order is not a preference,
# it is a pass that finds nothing to do.
PIPELINE_STEPS = ('probe', 'detect', 'thumbs')

TRIAGE_STATUSES = ('pending', 'keep', 'reject')

_INSERT_CHUNK = 2000


# --- the job slot --------------------------------------------------------------

def job_key(bank_id):
    """The video lane's key into the shared ``bank_jobs`` registry.

    A STRING, so it can never collide with the image lane's integer keys whatever
    the ids happen to be. See the module docstring for the failure this avoids."""
    return f'video:{int(bank_id)}'


def cancel(bank_id) -> bool:
    return bank_jobs.cancel(job_key(bank_id))


def activity(bank_id):
    return bank_jobs.get(job_key(bank_id))


# --- storage -------------------------------------------------------------------

def _bank_dir(bank_id) -> Path:
    return cfg.video_banks_root() / str(int(bank_id))


def _thumbs_dir(bank_id) -> Path:
    return _bank_dir(bank_id) / 'thumbs'


def thumb_path(bank_id, clip_id) -> Path:
    """One .jpg per detected shot. The ONLY media a bank writes."""
    return _thumbs_dir(bank_id) / f'clip_{int(clip_id)}.jpg'


def dataset_dir(dataset_id) -> Path:
    """A video dataset's folder. FLAT — see ``_promote_job`` for why a subfolder
    here is a defect rather than a matter of taste."""
    return cfg.video_datasets_root() / str(int(dataset_id))


def _contained_path(base_dir: str, relpath: str) -> str | None:
    """`base_dir/relpath` resolved, or None when it escapes `base_dir`.

    Both sides are realpath'd (so a symlink cannot step out) and the prefix test
    carries the SEPARATOR: without it `/srv/rushes-secret` passes the check for a
    bank rooted at `/srv/rushes`."""
    base = os.path.realpath(base_dir)
    full = os.path.realpath(os.path.join(base, relpath))
    if os.path.normcase(full).startswith(os.path.normcase(base + os.sep)):
        return full
    return None


def _abs_source_path(bank: VideoBank, relpath: str) -> str | None:
    """The containment-checked absolute path of one source file.

    A relpath is data from a database that a user can edit; resolving it without
    checking it still lands under the bank's folder is how `..` reads a file the
    bank was never pointed at."""
    return _contained_path(bank.source_path, relpath)


def source_media_path(user_id, bank_id, source_id) -> str | None:
    """The readable bytes of ONE source file, for the player. None on anything
    that is not a file this bank legitimately holds.

    One return value for four different refusals (unknown bank, unknown source,
    a relpath that escapes the bank's folder, a file that has since vanished) on
    purpose: the caller answers 404 to all of them. Distinguishing "escaped the
    folder" from "not found" tells whoever tried which paths exist."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        return None
    row = VideoSource.query.filter_by(id=source_id, bank_id=bank_id).first()
    if row is None:
        return None
    path = _abs_source_path(bank, row.relpath)
    return path if path and os.path.isfile(path) else None


def dataset_clip_media_path(user_id, dataset_id, clip_id) -> str | None:
    """The bytes of one PROMOTED clip. Same contract as source_media_path.

    The filename was written by the export job rather than typed by anyone, and
    it is still checked for containment: it is a column in a database the user
    can reach, and "we wrote it ourselves" is the assumption every path-traversal
    write-up starts with."""
    ds = get_video_dataset(user_id, dataset_id)
    if ds is None or not ds.output_dir:
        return None
    row = VideoDatasetClip.query.filter_by(dataset_id=ds.id, id=clip_id).first()
    if row is None:
        return None
    path = _contained_path(ds.output_dir, row.filename or '')
    return path if path and os.path.isfile(path) else None


# --- the four media seams ------------------------------------------------------
# Each is the ONE place this module touches something the app cannot assume is
# installed. Tests replace them; nothing else in this file imports av, torch or
# subprocesses ffmpeg.

def _probe_file(path):
    """What this file is: duration, native rate, geometry, codec. Never raises —
    see services/video_probe.probe."""
    from . import video_probe
    return video_probe.probe(path)


def _detect_shots(path, fps_native=None):
    """The shot boundaries of one file, as dicts carrying PTS seconds.

    Imported lazily and by name so an install with no detection extra fails HERE,
    per file, into detect_state='error' — rather than at import time, which would
    take the whole app down for a capability it may never use."""
    from . import shot_detect
    return shot_detect.detect_shots(path, fps_native=fps_native)


def _is_detector_unavailable(exc) -> bool:
    """Is this "the extra is not installed" rather than "this file failed"?

    services/shot_detect raises two RuntimeErrors: ShotDetectUnavailable (the
    install lacks the detector) and ShotDetectFileError (this one file defeated
    it). They must not be handled the same way — see _detect_job.

    Matched by CLASS NAME, deliberately. The condition being identified is that
    the module may not be importable at all, so importing it here to isinstance()
    against an error raised by its absence is circular. The name is part of the
    contract agreed with that module, and a rename would surface as this branch
    going quiet rather than as a crash — which is why the behaviour is pinned by
    a test rather than left to review."""
    return type(exc).__name__ == 'ShotDetectUnavailable'


def _write_thumbnail(src_path, timestamp_s, dst_path) -> bool:
    """Grab one frame at `timestamp_s` and write it as a .jpg. True on success.

    Lazy `av` import for the same reason as detection, and every failure is a
    False rather than an exception: a bank whose thumbnails failed is still a
    perfectly workable bank, it just shows placeholders."""
    try:
        import av
        from PIL import Image
    except ImportError:
        return False
    try:
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with av.open(src_path) as container:
            stream = container.streams.video[0]
            # Seek in the stream's own time base, then decode forward to the first
            # frame at or after the target: seeking lands on the preceding keyframe.
            container.seek(int(timestamp_s / stream.time_base), stream=stream)
            for frame in container.decode(stream):
                img = frame.to_image()
                img.thumbnail((480, 480), Image.LANCZOS)
                img.convert('RGB').save(dst_path, 'JPEG', quality=82)
                return True
    except Exception:                       # noqa: BLE001 — any decode error
        return False
    return False


def _run_ffmpeg(args):
    """Execute ONE clip encode. Returns (returncode, stderr tail).

    The single subprocess of this module. stderr is truncated because ffmpeg is
    verbose and the tail is where the reason lives."""
    proc = subprocess.run(args, capture_output=True, text=True,
                          encoding='utf-8', errors='replace',
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return proc.returncode, (proc.stderr or '')[-800:]


def _ffmpeg_or_raise():
    """The encoder, or a RuntimeError naming what is missing.

    Checked BEFORE a dataset row is created, so a user with no ffmpeg gets a 503
    instead of an empty dataset folder they then have to clean up."""
    path = ffmpeg_tools.ffmpeg_path()
    if not path:
        raise RuntimeError(
            'ffmpeg is required to cut clips and was not found — install the '
            'video extra from Setup, or put ffmpeg on your PATH')
    return path


# --- banks ---------------------------------------------------------------------

def get_bank(user_id, bank_id) -> VideoBank | None:
    return VideoBank.query.filter_by(id=bank_id, user_id=user_id).first()


def _scan_folder(folder) -> list:
    """Every video file under `folder`, as relpaths. Recursive, case-insensitive."""
    rels = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(VIDEO_EXTS):
                rels.append(os.path.relpath(os.path.join(root, f), folder))
                if len(rels) > BANK_MAX_FILES:
                    raise ValueError(
                        f'this folder holds more than {BANK_MAX_FILES:,} videos '
                        '— point the bank at a subfolder, or split it in two')
    return rels


def create_bank(user_id, name, folder):
    """Register a folder of rushes as a bank: one row per video file.

    Instant — no decode, no detection. Those are the separate passes, because a
    two-hour file costs minutes and an HTTP request must not.
    Returns (bank, added)."""
    name = (name or '').strip()
    # Windows «Copy as path» pastes quoted; unquote so a direct paste works first
    # try, the same nicety the image bank and the dataset import already have.
    folder = (folder or '').strip().strip('"\'')
    if not name:
        raise ValueError('name is required')
    if not folder or not os.path.isdir(folder):
        raise ValueError(f'folder not found or not readable: {folder or "(empty)"}')
    # A bank and a dataset must never share bytes. Both roots are checked: the
    # image lane's (a video bank over it would be harmless today but the rule is
    # the rule) and the video lane's own, which is the real trap — promoting into
    # a folder a bank points at would make the bank list its own output as source
    # material, and re-promote it on the next pass.
    for root in (None, cfg.video_datasets_root()):
        conflict = path_guard.dataset_folder_conflict(folder, datasets_root=root)
        if conflict:
            raise ValueError(conflict['message'])
    folder = os.path.realpath(folder)
    rels = _scan_folder(folder)
    bank = VideoBank(user_id=user_id, name=name, source_path=folder)
    db.session.add(bank)
    db.session.flush()                  # need bank.id for the child rows
    _insert_sources(bank.id, folder, rels)
    db.session.commit()
    return bank, len(rels)


def _insert_sources(bank_id, folder, rels) -> int:
    rows = []
    for rel in rels:
        try:
            size = os.path.getsize(os.path.join(folder, rel))
        except OSError:
            size = None
        rows.append({'bank_id': bank_id, 'relpath': rel, 'file_size': size})
    for i0 in range(0, len(rows), _INSERT_CHUNK):
        db.session.execute(VideoSource.__table__.insert(), rows[i0:i0 + _INSERT_CHUNK])
    return len(rows)


def refresh_bank(user_id, bank_id, force=False) -> dict | None:
    """Re-inventory the source folder.

    STRICTLY ADDITIVE, exactly like the image lane: the only write is an INSERT of
    relpaths we do not know yet. Files that VANISHED are counted, never removed —
    an unplugged drive or a renamed folder would otherwise wipe a triage worked
    over days in one silent pass, and the user would have no way to know why.

    Returns {'added', 'missing', 'unavailable', 'error'}, or None when the bank is
    unknown. ``force`` is accepted for symmetry with the image lane's cooldown."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        return None
    out = {'added': 0, 'missing': 0, 'unavailable': False, 'error': None}
    if not os.path.isdir(bank.source_path):
        out['unavailable'] = True
        out['error'] = 'the source folder is not reachable right now'
        return out
    try:
        rels = _scan_folder(bank.source_path)
    except (OSError, ValueError) as e:
        out['error'] = str(e)
        return out
    known = {s.relpath for s in
             db.session.query(VideoSource.relpath).filter_by(bank_id=bank.id)}
    on_disk = set(rels)
    new = [r for r in rels if r not in known]
    out['missing'] = len(known - on_disk)
    if new:
        _insert_sources(bank.id, bank.source_path, new)
        db.session.commit()
        out['added'] = len(new)
    return out


def delete_bank(user_id, bank_id) -> bool:
    """Throw the bank away, with its sources, clips and thumbnails.

    Children are deleted EXPLICITLY, deepest first, rather than trusted to the
    ondelete=CASCADE in the schema: SQLite only enforces foreign keys when the
    PRAGMA is on, and these models deliberately carry no ORM relationship() to
    cascade through either. What survives is any dataset built out of this bank —
    that is why VideoDatasetClip's provenance is a plain integer."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        return False
    VideoClip.query.filter_by(bank_id=bank.id).delete(synchronize_session=False)
    VideoSource.query.filter_by(bank_id=bank.id).delete(synchronize_session=False)
    db.session.flush()
    db.session.delete(bank)
    db.session.commit()
    try:
        from . import trash
        if _bank_dir(bank_id).is_dir():
            trash.dispose(str(_bank_dir(bank_id)), context='video bank thumbnails')
    except Exception as e:                  # noqa: BLE001 — the rows are gone already
        logger.warning('video bank %s: could not dispose thumbnails: %s', bank_id, e)
    return True


def _counts(bank_id) -> dict:
    src = VideoSource.query.filter_by(bank_id=bank_id)
    clips = VideoClip.query.filter_by(bank_id=bank_id)
    return {
        'sources': src.count(),
        'probed': src.filter(VideoSource.probe_state.isnot(None)).count(),
        'unreadable': src.filter_by(probe_state='unreadable').count(),
        'detected': src.filter_by(detect_state='ok').count(),
        'detect_errors': src.filter_by(detect_state='error').count(),
        'clips': clips.count(),
        'pending': clips.filter_by(status='pending').count(),
        'keep': clips.filter_by(status='keep').count(),
        'reject': clips.filter_by(status='reject').count(),
        'promoted': clips.filter(VideoClip.promoted_dataset_id.isnot(None)).count(),
        'thumbs': clips.filter_by(thumb_state='ok').count(),
    }


def _load_pipeline_report(bank: VideoBank):
    """The persisted pass summary, parsed. A corrupt blob is swallowed — a broken
    report must never 500 the whole bank payload."""
    raw = getattr(bank, 'pipeline_report', None)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def _bank_row(bank: VideoBank) -> dict:
    return {
        'id': bank.id, 'name': bank.name, 'source_path': bank.source_path,
        'created_at': bank.created_at.isoformat() if bank.created_at else None,
        'counts': _counts(bank.id),
    }


def list_banks(user_id) -> list:
    banks = (VideoBank.query.filter_by(user_id=user_id)
             .order_by(VideoBank.id.desc()).all())
    return [_bank_row(b) for b in banks]


def bank_payload(user_id, bank_id) -> dict | None:
    """The workspace payload: the bank, its counters, its per-file state and the
    live job. One request per poll, like the image lane."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        return None
    payload = _bank_row(bank)
    payload['sources'] = sources_payload(user_id, bank_id)
    payload['activity'] = activity(bank_id)
    payload['pipeline_report'] = _load_pipeline_report(bank)
    payload['capability'] = _capability()
    return payload


def _capability() -> dict:
    """Decode / detect / encode reported SEPARATELY — they fail independently and
    are fixed differently, and a single "video unavailable" is how a user
    reinstalls the wrong thing."""
    try:
        from .. import capabilities
        return capabilities.probe_video()
    except Exception as e:                  # noqa: BLE001 — never 500 the payload
        logger.warning('video capability probe failed: %s', e)
        return {'ok': False, 'detail': 'could not probe the video extra',
                'decode': False, 'detect': False, 'encode': False}


def sources_payload(user_id, bank_id) -> list:
    rows = (VideoSource.query.filter_by(bank_id=bank_id)
            .order_by(VideoSource.relpath.asc()).all())
    clip_counts = dict(
        db.session.query(VideoClip.source_id, db.func.count(VideoClip.id))
        .filter(VideoClip.bank_id == bank_id).group_by(VideoClip.source_id).all())
    return [{
        'id': s.id, 'relpath': s.relpath, 'file_size': s.file_size,
        'duration_s': s.duration_s, 'fps_native': s.fps_native,
        'width': s.width, 'height': s.height, 'codec': s.codec,
        'probe_state': s.probe_state, 'detect_state': s.detect_state,
        'clips': clip_counts.get(s.id, 0),
    } for s in rows]


# --- clips ---------------------------------------------------------------------

def metric_thresholds() -> dict:
    """The cuts currently in force, read from config on every call so a Settings
    save re-sorts the bank on the next poll. All default to None — a cut that has
    not been chosen filters NOTHING, because the published defaults measurably do
    not transfer between corpora (the public motion floor lands at the 7th
    percentile of this machine's own test bank)."""
    section = cfg.get('video_bank') or {}
    return {k: section.get(k) for k in
            ('motion_floor', 'motion_ceiling', 'luma_floor', 'freeze_max',
             'sharpness_floor')}


def _clip_row(clip: VideoClip, relpaths: dict, thresholds=None) -> dict:
    metrics = json.loads(clip.metrics_json) if clip.metrics_json else None
    # Flags are DERIVED here, at read time, from raw scores + the thresholds in
    # force — never stored. Sorted so the payload is deterministic.
    flags = (sorted(video_metrics.verdicts(metrics, thresholds))
             if metrics and thresholds is not None
             and metrics.get('metrics_state') == 'ok' else [])
    return {
        'id': clip.id, 'source_id': clip.source_id,
        'relpath': relpaths.get(clip.source_id),
        'start_s': clip.start_s, 'end_s': clip.end_s,
        'duration_s': round(clip.end_s - clip.start_s, 3),
        'start_frame': clip.start_frame, 'end_frame': clip.end_frame,
        'detector': clip.detector, 'thumb_state': clip.thumb_state,
        'status': clip.status, 'reject_reason': clip.reject_reason,
        'promoted_dataset_id': clip.promoted_dataset_id,
        'metrics': metrics if metrics and metrics.get('metrics_state') == 'ok' else None,
        'flags': flags,
    }


def list_clips(user_id, bank_id, *, status=None, source_id=None, ids=None,
               ids_only=False, offset=0, limit=200) -> dict | None:
    """One page of the clip gallery. ``ids_only`` answers the WHOLE filter as a
    list of ids in one request — what "select all in filter" needs, and it shares
    this function so the two answers can never disagree about what the filter
    holds."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        return None
    q = VideoClip.query.filter_by(bank_id=bank_id)
    if status in TRIAGE_STATUSES:
        q = q.filter_by(status=status)
    if source_id:
        q = q.filter_by(source_id=int(source_id))
    if ids is not None:
        q = q.filter(VideoClip.id.in_(ids)) if ids else q.filter(db.false())
    q = q.order_by(VideoClip.source_id.asc(), VideoClip.start_s.asc())
    total = q.count()
    if ids_only:
        return {'ids': [r.id for r in q.all()], 'total': total}
    rows = q.offset(max(0, int(offset))).limit(max(1, int(limit))).all()
    relpaths = dict(db.session.query(VideoSource.id, VideoSource.relpath)
                    .filter_by(bank_id=bank_id).all())
    thresholds = metric_thresholds()
    return {'clips': [_clip_row(c, relpaths, thresholds) for c in rows],
            'total': total, 'offset': int(offset), 'limit': int(limit)}


def metrics_dry_run(user_id, bank_id, thresholds) -> dict:
    """Per-rule counts over the bank's stored raw scores — the preview that keeps
    a mis-set threshold from quietly gutting a bank. Pure read; flags nothing."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        return {'total_flagged': 0}
    rows = (VideoClip.query.filter_by(bank_id=bank_id)
            .filter(VideoClip.metrics_json.isnot(None)).all())
    scores = [json.loads(r.metrics_json) for r in rows]
    return video_metrics.dry_run(
        [s for s in scores if s.get('metrics_state') == 'ok'], thresholds)


def set_clip_status(user_id, bank_id, ids, status, reason=None) -> dict:
    """Triage. ``ids`` empty or None means EVERY clip of the bank — the same
    "no selection = all of it" convention promotion uses, so the two cannot drift.

    ``reject_reason`` is cleared on anything that is not a reject: a clip flipped
    back to keep must not keep carrying why it was once refused."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        raise ValueError('bank not found')
    if status not in TRIAGE_STATUSES:
        raise ValueError(f'status must be one of {", ".join(TRIAGE_STATUSES)}')
    q = VideoClip.query.filter_by(bank_id=bank_id)
    if ids:
        q = q.filter(VideoClip.id.in_([int(i) for i in ids]))
    rows = q.all()
    for row in rows:
        row.status = status
        row.reject_reason = (str(reason)[:16] if (reason and status == 'reject')
                             else None)
    db.session.commit()
    return {'updated': len(rows), 'counts': _counts(bank_id)}


# --- passes --------------------------------------------------------------------

def _require_free_bank(user_id, bank_id) -> VideoBank:
    bank = get_bank(user_id, bank_id)
    if bank is None:
        raise ValueError('bank not found')
    return bank


def start_probe(app, user_id, bank_id, reprobe=False):
    """Read what each source file IS. Cheap per file, but a bank holds hundreds."""
    _require_free_bank(user_id, bank_id)
    return bank_jobs.start(app, job_key(bank_id), 'probe',
                           _probe_job(bank_id, bool(reprobe)))


def _probe_job(bank_id, reprobe):
    def run(job):
        q = VideoSource.query.filter_by(bank_id=bank_id)
        if not reprobe:
            q = q.filter(VideoSource.probe_state.is_(None))
        rows = q.order_by(VideoSource.id.asc()).all()
        bank = db.session.get(VideoBank, bank_id)
        bank_jobs.progress(job, done=0, total=len(rows), detail='probing')
        ok = bad = 0
        for src in rows:
            if bank_jobs.cancelled(job):
                break
            path = _abs_source_path(bank, src.relpath) if bank else None
            info = (_probe_file(path) if path
                    else {'probe_state': 'unreadable'})
            src.probe_state = info.get('probe_state') or 'unreadable'
            if src.probe_state == 'ok':
                src.duration_s = info.get('duration_s')
                src.fps_native = info.get('fps_native')
                src.width = info.get('width')
                src.height = info.get('height')
                codec = info.get('codec')
                src.codec = str(codec)[:24] if codec else None
                ok += 1
            else:
                bad += 1
            if info.get('file_size') is not None:
                src.file_size = info['file_size']
            db.session.commit()
            bank_jobs.bump(job)
        detail = f'done — {ok} readable'
        if bad:
            detail += f', {bad} unreadable'
        bank_jobs.progress(job, detail=detail)
        return {'ok': ok, 'unreadable': bad}
    return run


def start_detect(app, user_id, bank_id, redetect=False):
    """Find the shot boundaries. The expensive pass — minutes per hour of source."""
    _require_free_bank(user_id, bank_id)
    return bank_jobs.start(app, job_key(bank_id), 'detect',
                           _detect_job(bank_id, bool(redetect)))


def _detect_job(bank_id, redetect):
    def run(job):
        q = VideoSource.query.filter_by(bank_id=bank_id, probe_state='ok')
        if not redetect:
            q = q.filter(VideoSource.detect_state.is_(None))
        rows = q.order_by(VideoSource.id.asc()).all()
        bank = db.session.get(VideoBank, bank_id)
        bank_jobs.progress(job, done=0, total=len(rows), detail='detecting shots')
        made = failed = 0
        for src in rows:
            if bank_jobs.cancelled(job):
                break
            path = _abs_source_path(bank, src.relpath) if bank else None
            try:
                if path is None:
                    raise OSError('source file is outside the bank folder')
                shots = _detect_shots(path, src.fps_native)
            except Exception as e:      # noqa: BLE001 — one bad file, not the pass
                if _is_detector_unavailable(e):
                    # A fact about the INSTALL, not about these files. Stamping
                    # detect_state='error' on all of them would be wrong twice:
                    # it blames the material, and because the pass skips anything
                    # already marked, installing the extra afterwards would fix
                    # nothing until the user found the re-detect checkbox.
                    bank_jobs.fail(job, str(e))
                    db.session.rollback()
                    return {'clips': made, 'failed': failed, 'unavailable': True}
                logger.info('video bank %s: detection failed on a source: %s',
                            bank_id, type(e).__name__)
                src.detect_state = 'error'
                failed += 1
                db.session.commit()
                bank_jobs.bump(job)
                continue
            if redetect:
                # Only clips nobody has promoted: a re-detect must not silently
                # revoke the provenance of a dataset already built.
                (VideoClip.query
                 .filter_by(bank_id=bank_id, source_id=src.id)
                 .filter(VideoClip.promoted_dataset_id.is_(None))
                 .delete(synchronize_session=False))
            made += _insert_clips(bank_id, src, shots)
            src.detect_state = 'ok'
            db.session.commit()
            bank_jobs.bump(job)
        detail = f'done — {made} clips found'
        if failed:
            detail += f', {failed} files failed detection'
        bank_jobs.progress(job, detail=detail)
        return {'clips': made, 'failed': failed}
    return run


def _insert_clips(bank_id, src: VideoSource, shots) -> int:
    """Persist the detector's bounds AS GIVEN.

    start_s/end_s are copied verbatim because they are canonical; the frame
    indices are stored because they are what the detector actually said, and they
    make a later disagreement debuggable. Nothing ever cuts from them."""
    rows = []
    for shot in shots or []:
        try:
            start_s = float(shot['start_s'])
            end_s = float(shot['end_s'])
        except (KeyError, TypeError, ValueError):
            continue
        if end_s <= start_s:
            continue
        rows.append({
            'bank_id': bank_id, 'source_id': src.id,
            'start_s': start_s, 'end_s': end_s,
            'start_frame': shot.get('start_frame'),
            'end_frame': shot.get('end_frame'),
            'detector': (shot.get('detector') or 'transnetv2')[:16],
            'status': 'pending',
        })
    for i0 in range(0, len(rows), _INSERT_CHUNK):
        db.session.execute(VideoClip.__table__.insert(), rows[i0:i0 + _INSERT_CHUNK])
    return len(rows)


def start_measure(app, user_id, bank_id, remeasure=False):
    """Wave 2's pass: one decode per clip, every metric out of it. The heavy
    per-clip work lives in video_metrics_scan; this wrapper only gives it the
    same job envelope (busy refusal, progress, cancel) as every other pass."""
    _require_free_bank(user_id, bank_id)
    return bank_jobs.start(app, job_key(bank_id), 'measure',
                           _measure_job(bank_id, bool(remeasure)))


def _measure_job(bank_id, remeasure):
    def run(job):
        from . import video_metrics_scan
        q = (VideoClip.query.filter_by(bank_id=bank_id)
             .join(VideoSource, VideoSource.id == VideoClip.source_id)
             .filter(VideoSource.probe_state == 'ok'))
        if not remeasure:
            q = q.filter(VideoClip.metrics_json.is_(None))
        total = q.count()
        bank_jobs.progress(job, done=0, total=total, detail='measuring clips')
        # Delegate per-clip work but keep cancel/progress here: the scan commits
        # per clip (its resume contract), so cancelling between clips loses
        # nothing and the next run picks up exactly where this one stopped.
        measured = unreadable = 0
        bank = db.session.get(VideoBank, bank_id)
        for clip in q.order_by(VideoClip.id.asc()).all():
            if bank_jobs.cancelled(job):
                break
            r = video_metrics_scan.measure_one(bank, clip)
            if r == 'ok':
                measured += 1
            else:
                unreadable += 1
            bank_jobs.bump(job)
        detail = f'done — {measured} measured'
        if unreadable:
            detail += f', {unreadable} unreadable'
        bank_jobs.progress(job, detail=detail)
        return {'measured': measured, 'unreadable': unreadable}
    return run


def start_thumbs(app, user_id, bank_id, rethumb=False):
    """One frame per shot, taken from the shot's MIDDLE — a boundary is where a cut
    just happened, so the opening frames are disproportionately dissolves and black."""
    _require_free_bank(user_id, bank_id)
    return bank_jobs.start(app, job_key(bank_id), 'thumbs',
                           _thumbs_job(bank_id, bool(rethumb)))


def _thumbs_job(bank_id, rethumb):
    def run(job):
        from . import video_probe
        q = VideoClip.query.filter_by(bank_id=bank_id)
        if not rethumb:
            q = q.filter(VideoClip.thumb_state.is_(None))
        rows = q.order_by(VideoClip.id.asc()).all()
        bank = db.session.get(VideoBank, bank_id)
        relpaths = dict(db.session.query(VideoSource.id, VideoSource.relpath)
                        .filter_by(bank_id=bank_id).all())
        bank_jobs.progress(job, done=0, total=len(rows), detail='making thumbnails')
        ok = 0
        for clip in rows:
            if bank_jobs.cancelled(job):
                break
            path = _abs_source_path(bank, relpaths.get(clip.source_id) or '') \
                if bank else None
            done = False
            if path:
                ts = video_probe.thumbnail_timestamp(clip.start_s, clip.end_s)
                done = _write_thumbnail(path, ts, str(thumb_path(bank_id, clip.id)))
            clip.thumb_state = 'ok' if done else 'error'
            ok += 1 if done else 0
            bank_jobs.bump(job)
        db.session.commit()
        bank_jobs.progress(job, detail=f'done — {ok}/{len(rows)} thumbnails')
        return {'thumbs': ok, 'total': len(rows)}
    return run


def _sanitize_steps(steps):
    if not steps:
        return list(PIPELINE_STEPS)
    wanted = {s for s in steps if s in PIPELINE_STEPS}
    return [s for s in PIPELINE_STEPS if s in wanted]      # canonical order


def start_pipeline(app, user_id, bank_id, steps=None):
    """Probe → detect → thumbnails, chained, with a report that survives the night.

    The passes are also individually reachable, but chaining them is what a user
    actually wants on a fresh bank: each one's input is the previous one's output,
    and running them by hand in the wrong order finds nothing to do and says so in
    a way that reads like a bug."""
    _require_free_bank(user_id, bank_id)
    wanted = _sanitize_steps(steps)
    if not wanted:
        raise ValueError('no pipeline steps selected')
    return bank_jobs.start(app, job_key(bank_id), 'pipeline',
                           _pipeline_job(user_id, bank_id, wanted))


_STEP_RUNNERS = {
    'probe': lambda bank_id: _probe_job(bank_id, False),
    'detect': lambda bank_id: _detect_job(bank_id, False),
    'thumbs': lambda bank_id: _thumbs_job(bank_id, False),
}


def _pipeline_job(user_id, bank_id, steps):
    def run(job):
        import time as _time
        results = []
        pipe = {'steps': list(steps), 'total_steps': len(steps), 'index': 0,
                'current': steps[0], 'results': results}

        def _sync(current=None, index=None):
            if index is not None:
                pipe['index'] = index
            if current is not None:
                pipe['current'] = current
            pipe['results'] = list(results)
            bank_jobs.set_pipeline(job, pipe)

        _sync()
        for i, step in enumerate(steps):
            if bank_jobs.cancelled(job):
                break
            _sync(current=step, index=i)
            entry = {'step': step, 'status': 'done', 'reason': None, 'counts': {}}
            try:
                out = _STEP_RUNNERS[step](bank_id)(job)
                entry['counts'] = out or {}
            except Exception as e:      # noqa: BLE001 — one bad pass never sinks the rest
                entry['status'] = 'error'
                entry['reason'] = f'{type(e).__name__}: {e}'
                db.session.rollback()
            results.append(entry)
            _sync()

        cancelled = bank_jobs.cancelled(job)
        reached = {e['step'] for e in results}
        for step in steps:
            if step not in reached:
                results.append({
                    'step': step,
                    'status': 'cancelled' if cancelled else 'skipped',
                    'reason': 'cancelled before it ran' if cancelled
                    else 'not reached', 'counts': {}})
        _sync()

        report = {'started_at': job.get('started_at'), 'finished_at': _time.time(),
                  'cancelled': cancelled, 'requested_steps': list(steps),
                  'steps': results, 'counts': _counts(bank_id)}
        bank = db.session.get(VideoBank, bank_id)
        if bank is not None:
            bank.pipeline_report = json.dumps(report)
            db.session.commit()
        done_n = sum(1 for e in results if e['status'] == 'done')
        tail = f'done — {done_n}/{len(steps)} steps ran'
        if cancelled:
            tail = f'cancelled — {done_n}/{len(steps)} steps ran'
        bank_jobs.progress(job, detail=tail)
    return run


# --- promotion: the ONE place media is written --------------------------------

def resolve_frames(profile_key, frames):
    """The frame count this export will use, or a ValueError naming a legal one.

    We REFUSE an illegal count rather than snapping to the nearest silently. The
    catalogue can snap, and a UI offering `frame_choices` never produces an illegal
    value, so a request that carries one came from somewhere that believed it —
    and every trainer downstream would accept it and quietly floor it in latent
    space. A refusal that names the nearest legal count is actionable; a silent
    correction produces a dataset that is not the one that was asked for."""
    profile = video_targets.get(profile_key)
    if profile is None:
        raise ValueError(f'unknown target profile: {profile_key}')
    if frames in (None, ''):
        frames = profile['frame_default']
        if not frames:
            raise ValueError(
                f'{profile["label"]} declares no default clip length — pass an '
                'explicit frame count')
    try:
        frames = int(frames)
    except (TypeError, ValueError):
        raise ValueError('frames must be a whole number of frames') from None
    if not video_targets.is_legal_frames(profile_key, frames):
        near = video_targets.snap_frames(profile_key, frames)
        raise ValueError(
            f'{profile["label"]} cannot ingest a {frames}-frame clip — the nearest '
            f'length it accepts is {near}')
    return frames


def resolve_size(profile_key, size):
    """(width, height) or None for "keep the source's size". ValueError off-grid.

    A STEP, not a whitelist: the official size lists are inference-CLI asserts and
    enforcing them would refuse perfectly trainable data. What is real is the
    divisibility the VAE and the patch size impose together."""
    if not size:
        return None
    try:
        width, height = int(size[0]), int(size[1])
    except (TypeError, ValueError, IndexError):
        raise ValueError('size must be a width and a height') from None
    if not video_targets.validate_resolution(profile_key, width, height):
        profile = video_targets.get(profile_key) or {}
        step = profile.get('size_multiple')
        raise ValueError(
            f'{width}x{height} is not a size {profile.get("label", profile_key)} '
            f'can train at — both sides must be multiples of {step}')
    return (width, height)


def start_promote(app, user_id, bank_id, *, ids=None, name, target_profile,
                  frames=None, size=None):
    """Encode the KEPT clips into a new video dataset.

    Everything that can be refused is refused HERE, synchronously, before a single
    row or folder is created: an unknown profile, an illegal frame count, an
    off-grid size, an empty selection, a missing ffmpeg. A background job that
    fails on its first item leaves a dataset the user then has to clean up.

    ``ids`` empty/None = every KEPT clip of the bank. Returns the dataset's
    identity so the caller can navigate straight to it."""
    bank = _require_free_bank(user_id, bank_id)
    name = (name or '').strip()
    if not name:
        raise ValueError('name is required')
    frames = resolve_frames(target_profile, frames)
    size = resolve_size(target_profile, size)
    profile = video_targets.get(target_profile)

    q = VideoClip.query.filter_by(bank_id=bank_id, status='keep')
    if ids:
        q = q.filter(VideoClip.id.in_([int(i) for i in ids]))
    clip_ids = [c.id for c in
                q.order_by(VideoClip.source_id.asc(), VideoClip.start_s.asc()).all()]
    if not clip_ids:
        raise ValueError('nothing to promote — keep some clips first')
    _ffmpeg_or_raise()

    dataset = VideoDataset(user_id=user_id, name=name,
                           target_profile=target_profile, fps=profile['fps'],
                           frames=frames,
                           width=size[0] if size else None,
                           height=size[1] if size else None,
                           output_dir='')
    db.session.add(dataset)
    db.session.flush()                      # need the id to name its folder
    out_dir = dataset_dir(dataset.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset.output_dir = str(out_dir)
    db.session.commit()

    bank_jobs.start(app, job_key(bank_id), 'promote',
                    _promote_job(bank.id, dataset.id, clip_ids, target_profile,
                                 frames, size),
                    total=len(clip_ids))
    return {'id': dataset.id, 'name': dataset.name,
            'output_dir': dataset.output_dir, 'clips': len(clip_ids)}


def _promote_job(bank_id, dataset_id, clip_ids, profile_key, frames, size):
    """One ffmpeg per kept clip, straight into a FLAT folder.

    NOT ONE SUBFOLDER, EVER. ai-toolkit's dataset scan is os.walk — recursive —
    and excludes only dotfiles and a directory literally named `_controls`. A
    `preview/` or `rejects/` folder written here for our own convenience would be
    picked up and trained on with no message anywhere. That makes a subfolder a
    defect rather than a matter of taste, and it is why rejected clips are simply
    never encoded instead of being encoded somewhere out of the way.

    The .txt sidecar is written for EVERY clip that lands, even with no caption:
    musubi-tuner raises FileNotFoundError out of a worker future with no handler
    on the path, and diffusion-pipe drops the clip instead because its
    skip_empty_caption defaults to true. Wave 1 has no captioning at all, so
    without this every clip would take one of those two paths."""
    def run(job):
        ffmpeg = _ffmpeg_or_raise()
        bank = db.session.get(VideoBank, bank_id)
        dataset = db.session.get(VideoDataset, dataset_id)
        if bank is None or dataset is None:
            return {}
        out_dir = Path(dataset.output_dir)
        relpaths = dict(db.session.query(VideoSource.id, VideoSource.relpath)
                        .filter_by(bank_id=bank_id).all())
        rows = {c.id: c for c in VideoClip.query.filter(
            VideoClip.id.in_(clip_ids)).all()}
        bank_jobs.progress(job, done=0, total=len(clip_ids), detail='encoding clips')

        index = 0
        encoded = too_short = failed = 0
        for clip_id in clip_ids:
            if bank_jobs.cancelled(job):
                break
            clip = rows.get(clip_id)
            if clip is None:
                continue
            relpath = relpaths.get(clip.source_id) or ''
            src = _abs_source_path(bank, relpath)
            if not src or not os.path.isfile(src):
                failed += 1
                bank_jobs.bump(job)
                continue
            # The filename index advances only on a clip that LANDED, so the folder
            # is contiguous: trainers walk it in filename order and a gap reads as
            # a dataset someone edited by hand.
            candidate = index + 1
            dst = out_dir / video_clip_export.clip_filename(candidate)
            try:
                args = video_clip_export.command_for_profile(
                    ffmpeg=ffmpeg, src=src, dst=str(dst),
                    start_s=clip.start_s, end_s=clip.end_s,
                    profile_key=profile_key, frames=frames, size=size)
            except video_clip_export.ClipTooShort:
                # Loud, and it leaves NOTHING behind: a short clip encoded anyway
                # is a file ai-toolkit trains as repeated stills without a word.
                too_short += 1
                bank_jobs.bump(job)
                continue
            except ValueError as e:
                failed += 1
                logger.warning('video promote: %s', e)
                bank_jobs.bump(job)
                continue
            code, err = _run_ffmpeg(args)
            if code != 0 or not dst.exists():
                failed += 1
                logger.warning('video promote: ffmpeg exited %s: %s', code, err)
                try:
                    dst.unlink()            # never leave a half file in a dataset
                except OSError:
                    pass
                bank_jobs.bump(job)
                continue
            video_clip_export.write_sidecar(str(dst), None)
            index = candidate
            encoded += 1
            db.session.add(VideoDatasetClip(
                dataset_id=dataset_id, filename=dst.name, caption=None,
                source_bank_id=bank_id, source_clip_id=clip.id,
                src_relpath=relpath, start_s=clip.start_s, end_s=clip.end_s))
            clip.promoted_dataset_id = dataset_id
            db.session.commit()
            bank_jobs.bump(job)

        detail = f'done — {encoded} clips encoded'
        if too_short:
            detail += f', {too_short} too short for {frames} frames'
        if failed:
            detail += f', {failed} failed'
        bank_jobs.progress(job, detail=detail)
        return {'encoded': encoded, 'too_short': too_short, 'failed': failed}
    return run


# --- video datasets ------------------------------------------------------------

def get_video_dataset(user_id, dataset_id) -> VideoDataset | None:
    return VideoDataset.query.filter_by(id=dataset_id, user_id=user_id).first()


def _dataset_row(ds: VideoDataset) -> dict:
    profile = video_targets.get(ds.target_profile) or {}
    seconds = video_targets.clip_seconds(ds.target_profile, ds.frames) \
        if ds.frames else None
    return {
        'id': ds.id, 'name': ds.name, 'target_profile': ds.target_profile,
        'target_label': profile.get('label', ds.target_profile),
        'fps': ds.fps, 'frames': ds.frames,
        'clip_seconds': round(seconds, 3) if seconds else None,
        'width': ds.width, 'height': ds.height, 'output_dir': ds.output_dir,
        'clips': VideoDatasetClip.query.filter_by(dataset_id=ds.id).count(),
        'training_verified': profile.get('training_verified', False),
        # Surfaced on the dataset, not only in the picker: a user who built a set
        # for MiniMax H3 needs the territory restriction in front of them when
        # they come back to it, not once at creation.
        'licence_note': profile.get('licence_note'),
        'created_at': ds.created_at.isoformat() if ds.created_at else None,
    }


def list_video_datasets(user_id) -> list:
    rows = (VideoDataset.query.filter_by(user_id=user_id)
            .order_by(VideoDataset.id.desc()).all())
    return [_dataset_row(d) for d in rows]


def video_dataset_payload(user_id, dataset_id) -> dict | None:
    ds = get_video_dataset(user_id, dataset_id)
    if ds is None:
        return None
    clips = (VideoDatasetClip.query.filter_by(dataset_id=ds.id)
             .order_by(VideoDatasetClip.filename.asc()).all())
    payload = _dataset_row(ds)
    payload['items'] = [{
        'id': c.id, 'filename': c.filename, 'caption': c.caption,
        'source_bank_id': c.source_bank_id, 'source_clip_id': c.source_clip_id,
        'src_relpath': c.src_relpath, 'start_s': c.start_s, 'end_s': c.end_s,
    } for c in clips]
    return payload


def set_dataset_clip_caption(user_id, dataset_id, clip_id, caption) -> dict | None:
    """Write a caption, and REWRITE THE SIDECAR IN THE SAME BREATH.

    Storing the caption in the database alone is the quiet failure of this
    feature: the trainer never reads our database, it reads the .txt next to the
    .mp4. The two must move together or the dataset trains on what it had before,
    with the UI showing what it has now."""
    ds = get_video_dataset(user_id, dataset_id)
    if ds is None:
        return None
    row = VideoDatasetClip.query.filter_by(dataset_id=ds.id, id=clip_id).first()
    if row is None:
        return None
    row.caption = (caption or '').strip() or None
    db.session.commit()
    clip_path = os.path.join(ds.output_dir, row.filename)
    written = True
    try:
        video_clip_export.write_sidecar(clip_path, row.caption)
    except OSError as e:
        written = False
        logger.warning('video dataset %s: could not write sidecar: %s', ds.id, e)
    return {'ok': True, 'caption': row.caption, 'sidecar_written': written}


def delete_video_dataset(user_id, dataset_id) -> bool:
    """Throw away a badly cut dataset — the ENCODE, never the triage.

    The bank's clips stay exactly as they were; they only stop claiming to have
    been promoted. That is the whole point of promoted_dataset_id being a real FK
    with SET NULL, and it is applied here by hand because SQLite enforces neither
    the cascade nor the SET NULL unless the PRAGMA is on."""
    ds = get_video_dataset(user_id, dataset_id)
    if ds is None:
        return False
    (VideoClip.query.filter_by(promoted_dataset_id=ds.id)
     .update({'promoted_dataset_id': None}, synchronize_session=False))
    VideoDatasetClip.query.filter_by(dataset_id=ds.id).delete(
        synchronize_session=False)
    db.session.flush()
    out_dir = ds.output_dir
    db.session.delete(ds)
    db.session.commit()
    try:
        from . import trash
        if out_dir and os.path.isdir(out_dir):
            trash.dispose(out_dir, context='video dataset')
    except Exception as e:                  # noqa: BLE001 — the rows are gone already
        logger.warning('video dataset %s: could not dispose its folder: %s',
                       dataset_id, e)
    return True
