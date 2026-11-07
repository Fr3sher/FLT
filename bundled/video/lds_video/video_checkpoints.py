"""Checkpoints & LoRAs of a VIDEO dataset — both lanes in one list, and every
verb the image workspace's Checkpoints section has, at the unit of the STEP.

WHY THE STEP AND NOT THE FILE. A Wan 2.2 checkpoint is two files at one step
(`_high_noise` / `_low_noise`), and every operation that takes a file where it
should take a step gets it wrong without raising: a deploy that puts one expert
in ComfyUI, a delete that leaves the other half on disk, a "continue" that seeds
half a LoRA. So the list is grouped by step (`cloud_video_training.harvested_steps`
already does this for a cloud run; `group_saves_by_step` is that grouping made
shareable with the local folder), and deploy / delete take a step and act on
all of its files. Download stays per file, because two files side by side is
what ai-toolkit wrote and what every loader downstream expects.

WHY ONE LIST FOR TWO LANES. The image workspace shows local saves and cloud
runs' saves in the same section, with the same verbs. The video lane had the
cloud half only, rendered at the tail of the training block with a download link
per file and nothing else — a user who learned "📦 Deploy" on an image dataset
found no such button here (CLAUDE.md's parity rule; maintainer, 2026-09-02).

Deploy goes through the Video Test Studio's own copy (`video_test_studio`):
one folder, one naming, so a LoRA deployed from here is exactly what the
Studio's picker lists as "deployed". Deletes go through the app's trash like the
clips' removal does (`video_bank_service.remove_dataset_clips`) — never
`os.remove` — and a cloud run's per-file delete reuses
`cloud_training.delete_cloud_checkpoint`, which also clears the run's
`checkpoint_local_path` when it pointed at the trashed file.
"""
import json
import os
from pathlib import Path

from lds_sdk import cloud_runs
from lds_video.models import VideoDataset
from lds_sdk.video_host import run_dataset as crd
from lds_sdk import run_history as rg
from lds_video import video_run_lineage as checkpoint_steps
from lds_sdk.video_host import trash
from lds_video import video_targets
from lds_video import video_test_studio as vts
from lds_video import video_training_local as vtl

# Same destination as a removed clip: the app's own trash (Settings ▸ Storage),
# recoverable until it is emptied. Named on every delete answer so the UI's
# wording comes from `utils/deletionWording.js`, never from a hardcoded sentence.
DELETE_MODE = 'app_trash'

# What "ⓘ Details" shows of a cloud run's stamped parameters. An allow-list
# rather than the whole `train_params` blob: `resume_ckpt_paths` are pod-side
# machine paths and `auth_token`-class fields must never leave the row.
_PUBLIC_PARAMS = ('train_type', 'steps', 'base_model', 'low_vram', 'do_i2v',
                  'distillation', 'target_profile', 'frames', 'requested_gpu',
                  'resume_step', 'parent_run_id', 'auto_retry_of',
                  'sample_prompts', 'rank')


def _dataset(user_id, dataset_id):
    ds = VideoDataset.query.filter_by(id=int(dataset_id), user_id=user_id).first()
    if ds is None:
        raise LookupError('video dataset not found')
    return ds


def _cloud_run(ds, run_id):
    """One cloud run OF THIS VIDEO DATASET, active or not, or LookupError.
    Ownership is the (id, table) pair — the face lane shares the id space."""
    try:
        run = cloud_runs.get(int(run_id))
    except (TypeError, ValueError):
        run = None
    if run is None or not crd.owns(run, ds.id, crd.VIDEO):
        raise LookupError('video training run not found')
    return run


def _deployed_index() -> dict:
    """``basename.lower() -> LoraLoader-form name`` of every video LoRA ComfyUI
    can load, from the Studio's own scan — so "deployed" here means exactly
    what the Studio's picker means by it."""
    return {os.path.basename(e['filename']).lower(): e['filename']
            for e in vts.deployed_loras()}


