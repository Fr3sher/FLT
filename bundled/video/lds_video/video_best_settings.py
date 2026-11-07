"""A video's chosen generation recipe, attached to its verified training set."""
import hashlib
import json
import os
from datetime import datetime, timezone
from functools import lru_cache

from lds_video.models import db
from lds_sdk import cloud_runs
from lds_video.models import VideoDataset, VideoTestClip


def _name(value):
    return str(value or '').replace('\\', '/').strip('/')


@lru_cache(maxsize=128)
def _digest(path, size, modified, changed):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.digest()


def _same_weight(first, second):
    try:
        a, b = os.stat(first), os.stat(second)
        if a.st_size != b.st_size:
            return False
        if os.path.samefile(first, second):
            return True
        return _digest(os.path.realpath(first), a.st_size, a.st_mtime_ns, a.st_ctime_ns) == _digest(
            os.path.realpath(second), b.st_size, b.st_mtime_ns, b.st_ctime_ns)
    except OSError:
        return False


def _fingerprint(path):
    stat = os.stat(path)
    return _digest(os.path.realpath(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns).hex()


def _deployed_path(name):
    from lds_sdk.video_host import comfy_model_paths
    # Resolve the same first existing search root as the loader.
    return next((os.path.join(str(root), *name.split('/'))
                 for root in comfy_model_paths.search_roots('loras')
                 if os.path.isfile(os.path.join(str(root), *name.split('/')))), None)


def _saved_origin(ds, name, deployed):
    """The remembered weight stays attributable after its training save is removed."""
    from lds_sdk.video_host import run_dataset as crd
    saved = read_best(ds)
    if not saved or _name(saved['settings'].get('lora')) != name:
        return None
    run_id = saved.get('run_id')
    if run_id is not None:
        run = cloud_runs.get(run_id)
        if run is not None and not crd.owns(run, ds.id, crd.VIDEO):
            return None
    try:
        if not saved.get('lora_sha256') or _fingerprint(deployed) != saved['lora_sha256']:
            return None
    except OSError:
        return None
    return ds.id, run_id


def resolve_lora(user_id, lora, *, run_id=None, dataset_id=None):
    """Resolve a real deployed weight to ONE video training origin.

    Client ids are assertions to check, never attribution. Identical basenames
    are insufficient: the deployed bytes must match the checkpoint. Ambiguous
    imported files remain unassociated; explicit wrong claims are refused.
    """
    from lds_video import video_training_local as vtl
    from lds_sdk import run_history as rg
    from lds_sdk.video_host import run_dataset as crd
    name = _name(lora)
    claimed = run_id not in (None, '') or dataset_id not in (None, '')
    if not name:
        if claimed:
            raise ValueError('A video dataset or run needs its trained LoRA.')
        return None, None
    if '..' in name.split('/') or os.path.isabs(str(lora)):
        raise ValueError('Invalid deployed LoRA name.')
    deployed = _deployed_path(name)
    if not deployed:
        if claimed:
            raise ValueError('The trained LoRA is not deployed in ComfyUI.')
        return None, None
    basename = name.rsplit('/', 1)[-1]
    datasets = VideoDataset.query.filter_by(user_id=user_id).all()
    ids = {ds.id for ds in datasets}
    matches = set()
    for run in [run for run in cloud_runs.all_runs() if run.dataset_table == 'video_dataset']:
        if run.dataset_id not in ids or not crd.owns(run, run.dataset_id, crd.VIDEO):
            continue
        path = rg.run_checkpoint_files(run).get(basename)
        if path and _same_weight(deployed, path):
            matches.add((run.dataset_id, run.id))
    for ds in datasets:
        try:
            entries = vtl.list_run_checkpoints(ds.id, user_id)
        except (RuntimeError, OSError):
            continue
        if any(e['filename'] == basename and _same_weight(deployed, e['path']) for e in entries):
            matches.add((ds.id, None))
    for ds in datasets:
        saved_origin = _saved_origin(ds, name, deployed)
        if saved_origin:
            matches.add(saved_origin)
    if run_id not in (None, ''):
        matches = {m for m in matches if m[1] == int(run_id)}
    if dataset_id not in (None, ''):
        matches = {m for m in matches if m[0] == int(dataset_id)}
    if len(matches) == 1:
        resolved_dataset, resolved_run = next(iter(matches))
        # The saved run id may be historical. Never assign a missing row to a
        # newly generated clip; a later SQLite row could reuse that integer.
        if resolved_run is not None and cloud_runs.get(resolved_run) is None:
            resolved_run = None
        return resolved_dataset, resolved_run
    if claimed:
        raise ValueError('This LoRA cannot be uniquely matched to that video dataset and run.')
    return None, None


def read_best(ds):
    try:
        value = json.loads(ds.best_settings or 'null')
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) and isinstance(value.get('settings'), dict) else None


def best_settings_loras(ds):
    best = read_best(ds)
    name = _name(best['settings'].get('lora')) if best else ''
    return [name] if name else []


def get_dataset(user_id, dataset_id):
    ds = VideoDataset.query.filter_by(id=int(dataset_id), user_id=user_id).first()
    if ds is None:
        raise LookupError('Video dataset not found.')
    return ds


def snapshot(clip):
    try:
        value = json.loads(clip.generation_settings or 'null')
    except (TypeError, ValueError):
        return None
    keys = ('mode', 'aspect', 'seed', 'steps', 'frames', 'megapixels', 'base_model',
            'lora', 'lora_strength', 'accel', 'sparse', 'latent_upscale')
    if not isinstance(value, dict) or any(key not in value for key in keys):
        return None
    return {**{key: value[key] for key in keys},
            **{key: value[key] for key in ('fused', 'h3_attention', 'h3_spectrum',
                                          'h3_video_vae', 'h3_video_writer') if key in value}}


def save_best(user_id, clip_id):
    clip = db.session.get(VideoTestClip, int(clip_id))
    if clip is None:
        raise LookupError('Video clip not found.')
    if clip.mode == 'ref2va' or json.loads(clip.generation_settings or '{}').get('refmods'):
        raise ValueError('Best settings do not support Reference mode yet. Use Reuse to restore this clip and its references.')
    if clip.status != 'done' or not clip.filename:
        raise ValueError('Best settings need a successfully rendered clip.')
    settings = snapshot(clip)
    if settings is None:
        raise ValueError('This older clip has no generation recipe. Generate a new clip to save best settings.')
    if not clip.dataset_id or not clip.lora:
        raise ValueError('Best settings need a LoRA trained on a video dataset in this app.')
    ds_id, run_id = resolve_lora(user_id, clip.lora, run_id=clip.run_id, dataset_id=clip.dataset_id)
    if _name(settings['lora']) != _name(clip.lora):
        raise ValueError('The generation recipe does not match this LoRA.')
    ds = get_dataset(user_id, ds_id)
    try:
        fingerprint = _fingerprint(_deployed_path(_name(clip.lora)))
    except (TypeError, OSError):
        raise ValueError('The deployed LoRA is no longer readable. Try saving best settings again.') from None
    best = {'clip_id': clip.id, 'dataset_id': ds.id, 'run_id': run_id,
            'lora_filename': _name(clip.lora).rsplit('/', 1)[-1], 'settings': settings,
            'lora_sha256': fingerprint,
            'decided_at': datetime.now(timezone.utc).isoformat()}
    ds.best_settings = json.dumps(best)
    db.session.commit()
    return best


def remove_best(user_id, dataset_id):
    ds = get_dataset(user_id, dataset_id)
    ds.best_settings = None
    db.session.commit()
