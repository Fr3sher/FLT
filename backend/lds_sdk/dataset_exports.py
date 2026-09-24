"""Read-only owned dataset snapshots for external publication/export plugins.

The host retains its caption semantics, reference location and image paths.
The plugin owns the format, consent, destination and network publication.
"""


from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetRecord:
    id: int
    name: str
    trigger_word: str | None
    train_type: str | None
    kind: str | None
    ref_filename: str | None
    subject_type: str | None = None


@dataclass(frozen=True)
class ExportImage:
    id: int
    filename: str | None
    caption: str | None


class DatasetExports:
    def __init__(self, user_id):
        self.user_id = str(user_id)

    def _dataset(self, dataset_id):
        from app.services import face_dataset_service
        return face_dataset_service.get_dataset(self.user_id, dataset_id)

    def get_dataset(self, dataset_id):
        row = self._dataset(dataset_id)
        if row is None:
            return None
        return DatasetRecord(**{key: getattr(row, key) for key in DatasetRecord.__dataclass_fields__})

    def kept_images(self, dataset_id):
        from app.models import FaceDatasetImage
        if self._dataset(dataset_id) is None:
            return ()
        rows = (FaceDatasetImage.query.filter_by(dataset_id=dataset_id, status='keep')
                .order_by(FaceDatasetImage.id.asc()).all())
        return tuple(ExportImage(row.id, row.filename, row.caption) for row in rows)

    def reference_path(self, dataset_id):
        from app.services import face_dataset_service
        row = self._dataset(dataset_id)
        return face_dataset_service._ref_path(row) if row is not None and row.ref_filename else None

    def image_path(self, image_id):
        from lds_sdk.images import DatasetImages
        return DatasetImages(self.user_id).path(image_id)

    def caption(self, dataset_id, caption):
        from app.services import face_dataset_service
        row = self._dataset(dataset_id)
        if row is None:
            raise ValueError('dataset not found')
        return face_dataset_service._export_caption(row, caption)


__all__ = ['DatasetExports']
