"""Video-owned dataset/Studio adapters for the optional DLSS 5 product.

Tables, original backups and row writes stay with Video. The renderer is
resolved through the enabled DLSS API; these helpers never ship its engine.
"""
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from lds_sdk import config as cfg
from lds_sdk.video_host import bank_jobs
from lds_sdk.dlss5 import (NeuralRenderError, normalize_params, status,
                           render_video, render_record)
logger = logging.getLogger(__name__)
JOB_KIND = 'neural_render'
_STUDIO_THREADS = {}

def backup_dir(dataset_id) -> Path:
    """Originals of rendered dataset clips — OUTSIDE the dataset folder on
    purpose (every trainer reads that folder whole)."""
    return cfg.data_dir() / 'video_nr_backup' / str(int(dataset_id))

# ── Dataset clips: render in place, keep the original ───────────────────────

def job_key(dataset_id) -> str:
    """The bank_jobs slot. A string on purpose, like the video bank's
    ``video:<id>``: dataset 3 and image bank 3 must never share a slot."""
    return f'vds:{int(dataset_id)}'


def dataset_job(dataset_id):
    return bank_jobs.get(job_key(dataset_id))


def cancel_dataset_job(dataset_id) -> bool:
    return bank_jobs.cancel(job_key(dataset_id))


def _dataset_and_rows(user_id, dataset_id, clip_ids=None):
    from lds_video.models import VideoDatasetClip
    from lds_video import video_bank_service as vbs
    ds = vbs.get_video_dataset(user_id, dataset_id)
    if ds is None or not ds.output_dir:
        return None, []
    q = VideoDatasetClip.query.filter(VideoDatasetClip.dataset_id == ds.id)
    if clip_ids:
        ids = {int(i) for i in clip_ids if str(i).lstrip('-').isdigit()}
        q = q.filter(VideoDatasetClip.id.in_(ids))
    return ds, q.order_by(VideoDatasetClip.filename).all()


def rendered_clip_ids(user_id, dataset_id) -> list:
    """Which clips of this dataset currently play a RENDER (their original is in
    the backup folder). Derived from disk, not stored: the backup IS the state."""
    ds, rows = _dataset_and_rows(user_id, dataset_id)
    if ds is None:
        return []
    root = backup_dir(ds.id)
    return [r.id for r in rows if (root / r.filename).is_file()]


def start_dataset_render(app, user_id, dataset_id, clip_ids, params) -> dict:
    """Queue the in-place render of ``clip_ids`` (all clips when empty). One job
    per dataset, like every bank pass; the snapshot is read from dataset_job."""
    params = normalize_params(params)
    st = status()
    if not st['ready']:
        raise NeuralRenderError('neural rendering is not set up: ' + '; '.join(st['missing']))
    ds, rows = _dataset_and_rows(user_id, dataset_id, clip_ids)
    if ds is None:
        raise NeuralRenderError('dataset not found')
    if not rows:
        raise NeuralRenderError('no clip to render')
    targets = [(r.id, r.filename) for r in rows]
    out_dir = ds.output_dir
    dataset_ident = ds.id

    def _run(job):
        done = 0
        failed = []
        current = {'proc_cancel': False}
        bank_jobs.set_cancel_hook(job, lambda: current.__setitem__('proc_cancel', True))
        for clip_id, filename in targets:
            if bank_jobs.cancelled(job):
                break
            bank_jobs.progress(job, done=done, total=len(targets), detail=f'rendering {filename}')
            try:
                _render_one_in_place(dataset_ident, out_dir, filename, params,
                                     cancel=lambda: bank_jobs.cancelled(job) or current['proc_cancel'])
            except NeuralRenderError as exc:
                if str(exc) == 'cancelled':
                    break
                failed.append(f'{filename}: {exc}')
                logger.warning('neural render: dataset %s %s failed: %s', dataset_ident, filename, exc)
            done += 1
            bank_jobs.progress(job, done=done, total=len(targets))
        if failed:
            bank_jobs.fail(job, f'{len(failed)} of {len(targets)} clips failed — first: {failed[0]}')

    bank_jobs.start(app, job_key(dataset_ident), JOB_KIND, _run, total=len(targets))
    return {'queued': len(targets), 'params': params}


def sidecar_path(dataset_id, filename) -> Path:
    """Where a dataset clip's render record lives: next to its kept original,
    outside the dataset folder (a trainer must never find a .json there)."""
    return backup_dir(dataset_id) / (os.path.basename(str(filename)) + '.nr.json')


