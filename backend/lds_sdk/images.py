"""Owned image snapshots and bounded writes into LDS's existing media tables.

The public records are immutable values, never SQLAlchemy models or sessions.
The two repositories intentionally keep their different states: a completed
gallery render is done; a dataset candidate stays pending for keep/reject.
No image-generation policy or plugin workflow belongs in these adapters.
"""


from dataclasses import dataclass


import os


@dataclass(frozen=True)
class ImageRecord:
    id: int
    dataset_id: int
    status: str
    filename: str | None
    derivation_kind: str | None
    parent_image_id: int | None
    camera_pose: str | None
    job_id: str | None


def _snapshot(row):
    if row is None:
        return None
    return ImageRecord(**{name: getattr(row, name) for name in ImageRecord.__dataclass_fields__})


def _host():
    from app.extensions import db
    from app.services import face_dataset_service
    return db, face_dataset_service


class GalleryImages:
    """Gallery records owned through their parent dataset, for one user."""

    def __init__(self, user_id):
        self.user_id = str(user_id)

    def _row(self, image_id):
        from app.models import LoraTestImage
        db, datasets = _host()
        row = db.session.get(LoraTestImage, image_id, populate_existing=True)
        return row if row is not None and datasets.get_dataset(self.user_id, row.dataset_id) else None

    def get(self, image_id):
        return _snapshot(self._row(image_id))

    def path(self, image_id):
        row = self._row(image_id)
        if row is None or not row.filename:
            return None
        _, datasets = _host()
        return os.path.join(datasets._dataset_dir(row.dataset_id), row.filename)

    def create_derivative(self, source_id, *, derivation_kind, prompt):
        """Create a pending same-gallery derivative, outside the training timeline."""
        from app.models import LoraTestImage
        db, _ = _host()
        source = self._row(source_id)
        if source is None:
            return None
        row = LoraTestImage(
            dataset_id=source.dataset_id, checkpoint=source.checkpoint,
            strength=source.strength, status='pending', filename=None,
            record_id=source.record_id, step=source.step, run_id=None,
            seed=source.seed, prompt=prompt[:500], parent_image_id=source.id,
            derivation_kind=derivation_kind)
        db.session.add(row)
        db.session.commit()
        return _snapshot(row)

    def attach_job(self, image_id, job_id, *, camera_pose=None):
        db, _ = _host()
        row = self._row(image_id)
        if row is None:
            return False
        row.job_id, row.camera_pose = job_id, camera_pose
        db.session.commit()
        return True

    def discard_unqueued(self, image_id):
        """Remove a failed admission only; never delete a live or finished result."""
        db, _ = _host()
        row = self._row(image_id)
        if row is None or row.status != 'pending' or row.filename or row.job_id:
            return False
        db.session.delete(row)
        db.session.commit()
        return True


class DatasetImages:
    """Dataset image candidates with the host's ownership/activity semantics."""

    def __init__(self, user_id):
        self.user_id = str(user_id)

    def _row(self, image_id):
        _, datasets = _host()
        row = datasets._live_image_row(image_id)
        return row if row is not None and datasets.get_dataset(self.user_id, row.dataset_id) else None

    def get(self, image_id):
        return _snapshot(self._row(image_id))

    def path(self, image_id):
        _, datasets = _host()
        row = self._row(image_id)
        return datasets._img_path(row) if row is not None and row.filename else None

    def require_editable(self, dataset_id):
        _, datasets = _host()
        if not datasets.get_dataset(self.user_id, dataset_id):
            raise ValueError('dataset not found')
        datasets._guard_not_bank_export(dataset_id)

    @property
    def max_fanout(self):
        _, datasets = _host()
        return datasets.MAX_FANOUT

    def pending_count(self, dataset_id):
        from app.models import FaceDatasetImage
        _, datasets = _host()
        if not datasets.get_dataset(self.user_id, dataset_id):
            raise ValueError('dataset not found')
        return (FaceDatasetImage.query.filter_by(dataset_id=dataset_id, status='pending')
                .filter(FaceDatasetImage.filename.is_(None)).count())

    def create_derivative(self, source_id, *, derivation_kind, camera_pose=None,
                          generation_meta=None, variation_prompt=None, caption=None):
        """Persist a generated candidate before enqueue; leave caption origin unset.

        camera_pose is an existing nullable LDS provenance column. Its vocabulary
        and interpretation belong to the contributing plugin, not the SDK.
        """
        from app.models import FaceDatasetImage
        db, _ = _host()
        source = self._row(source_id)
        if source is None:
            return None
        self.require_editable(source.dataset_id)
        row = FaceDatasetImage(
            dataset_id=source.dataset_id, source='generated', status='pending',
            parent_image_id=source.id, derivation_kind=derivation_kind,
            camera_pose=camera_pose, generation_meta=generation_meta,
            variation_prompt=variation_prompt, caption=caption)
        db.session.add(row)
        db.session.commit()
        return _snapshot(row)

    def attach_job(self, image_id, job_id):
        db, _ = _host()
        row = self._row(image_id)
        if row is None:
            return False
        row.job_id = job_id
        db.session.commit()
        return True

    def fail_unqueued(self, image_id, reason):
        db, _ = _host()
        row = self._row(image_id)
        if row is None or row.status != 'pending' or row.filename or row.job_id:
            return False
        row.status, row.fail_reason = 'failed', reason
        db.session.commit()
        return True

    def sync_activity(self, dataset_id):
        _, datasets = _host()
        if datasets.get_dataset(self.user_id, dataset_id):
            datasets._sync_generate_activity(dataset_id)


def generation_metadata(**facts):
    """Serialize the host's provenance vocabulary, omitting unknown/empty facts."""
    _, datasets = _host()
    return datasets._generation_meta_json(**facts)


__all__ = ['DatasetImages', 'GalleryImages', 'generation_metadata']
