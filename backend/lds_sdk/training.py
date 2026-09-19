"""Read-only training provenance and host checkpoint locations for one user.

These snapshots contain persisted training facts, not ORM/session handles or
cloud credentials. Publication formatting and choosing which save to publish
belong to the consumer plugin.
"""

from dataclasses import dataclass

__all__ = ['RunRecord', 'TrainingHistory', 'family_label', 'network_geometry',
           'split_checkpoint_name']


@dataclass(frozen=True)
class RunRecord:
    id: int
    dataset_id: int
    family: str
    source: str
    cloud_run_id: int | None
    base_model: str | None
    variant: str | None
    masked: bool | None
    steps: int | None
    manifest: str | None
    settings: str | None
    version: int


class TrainingHistory:
    def __init__(self, user_id):
        self.user_id = str(user_id)

    def record(self, record_id):
        from app.extensions import db
        from app.models import TrainingRunRecord
        from app.services import face_dataset_service as datasets
        row = db.session.get(TrainingRunRecord, int(record_id))
        if row is None or not datasets.get_dataset(self.user_id, row.dataset_id):
            return None
        return RunRecord(**{key: getattr(row, key) for key in RunRecord.__dataclass_fields__})

    def cloud_checkpoint_files(self, record_id):
        from app.extensions import db
        from app.models import CloudTrainingRun
        from app.services import cloud_run_dataset, cloud_training
        record = self.record(record_id)
        if record is None or record.source != 'cloud' or not record.cloud_run_id:
            return None
        run = db.session.get(CloudTrainingRun, record.cloud_run_id)
        if run is None or not cloud_run_dataset.owns(run, record.dataset_id):
            return None
        return dict(cloud_training.run_checkpoint_files(run))

    def local_checkpoints(self, record_id):
        from app.services import lora_training
        record = self.record(record_id)
        if record is None:
            return ()
        return tuple(dict(row) for row in lora_training.list_checkpoints(
            self.user_id, record.dataset_id, record.base_model or '', record.family, record.variant))

    def local_checkpoint_path(self, record_id, filename):
        from app.services import lora_training
        record = self.record(record_id)
        if record is None:
            return None
        return lora_training.checkpoint_file_path(
            self.user_id, record.dataset_id, filename, record.base_model or '', record.family, record.variant)


def family_label(family):
    from app.services.lora_training import _FAMILY_LABEL
    return _FAMILY_LABEL.get(str(family or '').lower(), str(family or 'LoRA'))


def network_geometry(record):
    from app.services.checkpoint_registry import network_geometry as resolve
    return dict(resolve(record))


def split_checkpoint_name(name):
    from app.services.video_training import split_checkpoint_name as split
    return split(name)


def active_states():
    from app.services.cloud_training import ACTIVE_STATES
    return frozenset(ACTIVE_STATES)

__all__.append("active_states")
