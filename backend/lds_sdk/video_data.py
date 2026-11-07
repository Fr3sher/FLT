"""Video historical records and cleanup that remain usable without its package.

Snapshots never carry ORM models or a database session. User-owned lookups
check ownership before returning persisted values; queue completion only updates
its linked historical clip. Database operations join the host current transaction.
"""
from dataclasses import dataclass
from sqlalchemy import select


def _table(name):
    # Metadata owns the durable schema; compatibility with the transitional
    # core mapper requires no import of a product or a second table declaration.
    if name not in {'video_dataset', 'video_test_clip', 'video_checkpoint_preview'}:
        raise ValueError('This historical table is not part of Video.')
    from app.extensions import db
    return db.metadata.tables[name]


@dataclass(frozen=True)
class VideoDatasetRecord:
    id: int
    user_id: str
    name: str
    target_profile: str
    fps: int | None
    frames: int | None
    width: int | None
    height: int | None
    output_dir: str
    trigger_word: str | None
    best_settings: str | None
    created_at: object
    updated_at: object


def get_dataset(user_id, dataset_id):
    video_dataset = _table('video_dataset')
    from app.extensions import db
    row = db.session.execute(select(video_dataset).where(
        video_dataset.c.id == int(dataset_id),
        video_dataset.c.user_id == str(user_id))).mappings().first()
    return VideoDatasetRecord(**dict(row)) if row else None


def historical_dataset(dataset_id):
    """A persisted run's display snapshot; not a user-facing access check."""
    video_dataset = _table('video_dataset')
    from app.extensions import db
    row = db.session.execute(select(video_dataset).where(
        video_dataset.c.id == int(dataset_id))).mappings().first()
    return VideoDatasetRecord(**dict(row)) if row else None


def mark_linked_clip_failed(job_id):
    video_test_clip = _table('video_test_clip')
    from app.extensions import db
    db.session.execute(video_test_clip.update().where(
        video_test_clip.c.job_id == str(job_id)).values(status='failed'))
    db.session.commit()


def delete_dataset_links(connection, dataset_id):
    video_checkpoint_preview = _table('video_checkpoint_preview')
    from ._legacy_schema import video_civitai_link
    connection.execute(video_checkpoint_preview.delete().where(
        video_checkpoint_preview.c.dataset_id == dataset_id))
    connection.execute(video_civitai_link.delete().where(
        video_civitai_link.c.dataset_id == dataset_id))


def delete_clip_links(connection, clip_id):
    video_checkpoint_preview = _table('video_checkpoint_preview')
    connection.execute(video_checkpoint_preview.delete().where(
        video_checkpoint_preview.c.clip_id == clip_id))


__all__ = ['VideoDatasetRecord', 'get_dataset', 'historical_dataset', 'mark_linked_clip_failed', 'delete_dataset_links', 'delete_clip_links']
