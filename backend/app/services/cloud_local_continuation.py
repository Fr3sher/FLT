"""Address harvested cloud weights by their saved run, without a cloud provider."""
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid

from .. import config as cfg
from ..extensions import db
from ..models import CloudTrainingRun, TrainingRunRecord
from . import cloud_run_dataset, face_dataset_service as fds


def _refuse():
    raise ValueError('The selected checkpoint no longer belongs to this run. Refresh its checkpoints before continuing.')


def _fingerprint(info):
    # Windows Python 3.12 stat/fstat disagree on deprecated ctime; birthtime
    # names the creation timestamp consistently. Other platforms retain ctime.
    created = getattr(info, 'st_birthtime_ns', info.st_ctime_ns)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, created)


def _stamp(path):
    if path.is_symlink() or path.is_junction():
        _refuse()
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_nlink != 1:
        _refuse()
    return _fingerprint(info)


def resolve_cloud_checkpoint(user_id, dataset_id, family, base, variant,
                             record_id, step):
    """None for a local source; otherwise the exact, still-owned cloud file.

    The record, cloud row and immutable launch selection must all agree. Never
    substitute a same-step checkpoint from the mutable local training lane.
    """
    if record_id is None:
        return None
    if type(record_id) is not int or record_id <= 0:
        _refuse()
    record = db.session.get(TrainingRunRecord, record_id, populate_existing=True)
    if record is None:
        _refuse()
    if record.source == 'local':
        return None
    if (record.source != 'cloud' or record.dataset_id != dataset_id
            or record.family != family or (record.base_model or '') != (base or '')
            or (record.variant or '') != (variant or '')
            or type(record.cloud_run_id) is not int or record.cloud_run_id <= 0
            or type(step) is not int or step <= 0
            or fds.get_dataset(user_id, dataset_id) is None):
        _refuse()
    run = db.session.get(CloudTrainingRun, record.cloud_run_id, populate_existing=True)
    if run is None or not cloud_run_dataset.owns(run, dataset_id):
        _refuse()
    try:
        params = json.loads(run.train_params or '{}')
    except (TypeError, ValueError):
        _refuse()
    if (not isinstance(params, dict) or params.get('training_mode', 'lora') != 'lora'
            or params.get('train_type') != family
            or (params.get('base_model') or '') != (base or '')
            or (params.get('variant') or '') != (variant or '')):
        _refuse()

    # This is the public history reader, also used by the graph. It reads the
    # durable store / legacy staging only; no plugin admission or remote call.
    from .cloud_training import _run_staging_checkpoints
    matches = [item for item in _run_staging_checkpoints(run) if item['step'] == step]
    if not matches:
        _refuse()
    chosen = matches[-1]  # reader orders numbered saves after an equal-step final
    path = Path(chosen['path'])
    run_name = f'run_{run.id}'
    allowed = [cfg.checkpoints_root(create=False) / run_name]
    if run.staging_dir and Path(run.staging_dir).name == run_name:
        allowed.append(Path(run.staging_dir))
    try:
        if (path.name != chosen['filename'] or not any(
                not folder.is_symlink() and not folder.is_junction()
                and path.absolute().parent == folder.absolute()
                and path.resolve().parent == folder.resolve() for folder in allowed)):
            _refuse()
        stamp = _stamp(path)
    except OSError:
        _refuse()
    return {**chosen, 'record_id': record.id, 'source': 'cloud',
            'path': str(path.resolve()), '_source_stamp': stamp}


def seed_cloud_checkpoint(user_id, dataset_id, family, base, variant, chosen):
    """Copy and recheck the addressed file before replacing the local lane.

    Called under the existing launch/queue transaction locks. Source weights
    stay in their cloud store; a previous local lane is archived intact.
    """
    current = resolve_cloud_checkpoint(user_id, dataset_id, family, base, variant,
                                       chosen['record_id'], chosen['step'])
    if current is None or any(current[key] != chosen[key]
                              for key in ('path', '_source_stamp')):
        _refuse()
    from . import lora_training as lt
    ds = fds.get_dataset(user_id, dataset_id)
    folder = lt._run_root(ds, base, family, variant)
    folder.parent.mkdir(parents=True, exist_ok=True)
    lt.assert_free_disk(folder.parent, chosen['_source_stamp'][2] / 1e9
                        + lt.MIN_FREE_GB_TRAIN, 'a cloud checkpoint continuation')
    archived = None
    with tempfile.TemporaryDirectory(prefix='.lds-cloud-resume-', dir=folder.parent) as temp:
        seed = Path(temp)
        trigger = lt._safe_trigger(ds)
        save_root = seed / f'lora_{trigger}'
        save_root.mkdir()
        destination = save_root / f'lora_{trigger}_{chosen["step"]:09d}.safetensors'
        source = Path(current['path'])
        with source.open('rb') as reader, destination.open('xb') as writer:
            opened = os.fstat(reader.fileno())
            stamp = _fingerprint(opened)
            if stamp != current['_source_stamp']:
                _refuse()
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
        if (_stamp(source) != current['_source_stamp']
                or destination.stat().st_size != current['_source_stamp'][2]):
            _refuse()
        verified = resolve_cloud_checkpoint(user_id, dataset_id, family, base, variant,
                                             chosen['record_id'], chosen['step'])
        if verified is None or any(verified[key] != current[key]
                                   for key in ('path', '_source_stamp')):
            _refuse()
        if folder.exists():
            archived = str(folder) + '_superseded_' + uuid.uuid4().hex
            os.rename(folder, archived)
        try:
            os.replace(seed, folder)
        except OSError:
            if archived is not None:
                os.rename(archived, folder)
            raise
    return archived
