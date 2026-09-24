"""Compare exact video checkpoints with one shared Studio scene and seed.

The first job is queued only after every selector, frozen weight and workflow
has passed preflight. Each preview link commits with its clip and queue row.
Copies referenced by clips stay in ComfyUI for replay; unused copies created
by a refused batch are removed. No training save is overwritten or moved.
"""
import sqlalchemy as sa
import hashlib
import json
import math
import os
import shutil
import struct
import tempfile
import threading
import uuid
from pathlib import Path

from lds_video.models import db
from lds_sdk import cloud_runs
from lds_video.models import VideoTestClip
from lds_sdk.media import redact_tokens, redact_user_paths
from lds_video.models import VideoCheckpointPreview
from lds_sdk import run_history as rg
from lds_video import video_run_lineage as checkpoint_steps
from lds_video import video_best_settings as best
from lds_video import video_checkpoints as vck
from lds_video import video_test_studio as vts
from lds_video import video_training_local as vtl

_BATCH_LOCK = threading.RLock()
_FIELDS = {'checkpoints', 'mode', 'prompt', 'image', 'end_image', 'seed', 'steps',
           'frames', 'megapixels', 'aspect', 'lora_strength', 'accel', 'turbo',
           'eros', 'light', 'sparse', 'latent_upscale', 'ratio',
           'fused', 'h3_attention', 'h3_spectrum', 'h3_video_vae', 'h3_video_writer'}


class PreviewSelectionError(ValueError):
    def __init__(self, failures):
        super().__init__('Some checkpoints cannot be previewed. No clips were queued.')
        self.failures = failures


def _safe_error(exc):
    return redact_user_paths(redact_tokens(str(exc)))


def _integer(value, label, *, nullable=False, minimum=0):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= 2**53 - 1:
        raise ValueError(f'{label} must be an integer of at least {minimum}.')
    return value


def selectors(data):
    if not isinstance(data, dict) or set(data) - _FIELDS:
        raise ValueError('Unknown preview request fields.')
    requested = data.get('checkpoints')
    if not isinstance(requested, list) or not requested:
        raise ValueError('Choose at least one checkpoint.')
    out, seen = [], set()
    for value in requested:
        if not isinstance(value, dict) or set(value) != {'run_id', 'step', 'final'}:
            raise ValueError('Each checkpoint needs run_id, step and final only.')
        if not isinstance(value['final'], bool):
            raise ValueError('final must be true or false.')
        sel = {'run_id': _integer(value['run_id'], 'run_id', nullable=True, minimum=1),
               'step': _integer(value['step'], 'step', nullable=value['final']),
               'final': value['final']}
        key = (sel['run_id'], 'final' if sel['final'] else sel['step'])
        if key in seen:
            raise ValueError('The same checkpoint was selected more than once.')
        seen.add(key)
        out.append(sel)
    return out