def _undeployable(deployed_as) -> bool:
    """Only a copy sitting in the app's OWN deployment folder is ours to move
    out. A LoRA the user dropped by hand under `h3/` counts as deployed (the
    Studio lists it) but is not something a click in this list may trash."""
    if not deployed_as:
        return False
    sub = os.path.dirname(os.path.normpath(str(deployed_as)))
    return os.path.normcase(sub) == os.path.normcase(os.path.normpath(vts.LORA_SUBDIR))


def _file_row(name, path, deployed) -> dict:
    try:
        size = os.path.getsize(path)
    except OSError:
        size = None
    deployed_as = deployed.get(name.lower())
    return {'filename': name, 'size': size, 'deployed_as': deployed_as,
            'undeployable': _undeployable(deployed_as)}


def _step_rows(steps, paths_of, deployed) -> list:
    """The step groups with each file described (size, deployed state) and the
    step-level `deployed` flag: true only when EVERY file of the step is in
    ComfyUI — half a pair deployed is not a deployed LoRA."""
    out = []
    for s in steps:
        files = [_file_row(n, paths_of(n), deployed) for n in s['files']]
        out.append({'step': s['step'], 'final': bool(s['final']), 'files': files,
                    'deployed': bool(files) and all(f['deployed_as'] for f in files)})
    return out


def _local_saves(ds) -> dict:
    """``{filename: absolute path}`` of this dataset's LOCAL run saves — the
    lane's own listing (`list_run_checkpoints` reads the save root), keyed the
    way `run_checkpoint_files` keys a cloud run's, so both lanes feed one
    grouping."""
    try:
        entries = vtl.list_run_checkpoints(ds.id, ds.user_id)
    except RuntimeError:
        # No local trainer configured on this install (ai-toolkit's output
        # dir is unknown): the local lane simply has no saves to show. The
        # cloud half of the list must not die with it.
        return {}
    return {e['filename']: e['path'] for e in entries}


def local_group(ds, deployed=None) -> dict | None:
    """The local run's saves grouped by step, or None when it has none.

    The FINAL save of a local run is reported with `step: None`: ai-toolkit's
    naming carries no number for it, and unlike a cloud run the local lane
    stamps no `steps` parameter anywhere this list can read without opening
    the run's config — so the label says "Final" and invents no number."""
    saves = _local_saves(ds)
    if not saves:
        return None
    if deployed is None:
        deployed = _deployed_index()
    steps = checkpoint_steps.group_saves_by_step(saves, target=None)
    rows = _step_rows(steps, saves.get, deployed)
    _annotate_steps(ds, None, rows, saves)
    return {
        'run_name': vtl.local_run_name(ds),
        'folder': str(vtl.save_root(ds)),
        'active': bool(vtl.video_training_progress(ds.id, ds.user_id)['active']),
        'steps': rows,
    }


def cloud_groups(ds, deployed=None) -> list:
    """This dataset's cloud runs that brought files back, newest first, each
    with its steps. Same run facts as the training block's own list
    (`/train/cloud/checkpoints`) — that route keeps file NAMES for the block,
    this one describes each file for the section that acts on them."""
    if deployed is None:
        deployed = _deployed_index()
    out = []
    for run in (cloud_runs.for_dataset(ds.id, newest_first=True)):
        if not crd.owns(run, ds.id, crd.VIDEO):
            continue
        steps = checkpoint_steps.harvested_steps(run)
        if not steps:
            continue
        paths = rg.run_checkpoint_files(run)
        rows = _step_rows(steps, paths.get, deployed)
        _annotate_steps(ds, run.id, rows, paths)
        out.append({
            'run_id': run.id, 'status': run.status,
            'active': run.status in rg.ACTIVE_STATES,
            'gpu': run.gpu_name, 'price_per_hour': run.price_per_hour,
            'target_profile': rg.run_param(run, 'target_profile'),
            'parent_run_id': rg.run_param(run, 'parent_run_id'),
            'created_at': run.created_at.isoformat() if run.created_at else None,
            'finished_at': run.finished_at.isoformat() if run.finished_at else None,
            'steps': rows,
        })
    return out


