"""Named run dataset operations shared with the host; no module handle escapes."""

def dataset_row(run):
    from app.services.cloud_run_dataset import dataset_row, is_video
    from lds_sdk.dataset_exports import DatasetRecord
    row = dataset_row(run)
    if row is None or is_video(run):
        return row
    return DatasetRecord(**{key: getattr(row, key) for key in DatasetRecord.__dataclass_fields__})


def is_video(*args, **kwargs):
    from app.services.cloud_run_dataset import is_video
    return is_video(*args, **kwargs)


def owns(*args, **kwargs):
    from app.services.cloud_run_dataset import owns
    return owns(*args, **kwargs)


def table_of(*args, **kwargs):
    from app.services.cloud_run_dataset import table_of
    return table_of(*args, **kwargs)


from app.services.cloud_run_dataset import VIDEO as VIDEO  # noqa: E402 — stable value/type identity

__all__ = ['dataset_row', 'is_video', 'owns', 'table_of', 'VIDEO']
