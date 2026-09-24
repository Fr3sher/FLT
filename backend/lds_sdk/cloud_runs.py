"""Persistent cloud history for the local profile, independent of the plugin.

These are historical facts the core must retain while Cloud is OFF. No rental
credentials, pod connection details or mapped model cross this interface.
Operational cloud lifecycle changes belong to Cloud's own mapped model.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
import json
import uuid

__all__ = ['CloudRunRecord', 'get', 'all_runs', 'by_ids', 'for_dataset', 'with_statuses', 'delete_publication_links',
           'count_with_statuses', 'update_checkpoint_path', 'update_artifact_identity',
           'by_preview_key', 'ensure_video_preview_key', 'mark_dataset_deleted', 'delete_video_run']


@dataclass(frozen=True)
class CloudRunRecord:
    id: int
    video_preview_key: str | None
    dataset_id: int
    dataset_table: str | None
    run_name: str | None
    status: str | None
    phase_detail: str | None
    gpu_name: str | None
    price_per_hour: float | None
    staging_dir: str | None
    checkpoint_local_path: str | None
    train_params: str | None
    error: str | None
    created_at: datetime | None
    updated_at: datetime | None
    finished_at: datetime | None


def _host():
    from app.extensions import db
    from ._legacy_schema import cloud_training_run
    return db.session, cloud_training_run


def _rows(*conditions, newest_first=False, limit=None):
    session, table = _host()
    query = select(*(table.c[name] for name in CloudRunRecord.__dataclass_fields__)).where(*conditions)
    query = query.order_by(table.c.id.desc() if newest_first else table.c.id.asc())
    if limit is not None:
        query = query.limit(max(0, int(limit)))
    return [CloudRunRecord(**dict(row, train_params=_public_params(row['train_params'])))
            for row in session.execute(query).mappings()]


def _public_params(raw):
    """Rental observations belong to the provider, not historical recipes."""
    try:
        params = json.loads(raw or '{}')
    except (TypeError, ValueError):
        return raw
    if not isinstance(params, dict) or not any(k.startswith('_lds_rental_') for k in params):
        return raw
    return json.dumps({k: v for k, v in params.items() if not k.startswith('_lds_rental_')})


def get(run_id):
    if run_id is None:
        return None
    _, table = _host()
    rows = _rows(table.c.id == int(run_id), limit=1)
    return rows[0] if rows else None


def by_preview_key(key):
    _, table = _host()
    rows = _rows(table.c.video_preview_key == str(key), limit=1)
    return rows[0] if rows else None


def _dataset_pair(table, dataset_id, dataset_table):
    if dataset_table not in {'face_dataset', 'video_dataset'}:
        raise ValueError('Unknown dataset table.')
    return (table.c.dataset_id == int(dataset_id),
            func.coalesce(table.c.dataset_table, 'face_dataset') == dataset_table)


def ensure_video_preview_key(run_id, dataset_id, dataset_table):
    """Assign a non-reusable preview identity inside the caller's transaction."""
    from app.services.cloud_run_dataset import owns
    run = get(run_id)
    if run is None or not owns(run, dataset_id, dataset_table):
        return None
    session, table = _host()
    session.execute(table.update().where(table.c.id == int(run_id),
        *_dataset_pair(table, dataset_id, dataset_table),
        table.c.video_preview_key.is_(None)).values(video_preview_key=str(uuid.uuid4())))
    return get(run_id).video_preview_key


def mark_dataset_deleted(dataset_id, dataset_table):
    """Tombstone history before deleting a dataset, without committing the caller."""
    session, table = _host()
    # Maintenance reads the original params: public snapshots deliberately
    # omit provider metadata and must not be written back over its facts.
    rows = session.execute(select(table.c.id, table.c.train_params).where(
        *_dataset_pair(table, dataset_id, dataset_table))).mappings()
    for run in rows:
        try:
            params = json.loads(run['train_params'] or '{}')
        except (ValueError, TypeError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        params['dataset_deleted'] = True
        session.execute(table.update().where(table.c.id == run['id']).values(train_params=json.dumps(params)))


def all_runs(*, newest_first=False, limit=None):
    return _rows(newest_first=newest_first, limit=limit)


def by_ids(run_ids):
    _, table = _host()
    return _rows(table.c.id.in_(list(run_ids)))


def for_dataset(dataset_id, *, newest_first=False, dataset_table=None):
    _, table = _host()
    conditions = [table.c.dataset_id == int(dataset_id)]
    if dataset_table is not None:
        if dataset_table not in {'face_dataset', 'video_dataset'}:
            raise ValueError('Unknown dataset table.')
        conditions.append(func.coalesce(table.c.dataset_table, 'face_dataset') == dataset_table)
    return _rows(*conditions, newest_first=newest_first)


def with_statuses(statuses, *, dataset_id=None):
    _, table = _host()
    conditions = [table.c.status.in_(tuple(statuses))]
    if dataset_id is not None:
        conditions.append(table.c.dataset_id == int(dataset_id))
    return _rows(*conditions)


def count_with_statuses(statuses):
    session, table = _host()
    return int(session.execute(select(func.count()).select_from(table).where(
        table.c.status.in_(tuple(statuses)))).scalar_one())


def update_artifact_identity(run_id, **changes):
    """Update only local artifact identity inside the host's current transaction.

    The caller has already performed the file rename/move and owns its enclosing
    commit/rollback. Rental state, credentials and training parameters cannot be
    modified through this historical maintenance operation.
    """
    if not changes or set(changes) - {'run_name', 'staging_dir', 'checkpoint_local_path'}:
        raise ValueError('Only local artifact identity can be updated here.')
    session, table = _host()
    from app.utils.timestamps import naive_utcnow
    session.execute(table.update().where(table.c.id == int(run_id)).values(
        **changes, updated_at=naive_utcnow()))


def update_checkpoint_path(run_id, path):
    update_artifact_identity(run_id, checkpoint_local_path=path)


def delete_publication_links(connection, run_id):
    """ORM delete hook: detach persistent publication facts in that transaction."""
    from ._legacy_schema import video_civitai_link
    connection.execute(video_civitai_link.delete().where(
        video_civitai_link.c.source_key == f'cloud:{int(run_id)}'))


def delete_video_run(user_id, dataset_id, run_id):
    """Delete released terminal video history and local files, even Cloud OFF."""
    from app.services.cloud_history import delete_video_run as operation
    return operation(user_id, dataset_id, run_id)