def _options(data):
    from lds_video import video_motion_prompt as motion
    mode = str(data.get('mode') or 't2v').lower()
    if mode not in ('t2v', 'i2v'):
        raise ValueError('Graph previews support H3 text-to-video and image-to-video only; Reference mode is not supported.')
    prompt = str(data.get('prompt') or '').strip()
    if not prompt:
        raise ValueError('Describe the motion for every preview.')
    if len(prompt) > 4000:
        raise ValueError('The preview prompt must be at most 4000 characters.')
    prompt = motion.inject_alignment_header(prompt) if mode == 'i2v' else motion.strip_picture_references(prompt)
    if not motion.has_motion(prompt):
        raise ValueError('The preview prompt needs a motion description.')
    out = {'prompt': prompt, 'mode': mode}
    for role, key in (('start', 'image'), ('last', 'end_image')):
        name = data.get(key) if key != 'image' or mode == 'i2v' else None
        if name:
            if not isinstance(name, str) or name != os.path.basename(name) or '/' in name or '\\' in name:
                raise ValueError(f'The {role} frame must be a staged image name.')
            if not vts.restage_frame(name):
                raise ValueError(f'That {role} frame is no longer staged — pick it again.')
            path = vts.staged_frame_path(name, role=role)
            if key == 'image':
                from PIL import Image
                with Image.open(path) as image:
                    out['source_ratio'] = image.width / max(1, image.height)
            out[key] = name
    if mode == 'i2v' and not out.get('image'):
        raise ValueError('Pick one start frame for the image-to-video previews.')
    for key in ('steps', 'frames'):
        if data.get(key) is not None:
            out[key] = _integer(data[key], key, minimum=1)
    for key in ('megapixels', 'lora_strength'):
        if data.get(key) is not None:
            value = data[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{key} must be a finite number.')
            out[key] = value
    for key in ('eros', 'light', 'latent_upscale', 'turbo', 'fused', 'h3_spectrum'):
        if key in data:
            if not isinstance(data[key], bool):
                raise ValueError(f'{key} must be true or false.')
            out[key] = data[key]
    for key in ('accel', 'sparse', 'aspect', 'h3_attention', 'h3_video_vae', 'h3_video_writer'):
        if key in data:
            if not isinstance(data[key], str):
                raise ValueError(f'{key} must be a name.')
            out[key] = data[key]
    seed = data.get('seed')
    if seed is None or seed == -1:
        seed = vts.random.randint(0, 999_999_999_999_999)
    out['seed'] = _integer(seed, 'seed')
    return out


def _capability(ds, run, files):
    try:
        provenance = vck.run_provenance(ds, run)
    except (OSError, RuntimeError, ValueError, TypeError):
        provenance = {}
    profile, arch = provenance.get('target_profile'), provenance.get('arch')
    if profile == 'minimax_h3_ref2va' or arch == 'minimax_h3_ref2va':
        reason = 'Reference H3 checkpoints need the Reference pipeline; graph previews currently support standard H3 only.'
    elif arch != 'minimax_h3' or profile not in (None, 'minimax_h3'):
        reason = ('Graph previews currently support standard MiniMax H3 only; Wan and LTX need another video pipeline.'
                  if profile or arch else 'This checkpoint has no recorded training architecture. Its current dataset target is not proof.')
    elif len(files) != 1 or any(not os.path.isfile(path) for _, path in files):
        reason = 'This save needs exactly one complete checkpoint file on disk.'
    elif (run.status in rg.ACTIVE_STATES if run is not None else
          vtl.video_training_progress(ds.id, ds.user_id)['active']):
        reason = 'Stop this training before previewing its saves; their files may still change.'
    else:
        return {'ok': True, 'reason': None}
    return {'ok': False, 'reason': reason}


def _resolve_choice(ds, sel):
    run = vck._cloud_run(ds, sel['run_id']) if sel['run_id'] is not None else None
    if run is None:
        from lds_video.video_lineage import local_total_steps
        paths = vck._local_saves(ds)
        steps = checkpoint_steps.group_saves_by_step(paths, target=local_total_steps(ds))
    else:
        paths, steps = rg.run_checkpoint_files(run), checkpoint_steps.harvested_steps(run)
    choice = next((s for s in steps if s['step'] == sel['step'] and bool(s['final']) == sel['final']), None)
    if choice is None:
        raise ValueError('That exact checkpoint step is no longer available.')
    files = [(name, paths.get(name)) for name in choice['files']]
    if any(not path or not os.path.isfile(path) for _, path in files):
        raise ValueError('This checkpoint is incomplete or no longer on disk.')
    cap = _capability(ds, run, files)
    if not cap['ok']:
        raise ValueError(cap['reason'])
    name, path = files[0]
    if os.path.basename(name) != name or '/' in name or '\\' in name or not name.lower().endswith('.safetensors'):
        raise ValueError('Invalid checkpoint file name.')
    return {'selector': sel, 'run': run, 'filename': name, 'source': path}


def _stat_signature(path):
    stat = os.stat(path)
    values = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_dev)
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


def _validate_weight(path):
    """Validate the safetensors index and payload bounds, without loading tensors."""
    from lds_sdk.safetensors import read_safetensors_header as read_header, DTYPE_BYTES as _DTYPE_BYTES
    from lds_sdk.models import validate_model_file
    verdict = validate_model_file(path)
    if verdict['blocking']:
        raise ValueError(verdict['reason'])
    header = read_header(path)
    entries = {k: v for k, v in header.items() if k != '__metadata__'}
    if not entries:
        raise ValueError('This checkpoint contains no LoRA tensors.')
    with open(path, 'rb') as stream:
        payload_size = os.path.getsize(path) - 8 - struct.unpack('<Q', stream.read(8))[0]
    spans = []
    try:
        for spec in entries.values():
            start, end = spec['data_offsets']
            shape = spec['shape']
            if (not all(type(n) is int and n >= 0 for n in [start, end, *shape])
                    or end - start != math.prod(shape) * _DTYPE_BYTES[spec['dtype']]):
                raise ValueError('invalid tensor index')
            spans.append((start, end))
        cursor = 0
        for start, end in sorted(spans):
            if start != cursor or end > payload_size:
                raise ValueError('incomplete tensor payload')
            cursor = end
        if cursor != payload_size:
            raise ValueError('unexpected tensor payload size')
    except (TypeError, KeyError, ValueError) as exc:
        raise ValueError('This checkpoint has an invalid or incomplete safetensors payload.') from exc
    suffixes = (('.lora_A.weight', '.lora_B.weight'), ('.lora_down.weight', '.lora_up.weight'))
    pairs = [(a, b) for a, b in suffixes if any(k.endswith(a) for k in entries)]
    if not pairs or any(k[:-len(a)] + b not in entries
                        for a, b in pairs for k in entries if k.endswith(a)):
        raise ValueError('This checkpoint does not contain complete LoRA weight pairs.')


