"""Durable dataset-table identity shared by cloud providers and history."""
from app.services.cloud_run_dataset import FACE, VIDEO, is_video, table_of, owns

__all__ = ['FACE', 'VIDEO', 'is_video', 'table_of', 'owns', 'dataset_row', 'display_name']


def dataset_row(run):
    if is_video(run):
        from .video_data import get_dataset
    else:
        from .training_data import get_dataset
    from .config import local_user
    return get_dataset(local_user(), run.dataset_id)


def display_name(run):
    row = dataset_row(run)
    return getattr(row, 'name', None) if row is not None else None
