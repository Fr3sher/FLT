"""Named shared operations for dataset_activity."""

from app.services.dataset_activity import DatasetActivityBusy

__all__ = ['begin_exclusive', 'progress', 'end', 'DatasetActivityBusy']



def begin_exclusive(dataset_id, kind, total=0, detail=None, engine=None):
    from app.services.dataset_activity import begin_exclusive as operation
    return operation(dataset_id, kind, total, detail, engine)



def progress(token, done=None, total=None, detail=None):
    from app.services.dataset_activity import progress as operation
    return operation(token, done, total, detail)



def end(token):
    from app.services.dataset_activity import end as operation
    return operation(token)