def _freeze(choice):
    source, name = choice['source'], choice['filename']
    before = _stat_signature(source)
    _validate_weight(source)
    fingerprint = best._fingerprint(source)
    root = vts._loras_write_dir()
    if not root:
        raise ValueError('Configure the ComfyUI LoRA folder before rendering previews.')
    folder = Path(root) / 'previews' / fingerprint
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / name
    created = not destination.exists()
    if created:
        handle, temporary = tempfile.mkstemp(prefix='.preview-', dir=folder)
        os.close(handle)
        try:
            shutil.copyfile(source, temporary)
            if best._fingerprint(temporary) != fingerprint or _stat_signature(source) != before:
                raise ValueError('This checkpoint changed while being copied. Retry after training stops.')
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    elif best._fingerprint(destination) != fingerprint:
        raise ValueError('A cached preview weight was changed. Remove the altered copy before retrying.')
    if _stat_signature(source) != before:
        if created:
            destination.unlink(missing_ok=True)
        raise ValueError('This checkpoint changed while preparing the preview.')
    return {**choice, 'source_sha256': fingerprint, 'source_signature': before,
            'deployed': str(destination), 'created': created,
            'lora': '/'.join((vts.LORA_SUBDIR.replace('\\', '/'), 'previews', fingerprint, name))}


def _cleanup_unused(copies):
    for item in copies:
        if item['created'] and not VideoTestClip.query.filter_by(lora=item['lora']).first():
            try:
                os.unlink(item['deployed'])
                Path(item['deployed']).parent.rmdir()
            except OSError:
                pass


def _public(row, clip, *, source_current=True):
    ready = clip.status == 'done' and bool(clip.filename)
    return {'clip_id': clip.id, 'status': clip.status, 'error': _safe_error(clip.error or '') or None,
            'prompt': clip.prompt, 'seed': clip.seed, 'generation_settings': best.snapshot(clip),
            'url': f'/api/video-studio/clip/{clip.id}/video' if ready else None,
            'poster_url': f'/api/video-studio/clip/{clip.id}/last-frame.png' if ready else None,
            'selector': {'run_id': row.run_id, 'step': row.step, 'final': bool(row.final)},
            'batch_id': row.batch_id, 'source_sha256': row.source_sha256,
            'filename': row.filename, 'source_current': source_current,
            'created_at': row.created_at.isoformat() if row.created_at else None}


def _rows(ds):
    return (db.session.query(VideoCheckpointPreview, VideoTestClip)
            .join(VideoTestClip, sa.and_(VideoTestClip.id == VideoCheckpointPreview.clip_id,
                                        VideoTestClip.job_id == VideoCheckpointPreview.job_id))
            .filter(VideoCheckpointPreview.dataset_id == ds.id,
                    VideoCheckpointPreview.user_id == ds.user_id,
                    VideoTestClip.user_id == ds.user_id)
            .order_by(VideoCheckpointPreview.id.desc()).all())


def list_previews(user_id, dataset_id):
    ds = vck._dataset(user_id, dataset_id)
    sources = {}
    rows = []
    for row, clip in _rows(ds):
        if row.run_id not in sources:
            try:
                run = vck._cloud_run(ds, row.run_id) if row.run_id is not None else None
                paths = rg.run_checkpoint_files(run) if run else vck._local_saves(ds)
                sources[row.run_id] = (run.video_preview_key if run else None, paths)
            except (LookupError, ValueError, OSError, RuntimeError):
                sources[row.run_id] = (None, {})
        run_key, paths = sources[row.run_id]
        try:
            current = (row.run_key == run_key and row.filename in paths
                       and row.source_signature == _stat_signature(paths[row.filename]))
        except OSError:
            current = False
        rows.append(_public(row, clip, source_current=current))
    return {'previews': rows, 'count': len(rows)}