def _annotate_steps(ds, run_id, rows, paths):
    from lds_sdk.video_runtime import annotate_checkpoint_steps
    from lds_video import video_best_settings as best
    chosen = best.read_best(ds)
    for row in rows:
        row['best_settings'] = bool(chosen and chosen.get('run_id') == run_id and any(
            f['filename'] == chosen.get('lora_filename') for f in row['files']))
    # What a plugin knows about a step — the Civitai publisher stamps the
    # version a save IS (`row['civitai']`) — one call per run, never per step.
    stamped = annotate_checkpoint_steps(rows, ds.id, run_id, paths)
    if stamped is not rows and isinstance(stamped, list):
        rows[:] = stamped


def _json_file(path) -> dict:
    try:
        with open(path, encoding='utf-8') as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _params_json(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    return parsed if isinstance(parsed, dict) else {}


def run_provenance(ds, run) -> dict:
    """What a save was trained AS: a cloud run's recorded params (plus the
    target's architecture); for the local run, the job config that ran, then
    its run marker — never the dataset's CURRENT target, which can change after
    training and cannot describe an old save. Read by the graph previews (which
    pipeline can render a step) and by the Civitai publisher (the base model a
    version declares) — the video lane's fact, so the video lane's function."""
    if run is not None:
        params = _params_json(run.train_params)
        profile = video_targets.get(params.get('target_profile')) or {}
        return {**params, 'arch': profile.get('aitk_arch'), 'base_recorded': 'base_model' in params}
    root = Path(vtl.save_root(ds))
    marker = _json_file(root.parent / vtl._RUN_MARKER)
    if marker.get('dataset_id') != ds.id:
        marker = {}
    config = {}
    try:
        from lds_sdk import video_training_runtime as lt
        job = _json_file(Path(lt.jobs_dir()) / f'{vtl.local_run_name(ds)}.json')
        if (job.get('config') or {}).get('name') == vtl.local_run_name(ds):
            processes = job['config'].get('process') or []
            config = processes[0] if processes and isinstance(processes[0], dict) else {}
    except (RuntimeError, TypeError, OSError):
        pass
    model = config.get('model') or {}
    return {'target_profile': marker.get('target_profile'),
            'arch': model.get('arch') or marker.get('arch'),
            'base_model': model.get('name_or_path') or '',
            'base_recorded': bool(model.get('name_or_path')),
            'steps': (config.get('train') or {}).get('steps'),
            'rank': (config.get('network') or {}).get('linear')}


def list_checkpoints(user_id, dataset_id) -> dict:
    """Everything the Checkpoints & LoRAs section renders, in one answer.

    `can_deploy` is whether ComfyUI has a loras root at all on this install —
    the one fact that turns every 📦 into a stated refusal rather than a click
    that fails."""
    from lds_video import video_best_settings as best
    from lds_sdk.video_host import comfy_model_paths
    ds = _dataset(user_id, dataset_id)
    deployed = _deployed_index()
    return {
        'local': local_group(ds, deployed),
        'cloud': cloud_groups(ds, deployed),
        'can_deploy': bool(comfy_model_paths.search_roots('loras')),
        'deploy_folder': vts.LORA_SUBDIR.replace(os.sep, '/'),
        'delete_mode': DELETE_MODE,
        'best_settings': best.read_best(ds),
        'best_settings_loras': best.best_settings_loras(ds),
    }


def _step_files(ds, run_id, step, final) -> list:
    """``[(filename, path)]`` of ONE step of the local run (`run_id` None) or of
    one cloud run of this dataset. A step that is not there is a LookupError —
    a deploy or a delete must never act on "the nearest" save."""
    if run_id is None:
        saves = _local_saves(ds)
        steps = checkpoint_steps.group_saves_by_step(saves, target=None)
        paths = saves
    else:
        run = _cloud_run(ds, run_id)
        steps = checkpoint_steps.harvested_steps(run)
        paths = rg.run_checkpoint_files(run)
    final = bool(final)
    for s in steps:
        if bool(s['final']) != final:
            continue
        if not final and (step is None or int(s['step']) != int(step)):
            continue
        return [(n, paths[n]) for n in s['files'] if n in paths]
    raise LookupError('unknown checkpoint step')


def deploy_step(user_id, dataset_id, run_id, step, final=False) -> dict:
    """📦 Put EVERY file of one step into ComfyUI's loras folder, through the
    Studio's own copy. Answers the LoraLoader-form names it now goes by."""
    ds = _dataset(user_id, dataset_id)
    files = _step_files(ds, run_id, step, final)
    if not files:
        raise LookupError('unknown checkpoint step')
    return {'deployed': [vts.deploy_file(path) for _, path in files],
            'folder': vts.LORA_SUBDIR.replace(os.sep, '/')}


def undeploy(user_id, dataset_id, deployed_as) -> dict:
    """⏏ Move one deployed copy out of ComfyUI (to the trash). The training
    save is untouched — the step offers to deploy again right after."""
    _dataset(user_id, dataset_id)
    return {'removed': vts.undeploy_lora(deployed_as), 'delete_mode': DELETE_MODE}


def delete_step(user_id, dataset_id, run_id, step, final=False) -> dict:
    """🗑 Move every file of one step to the trash — all of a Wan pair, never
    half. Refused while the lane that writes these files is still writing:
    a local training in progress, or a cloud run still on its pod (its sync
    would just bring the file back).

    A file the OS holds open (an antivirus scan, a loader) stays, is counted in
    `files_kept` and named — the answer says what is on disk, not what was
    asked for. The same contract as removing a clip."""
    ds = _dataset(user_id, dataset_id)
    if run_id is None:
        if vtl.video_training_progress(ds.id, ds.user_id)['active']:
            raise RuntimeError('training is running on this set and still writing '
                               'these saves — stop it first')
        run = None
    else:
        run = _cloud_run(ds, run_id)
        if run.status in rg.ACTIVE_STATES:
            raise RuntimeError('this cloud run is still active — its save would '
                               'just be re-synced; stop the run first')
    files = _step_files(ds, run_id, step, final)
    removed, kept = [], []
    for name, path in files:
        try:
            if run is None:
                trash.send_to_trash(path, context=f'videockpt_ds{ds.id}')
            else:
                rg.delete_cloud_checkpoint(ds.id, run.id, name, dataset_table=crd.VIDEO)
        except trash.TrashLockError:
            kept.append(name)
            continue
        except ValueError:
            # Gone between the listing and the click — nothing left to move.
            continue
        removed.append(name)
    return {'removed': removed, 'files_kept': kept, 'delete_mode': DELETE_MODE}


def local_checkpoint_path(user_id, dataset_id, filename) -> str | None:
    """Resolve ONE local save by basename, or None. Resolved through the run's
    own listing, so a request can never point this at a path of its choosing —
    the cloud download's rule (`run_checkpoint_path`), applied to the folder."""
    ds = _dataset(user_id, dataset_id)
    if not filename or os.path.basename(filename) != filename:
        return None
    path = _local_saves(ds).get(filename)
    return path if path and os.path.isfile(path) else None


def run_details(user_id, dataset_id, run_id) -> dict:
    """ⓘ What one cloud run of this dataset was: its status line, its timing,
    its GPU and price, its genealogy, and the parameters it was launched with
    (allow-listed — see `_PUBLIC_PARAMS`)."""
    ds = _dataset(user_id, dataset_id)
    run = _cloud_run(ds, run_id)
    try:
        params = json.loads(run.train_params or '{}')
    except ValueError:
        params = {}
    return {
        'run_id': run.id, 'status': run.status,
        'phase_detail': run.phase_detail or '', 'error': run.error,
        'run_name': run.run_name, 'gpu': run.gpu_name,
        'price_per_hour': run.price_per_hour,
        'created_at': run.created_at.isoformat() if run.created_at else None,
        'finished_at': run.finished_at.isoformat() if run.finished_at else None,
        'parent_run_id': params.get('parent_run_id'),
        'saves': len(rg.run_checkpoint_files(run)),
        'params': {k: params[k] for k in _PUBLIC_PARAMS if k in params},
    }
