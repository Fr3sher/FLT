"""Owned host image collections and gallery records for media integration.

Identifiers are re-authorized against the user on every call. Results are frozen
snapshots, paths or dictionaries; no host ORM class/session escapes this module.
"""
from dataclasses import dataclass
from pathlib import Path


class LibraryFileUnavailable(LookupError):
    """An owned library row exists, but its file is missing or outside its root."""


@dataclass(frozen=True)
class LibraryRecord:
    id: int
    bank_id: int | None = None
    dataset_id: int | None = None
    filename: str | None = None
    relpath: str | None = None


def _models(source):
    from app.models import ImageBank, BankImage, FaceDataset, FaceDatasetImage, LoraTestImage
    choices = {'bank': (ImageBank, BankImage), 'dataset': (FaceDataset, FaceDatasetImage),
               'gallery': (FaceDataset, LoraTestImage)}
    if source not in choices:
        raise ValueError('Unknown image library.')
    return choices[source]


def _query(user_id, source):
    parent, model = _models(source)
    query = model.query.join(parent).filter(parent.user_id == str(user_id))
    if source == 'dataset':
        query = query.filter(model.filename.isnot(None), model.status.in_(('keep', 'reject')))
    elif source == 'gallery':
        query = query.filter(model.filename.isnot(None), model.status == 'done')
    return query, parent, model


def _collection(user_id, source, collection_id):
    parent, _ = _models(source)
    row = parent.query.filter_by(id=int(collection_id), user_id=str(user_id)).first()
    if row is None:
        raise LookupError('Library collection not found.')
    return row


def list_images(user_id, source, *, collection_id=None, offset=0, limit=40, q=''):
    if (isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 60
            or isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 100000
            or not isinstance(q, str) or len(q) > 200):
        raise ValueError('Invalid image-library page.')
    query, parent, model = _query(user_id, source)
    collections = []
    if source != 'gallery':
        collections = [{'id': row.id, 'label': row.name} for row in parent.query.filter_by(
            user_id=str(user_id)).order_by(parent.name, parent.id).limit(200)]
        if collection_id not in (None, ''):
            container = _collection(user_id, source, collection_id)
            column = model.bank_id if source == 'bank' else model.dataset_id
            query = query.filter(column == container.id)
    elif collection_id not in (None, ''):
        raise ValueError('This library has no collection selector.')
    if q.strip():
        escaped = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        label = model.relpath if source == 'bank' else model.filename
        query = query.filter(label.ilike('%' + escaped + '%', escape='\\'))
    rows = query.order_by(model.id.desc()).offset(offset).limit(limit + 1).all()
    return {'collections': collections, 'rows': tuple(LibraryRecord(**{
        key: getattr(row, key, None) for key in LibraryRecord.__dataclass_fields__}) for row in rows)}


def image_path(user_id, source, image_id, *, collection_id=None):
    query, _, model = _query(user_id, source)
    row = query.filter(model.id == int(image_id)).first()
    if row is None:
        raise LookupError('Library image not found.')
    if source != 'gallery':
        parent = _collection(user_id, source, collection_id)
        actual = row.bank_id if source == 'bank' else row.dataset_id
        if parent.id != actual:
            raise LookupError('Library image not found in this collection.')
    elif collection_id is not None:
        raise ValueError('This image has no collection selector.')
    if source == 'bank':
        from app.services import image_bank_service as banks
        path = banks.resolved_image_path(parent, row)
        roots = [parent.source_path, banks._bank_dir(parent.id)]
    else:
        from app.services.dataset_storage import dataset_path
        root = dataset_path(row.dataset_id)
        path, roots = Path(root) / row.filename, [root]
    target = Path(path).resolve() if path else None
    if target is None or not target.is_file() or not any(target.is_relative_to(Path(root).resolve()) for root in roots):
        raise LibraryFileUnavailable('That library file is no longer available.')
    return target


def source_metadata_storage(metadata, *, image_url=None):
    from app.services.face_dataset_service import _source_metadata_storage
    return _source_metadata_storage(metadata, image_url=image_url)


def similarity_push_down_weight(*args, **kwargs):
    from app.services.image_bank_service import _push_down_weight
    return _push_down_weight(*args, **kwargs)


__all__ = ['LibraryFileUnavailable', 'LibraryRecord', 'list_images', 'image_path', 'source_metadata_storage', 'similarity_push_down_weight']