def rendered_clip_params(user_id, dataset_id) -> dict:
    """{clip id: render record} for every clip of the dataset that plays a
    render and whose record survived. Read from disk like rendered_clip_ids —
    the backup folder IS the state."""
    ds, rows = _dataset_and_rows(user_id, dataset_id)
    if ds is None:
        return {}
    out = {}
    for r in rows:
        path = sidecar_path(ds.id, r.filename)
        if not (backup_dir(ds.id) / r.filename).is_file() or not path.is_file():
            continue
        try:
            out[r.id] = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
    return out


def _render_one_in_place(dataset_id, out_dir, filename, params, cancel=None) -> dict:
    """Render ONE dataset clip over itself.

    The ORIGINAL is the source, always: the first render copies the clip into
    the backup folder (write-once — an existing backup is never overwritten),
    and every render reads from there. So a clip rendered twice with different
    dials is two renders of the original, never a render of a render. The
    output lands next to the clip under a temporary name and replaces it in
    one ``os.replace``: the folder never holds a half-written .mp4 under the
    clip's name, and a trainer walking it mid-render sees the old file or the
    new one, never a truncated one."""
    clip_path = os.path.join(out_dir, filename)
    if not os.path.isfile(clip_path):
        raise NeuralRenderError('the clip is no longer on disk')
    root = backup_dir(dataset_id)
    root.mkdir(parents=True, exist_ok=True)
    backup = root / filename
    if not backup.is_file():
        shutil.copy2(clip_path, backup)
    fd, tmp_out = tempfile.mkstemp(prefix='.nr-', suffix='.mp4.part', dir=out_dir)
    os.close(fd)
    try:
        result = render_video(str(backup), tmp_out, params, cancel=cancel)
        os.replace(tmp_out, clip_path)
        try:
            sidecar_path(dataset_id, filename).write_text(
                json.dumps(render_record(params, result)), encoding='utf-8')
        except OSError:
            logger.warning('neural render: could not record the dials of %s', filename)
    finally:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
    return result


def forget_backups(dataset_id, filenames=None) -> int:
    """Drop the kept originals of clips that left the dataset (every backup when
    ``filenames`` is None — the dataset itself is gone). A backup without its
    clip can never be restored: a re-promotion creates a NEW dataset id, so
    the folder would only ever grow. Called by the routes that remove clips
    and delete datasets, after the removal succeeded."""
    root = backup_dir(dataset_id)
    if not root.is_dir():
        return 0
    if filenames is None:
        shutil.rmtree(root, ignore_errors=True)
        return 1
    dropped = 0
    for name in filenames:
        path = root / os.path.basename(str(name))
        if path.is_file():
            try:
                path.unlink()
                dropped += 1
            except OSError:
                pass
        record = root / (os.path.basename(str(name)) + '.nr.json')
        if record.is_file():
            try:
                record.unlink()
            except OSError:
                pass
    try:
        root.rmdir()          # only when empty
    except OSError:
        pass
    return dropped


def original_clip_path(user_id, dataset_id, clip_id) -> str | None:
    """The kept ORIGINAL of a rendered dataset clip, for the side-by-side
    player — None when the clip is unknown or plays no render (no backup).
    The filename comes from the row, never from the request, and the backup
    folder is the app's own: containment is by construction."""
    ds, rows = _dataset_and_rows(user_id, dataset_id, [clip_id])
    if ds is None or not rows:
        return None
    path = backup_dir(ds.id) / os.path.basename(rows[0].filename)
    return str(path) if path.is_file() else None


def restore_dataset_clips(user_id, dataset_id, clip_ids=None) -> dict:
    """🩹 Put the originals back (all rendered clips when ``clip_ids`` is empty).
    The backup is MOVED over the clip, so a restored clip has no backup and is
    reported as not rendered — the two facts cannot drift apart."""
    ds, rows = _dataset_and_rows(user_id, dataset_id, clip_ids)
    if ds is None:
        raise NeuralRenderError('dataset not found')
    if bank_jobs.running(job_key(ds.id)):
        raise NeuralRenderError('a render is running on this dataset — stop it first')
    root = backup_dir(ds.id)
    restored = 0
    for row in rows:
        backup = root / row.filename
        if not backup.is_file():
            continue
        clip_path = os.path.join(ds.output_dir, row.filename)
        try:
            os.replace(backup, clip_path)
            restored += 1
            sidecar = sidecar_path(ds.id, row.filename)
            if sidecar.is_file():
                sidecar.unlink()
        except OSError as exc:
            logger.warning('neural render: restore of %s refused: %s', row.filename, exc)
    return {'restored': restored}


# ── Studio clips: a new row ─────────────────────────────────────────────────

