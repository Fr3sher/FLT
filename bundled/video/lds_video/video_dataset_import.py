"""Create video datasets and append encoded clips without a bank intermediary."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import uuid

from lds_sdk.video_host import bank_jobs
from lds_video import video_bank_service as svc, video_clip_export, video_probe, video_targets
from lds_video.models import db, VideoDataset, VideoDatasetClip


def job_key(dataset_id):
    return f'video-dataset-import:{int(dataset_id)}'


def create(user_id, *, name, target_profile, frames=None, size=None, trigger_word=None):
    name = str(name or '').strip()
    if not name or len(name) > 100:
        raise ValueError('Name must contain 1 to 100 characters.')
    trigger = str(trigger_word or '').strip()
    if len(trigger) > 100:
        raise ValueError('Trigger word must contain at most 100 characters.')
    frames = svc.resolve_frames(target_profile, frames)
    size = svc.resolve_size(target_profile, size)
    profile = video_targets.get(target_profile)
    if not profile.get('fps') or frames <= 1:
        raise ValueError('Choose a video target with a fixed frame rate.')
    ds = VideoDataset(user_id=user_id, name=name, target_profile=target_profile,
                      fps=profile['fps'], frames=frames, width=size[0] if size else None,
                      height=size[1] if size else None, trigger_word=trigger or None,
                      output_dir='')
    db.session.add(ds)
    db.session.flush()
    folder = svc.dataset_dir(ds.id)
    created_folder = False
    try:
        folder.mkdir(parents=True, exist_ok=False)
        created_folder = True
        ds.output_dir = str(folder)
        db.session.commit()
    except Exception:
        db.session.rollback()
        # Only remove our empty directory; never erase a pre-existing dataset.
        if created_folder and folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()
        raise
    return svc._dataset_row(ds)


def _require_dataset(user_id, dataset_id):
    ds = svc.get_video_dataset(user_id, dataset_id)
    if ds is None:
        raise ValueError('video dataset not found')
    from lds_sdk.video_runtime import queue as queue_manager
    from lds_sdk.video_host import cloud_run_dataset
    if (queue_manager._get_system_state('training_in_progress', False)
            and queue_manager._get_system_state('training_dataset_table', None) == cloud_run_dataset.VIDEO
            and str(queue_manager._get_system_state('training_dataset_id', None)) == str(dataset_id)):
        raise ValueError('Wait for local training to finish before adding videos to this dataset.')
    if not ds.frames or not ds.fps or ds.frames <= 1:
        raise ValueError('This dataset takes still images, not video clips.')
    svc._ffmpeg_or_raise()
    # Fail before saving uploads when the decoder still needs preparation.
    try:
        import av  # noqa: F401
    except ImportError as exc:
        raise ValueError('Prepare video decoding in the Video settings first.') from exc
    return ds


def start(app, user_id, dataset_id, *, items=None, files=None, slice_long=False):
    """Stage uploads and launch one cancellable import. Web fetches run in the job."""
    _require_dataset(user_id, dataset_id)
    entries = list(files if files is not None else (items or []))
    if not entries:
        raise ValueError('Choose at least one video to import.')
    if files is None and any(not isinstance(item, dict) or not item.get('url')
                             or item.get('type') != 'video' for item in entries):
        raise ValueError('Choose video results to import.')
    key = job_key(dataset_id)
    lease = bank_jobs.reserve(key, 'video_import', total=len(entries))
    staging = None
    try:
        staging = Path(tempfile.mkdtemp(prefix='lds_video_import_'))
        staged = []
        if files is not None:
            from lds_sdk.video_host.scrape.netfetch import MAX_DRIVER_BYTES
            for upload in entries:
                # The browser filename is display data only, never a disk path.
                name = str(upload.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
                if Path(name).suffix.lower() not in svc.VIDEO_EXTS:
                    raise ValueError('Choose MP4, MOV, MKV, WebM or AVI videos.')
                path = staging / uuid.uuid4().hex
                size = 0
                with path.open('wb') as out:
                    while chunk := upload.stream.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_DRIVER_BYTES:
                            raise ValueError('A video exceeds the 200 MB import limit.')
                        out.write(chunk)
                staged.append({'path': str(path), 'name': name})
        else:
            staged = entries
        bank_jobs.start(app, key, 'video_import',
                        _worker(user_id, dataset_id, staged, staging, bool(slice_long), files is not None),
                        total=len(entries), reservation=lease)
    except Exception:
        bank_jobs.abort(lease)
        if staging:
            shutil.rmtree(staging, ignore_errors=True)
        raise
    return {'ok': True, 'queued': len(entries), 'activity': bank_jobs.get(key)}


def _worker(user_id, dataset_id, entries, staging, slice_long, uploaded):
    def run(job):
        encoded = already_there = 0
        skipped = {}
        try:
            ds = svc.get_video_dataset(user_id, dataset_id)
            if ds is None:
                raise ValueError('video dataset not found')
            out_dir = Path(ds.output_dir)
            profile = video_targets.get(ds.target_profile)
            size = (ds.width, ds.height) if ds.width and ds.height else None
            known = {row.filename for row in VideoDatasetClip.query.filter_by(dataset_id=dataset_id)}
            for entry in entries:
                if bank_jobs.cancelled(job):
                    break
                bank_jobs.progress(job, detail='Reading video' if uploaded else 'Downloading video')
                reason, path = ('ok', entry['path']) if uploaded else svc._download_scrape_video(entry, str(staging))
                if reason != 'ok' or not path:
                    skipped[reason] = skipped.get(reason, 0) + 1
                    bank_jobs.bump(job)
                    continue
                try:
                    blob = svc._video_blob_name(path)
                    probe = video_probe.probe(path)
                    duration = probe.get('duration_s') or 0
                    if not blob or probe.get('probe_state') != 'ok' or duration <= 0:
                        skipped['not_video'] = skipped.get('not_video', 0) + 1
                        continue
                    # Container duration includes the last frame's display
                    # interval. The exporter needs the last frame's timestamp.
                    duration = max(0, duration - 1 / (probe.get('fps_native') or ds.fps))
                    if (not size and profile.get('max_pixels') and
                            (probe.get('width') or 0) * (probe.get('height') or 0) > profile['max_pixels']):
                        skipped['resolution_too_large'] = skipped.get('resolution_too_large', 0) + 1
                        continue
                    if size is None:
                        step = profile.get('size_multiple') or 1
                        size = (int(probe.get('width') or 0) // step * step,
                                int(probe.get('height') or 0) // step * step)
                        if not all(size):
                            size = None
                            skipped['invalid_geometry'] = skipped.get('invalid_geometry', 0) + 1
                            continue
                    spans = video_clip_export.slice_spans(0, duration, ds.frames, ds.fps) if slice_long else [(0, duration)]
                    if not spans:
                        skipped['too_short'] = skipped.get('too_short', 0) + 1
                    for start_s, end_s in spans:
                        if bank_jobs.cancelled(job):
                            break
                        bank_jobs.require_reservation(job, job_key(dataset_id))
                        filename = f'import_{Path(blob).stem}_{round(start_s * 1000)}.mp4'
                        if filename in known:
                            already_there += 1
                            continue
                        dest = out_dir / filename
                        # Encode outside the training folder. Interrupted encodes
                        # and unselected footage must never become training input.
                        temp = staging / f'{uuid.uuid4().hex}.mp4'
                        try:
                            args = video_clip_export.command_for_profile(
                                ffmpeg=svc._ffmpeg_or_raise(), src=path, dst=str(temp),
                                start_s=start_s, end_s=end_s, profile_key=ds.target_profile,
                                frames=ds.frames, size=size)
                        except video_clip_export.ClipTooShort:
                            skipped['too_short'] = skipped.get('too_short', 0) + 1
                            break
                        except ValueError:
                            skipped['invalid_geometry'] = skipped.get('invalid_geometry', 0) + 1
                            break
                        bank_jobs.progress(job, detail='Encoding clips')
                        code, _err = svc._run_ffmpeg(args)
                        if code != 0 or not temp.is_file():
                            skipped['encode_failed'] = skipped.get('encode_failed', 0) + 1
                            continue
                        import av
                        with av.open(str(temp)) as container:
                            complete = container.streams.video[0].frames == ds.frames
                        if not complete:
                            skipped['too_short'] = skipped.get('too_short', 0) + 1
                            temp.unlink(missing_ok=True)
                            continue
                        bank_jobs.require_reservation(job, job_key(dataset_id))
                        if bank_jobs.cancelled(job):
                            break
                        # No source title is silently treated as a training caption.
                        caption = ''
                        sidecar = svc.plan_sidecar(ds.trigger_word, caption, None,
                                                  keeps_audio=bool(profile.get('audio')))['text']
                        part = out_dir / f'.{filename}.part'
                        try:
                            shutil.copyfile(temp, part)
                            os.replace(part, dest)
                            video_clip_export.write_sidecar(str(dest), sidecar)
                            if not ds.width or not ds.height:
                                ds.width, ds.height = size
                            db.session.add(VideoDatasetClip(dataset_id=dataset_id,
                                filename=filename, caption=caption,
                                src_relpath=entry.get('name') if uploaded else blob,
                                start_s=start_s, end_s=start_s + (ds.frames - 1) / ds.fps))
                            db.session.commit()
                        except Exception:
                            db.session.rollback()
                            dest.unlink(missing_ok=True)
                            dest.with_suffix('.txt').unlink(missing_ok=True)
                            raise
                        finally:
                            part.unlink(missing_ok=True)
                            temp.unlink(missing_ok=True)
                        known.add(filename)
                        encoded += 1
                finally:
                    Path(path).unlink(missing_ok=True)
                    bank_jobs.bump(job)
            detail = f'{encoded} clips added'
            if already_there:
                detail += f', {already_there} already imported'
            if skipped:
                detail += ', ' + ', '.join(f'{count} {why.replace("_", " ")}' for why, count in skipped.items())
            bank_jobs.progress(job, detail=detail)
            return {'encoded': encoded, 'already_there': already_there, 'skipped': skipped}
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return run