def start_previews(user_id, dataset_id, data):
    ds = vck._dataset(user_id, dataset_id)
    selected = selectors(data)
    choices, failures = [], []
    for sel in selected:
        try:
            choices.append(_resolve_choice(ds, sel))
        except (LookupError, ValueError, RuntimeError, OSError) as exc:
            failures.append({'selector': sel, 'error': _safe_error(exc)})
    if failures:
        raise PreviewSelectionError(failures)
    options = _options(data)
    batch_id, queued, copies = str(uuid.uuid4()), [], []
    with _BATCH_LOCK:
        try:
            classes = vts.registered_classes()
            light_ok, light_note = vts.light_usable() if options.get('light') else (False, '')
            eros_ok = vts.eros_on_disk() if options.get('eros') else False
            for choice in choices:
                item = _freeze(choice)
                copies.append(item)
                item['built'] = vts.build_workflow(**options, lora=item['lora'],
                    performance_classes=classes,
                    eros_on_disk=eros_ok, light_on_disk=light_ok, light_note=light_note,
                    sage=vts.sage_available(classes), filename_prefix=vts.new_prefix(user_id))
                vts.preflight(item['built']['workflow'])
            # No queue row exists before every workflow above passed.
            for item in copies:
                run = item['run']
                sel, recorded = item['selector'], {}

                def record(clip):
                    link = VideoCheckpointPreview(dataset_id=ds.id, user_id=str(user_id),
                        clip_id=clip.id, job_id=clip.job_id, batch_id=batch_id,
                        run_id=sel['run_id'], run_key=run.video_preview_key if run else None,
                        step=sel['step'], final=sel['final'], filename=item['filename'],
                        source_sha256=item['source_sha256'], source_signature=item['source_signature'],
                        deployed_lora=item['lora'])
                    db.session.add(link)
                    recorded['job_id'] = clip.job_id

                try:
                    if run is not None and not run.video_preview_key:
                        # Another request may have loaded this same NULL before
                        # waiting for the batch lock. Never overwrite its committed
                        # identity with the stale ORM object's first UUID.
                        cloud_runs.ensure_video_preview_key(run.id, ds.id, run.dataset_table)
                        run = cloud_runs.get(run.id)
                    result = vts.enqueue_clip(str(user_id), **options, lora=item['lora'],
                        skip_preflight=True, _prepared={'origin': (ds.id, sel['run_id']), 'built': item['built']},
                        _record=record)
                    queued.append({'selector': sel, 'clip_id': result['clip_id'], 'status': 'pending'})
                except Exception as exc:
                    db.session.rollback()
                    persisted = VideoCheckpointPreview.query.filter_by(job_id=recorded.get('job_id')).first()
                    error = {'selector': sel, 'error': _safe_error(exc)}
                    if persisted:
                        queued.append({'selector': sel, 'clip_id': persisted.clip_id, 'status': 'pending',
                                       'warning': error['error']})
                        error.update({'queued': True, 'clip_id': persisted.clip_id})
                    failures.append(error)
        except Exception:
            db.session.rollback()
            _cleanup_unused(copies)
            raise
        _cleanup_unused(copies)
    return {'ok': not failures, 'batch_id': batch_id, 'seed': options['seed'],
            'queued': queued, 'failures': failures, **list_previews(user_id, dataset_id)}


def annotate_pills(ds, run, pills, paths):
    rows = _rows(ds)
    for pill in pills:
        files = [(f['filename'], paths.get(f['filename'])) for f in pill['files']]
        safe_files = [(name, path) for name, path in files if path]
        pill['render_capability'] = _capability(ds, run, safe_files)
        pill['generated_preview'] = None
        if len(safe_files) != 1 or not os.path.isfile(safe_files[0][1]):
            continue
        try:
            signature = _stat_signature(safe_files[0][1])
        except OSError:
            # A save can disappear between scanning a run and drawing its pill.
            pill['render_capability'] = {'ok': False, 'reason': 'This checkpoint is no longer on disk.'}
            continue
        matched = [(row, clip) for row, clip in rows
                   if row.run_id == (run.id if run else None)
                   and row.run_key == (run.video_preview_key if run else None)
                   and row.step == pill['step'] and bool(row.final) == pill['final']
                   and row.filename == safe_files[0][0] and row.source_signature == signature]
        if matched:
            row, clip = matched[0]
            latest = _public(row, clip)
            pill['generated_preview'] = {key: latest[key] for key in ('status', 'url', 'poster_url', 'clip_id')}
            pill['generated_preview']['count'] = sum(c.status == 'done' and bool(c.filename) for _, c in matched)