def start_studio_render(app, user_id, clip_id, params) -> dict:
    """✨ Render a finished studio clip as a NEW clip (never an edit — the
    studio exists to compare). The row is written first, in ``pending``; a
    daemon thread renders and flips it to ``done`` or ``failed`` with the
    child's own sentence in ``error``."""
    from lds_video.models import db
    from lds_video.models import VideoTestClip
    from lds_video import video_test_studio as vts

    params = normalize_params(params)
    st = status()
    if not st['ready']:
        raise NeuralRenderError('neural rendering is not set up: ' + '; '.join(st['missing']))
    src = VideoTestClip.query.filter_by(id=int(clip_id)).first()
    if src is None:
        raise NeuralRenderError('clip not found')
    if src.status != 'done' or not src.filename:
        raise NeuralRenderError('that clip has not finished rendering yet')
    src_path = os.path.join(str(vts.clips_dir()), os.path.basename(src.filename))
    if not os.path.isfile(src_path):
        raise NeuralRenderError('that clip is no longer on disk')
    live = _STUDIO_THREADS.get(src.id)
    if live is not None and live.is_alive():
        raise NeuralRenderError('that clip is already being rendered')

    out_name = f'{vts.new_prefix(user_id)}_nr_{uuid.uuid4().hex[:6]}.mp4'
    clip = VideoTestClip(
        run_id=src.run_id, dataset_id=src.dataset_id, job_id=None,
        status='pending', prompt=src.prompt, mode=src.mode,
        aspect=src.aspect or 'auto', accel=src.accel,
        source_image=src.source_image, seed=src.seed, steps=src.steps,
        frames=src.frames, megapixels=src.megapixels, fps=src.fps,
        base_model=src.base_model, lora=src.lora, lora_strength=src.lora_strength,
        turbo=bool(src.turbo), sparse=src.sparse, latent_upscale=bool(src.latent_upscale),
        vfi_of=src.vfi_of, nr_of=src.id, nr_params=json.dumps(params))
    db.session.add(clip)
    db.session.commit()
    new_id = clip.id
    dst_path = os.path.join(str(vts.clips_dir()), out_name)

    def _run():
        with app.app_context():
            row = VideoTestClip.query.filter_by(id=new_id).first()
            # ⏱ This lane never goes through the queue, so nothing stamps it:
            # measured here, so a rendered clip carries a time its source can
            # be compared against — the very use of ⇔ Compare. Monotonic: a
            # local duration, not two database stamps.
            t0 = time.monotonic()
            try:
                result = render_video(src_path, dst_path, params)
                if row is not None:
                    row.filename = out_name
                    row.status = 'done'
                    row.error = None
                    row.nr_params = json.dumps(render_record(params, result))
                    logger.info('neural render: studio clip %s -> %s (%s, %s frames, %.1f ms/frame)',
                                src.id, new_id, result.get('mode_note'), result.get('frames'),
                                result.get('mean_ms') or 0)
            except NeuralRenderError as exc:
                if row is not None:
                    row.status = 'failed'
                    row.error = str(exc)
            except Exception as exc:  # noqa: BLE001 — the row must never stay pending
                logger.exception('neural render: studio clip %s crashed', new_id)
                if row is not None:
                    row.status = 'failed'
                    row.error = f'unexpected failure: {exc}'
            if row is not None:
                row.render_seconds = round(time.monotonic() - t0, 1)
            db.session.commit()

    thread = threading.Thread(target=_run, name=f'neural-render-{new_id}', daemon=True)
    _STUDIO_THREADS[src.id] = thread
    thread.start()
    return {'clip_id': new_id, 'params': params}


def dataset_exists(user_id, dataset_id):
    from .video_bank_service import get_video_dataset
    return get_video_dataset(user_id, dataset_id) is not None

def dataset_clip_media_path(user_id, dataset_id, clip_id):
    from .video_bank_service import dataset_clip_media_path as path
    return path(user_id, dataset_id, clip_id)

def studio_comparison_paths(user_id, clip_id):
    from .models import VideoTestClip
    from .video_test_studio import clips_dir
    def owned(ident):
        row = VideoTestClip.query.filter_by(id=int(ident)).first()
        return row if row and row.user_id in (None, str(user_id)) else None
    clip = owned(clip_id)
    if not clip or not clip.filename or not clip.nr_of:
        raise FileNotFoundError('this clip is not a neural render — nothing to compare')
    source = owned(clip.nr_of)
    if not source or not source.filename:
        raise FileNotFoundError('the clip this render came from is gone')
    root = Path(clips_dir()).resolve()
    paths = [root / os.path.basename(row.filename) for row in (source, clip)]
    if any(path.resolve().parent != root or not path.is_file() for path in paths):
        raise NeuralRenderError('The comparison files are unavailable.')
    return tuple(map(str, paths))

API_VERSION = 1
