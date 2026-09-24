"""Video publication API v1: read-only product facts for another plugin.

This facade owns the video-specific resolvers. Callers receive immutable
snapshots and explicit file lists, never mapped models or arbitrary modules.
Every operation resolves current ownership again, including the dataset/table
pair and a deleted dataset's tombstone on its historical cloud runs.
"""

from dataclasses import dataclass

API_VERSION = 1


@dataclass(frozen=True)
class Dataset:
    id: int
    user_id: str
    name: str
    trigger_word: str | None


@dataclass(frozen=True)
class Run:
    id: int
    status: str


def dataset(user_id, dataset_id):
    from . import video_checkpoints
    row = video_checkpoints._dataset(user_id, dataset_id)
    return Dataset(row.id, row.user_id, row.name, row.trigger_word)


def cloud_run(user_id, dataset_id, run_id):
    from . import video_checkpoints
    row = video_checkpoints._cloud_run(video_checkpoints._dataset(user_id, dataset_id), run_id)
    return Run(row.id, row.status)


def provenance(user_id, dataset_id, run_id):
    from . import video_checkpoints
    ds = video_checkpoints._dataset(user_id, dataset_id)
    run = video_checkpoints._cloud_run(ds, run_id) if run_id is not None else None
    return dict(video_checkpoints.run_provenance(ds, run))


def step_files(user_id, dataset_id, run_id, step, final):
    from . import video_checkpoints
    ds = video_checkpoints._dataset(user_id, dataset_id)
    return tuple(video_checkpoints._step_files(ds, run_id, step, final))


def training_progress(user_id, dataset_id):
    from . import video_checkpoints, video_training_local
    ds = video_checkpoints._dataset(user_id, dataset_id)
    return dict(video_training_local.video_training_progress(ds.id, ds.user_id))


def verified_base(arch):
    from . import video_training
    return video_training._VERIFIED_BASES.get(arch)


def split_checkpoint_name(name):
    from . import video_training
    return video_training.split_checkpoint_name(name)


def is_multistage_arch(arch):
    from . import video_training
    return video_training.is_multistage_arch(arch)
