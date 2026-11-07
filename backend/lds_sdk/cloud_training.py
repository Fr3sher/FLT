"""Local cloud-run history plus explicit dispatch to the active rental product.

History helpers never rent, supervise or terminate a provider instance. Video's
local checkpoint views remain available when the Cloud product is disabled.
"""
from app.services.cloud_training import (
    ACTIVE_STATES, _run_param, cfg, checkpoint_store_dir, latest_run_for,
    run_checkpoint_files, run_checkpoint_path,
)
from lds_sdk.lifecycle import is_available, state_change_lock

__all__ = ['ACTIVE_STATES', '_run_param', 'cfg', 'checkpoint_store_dir',
           'delete_cloud_checkpoint', 'get_active_runs', 'latest_run_for',
           'month_spend_usd', 'run_checkpoint_files', 'run_checkpoint_path', 'get_run',
           'full_transformer_token_preflight']


def get_run(user_id, run_id, *, dataset_id, dataset_table):
    """Read the one main mapper through dataset type and user ownership checks."""
    from app.extensions import db
    from app.models import CloudTrainingRun
    from app.services import cloud_run_dataset
    try:
        if isinstance(run_id, bool):
            return None
        run = db.session.get(CloudTrainingRun, int(run_id))
    except (TypeError, ValueError):
        return None
    if run is None or not cloud_run_dataset.owns(run, dataset_id, dataset_table):
        return None
    dataset = cloud_run_dataset.dataset_row(run)
    return run if dataset is not None and dataset.user_id == user_id else None


def _active_product():
    if not is_available('cloud_training'):
        raise RuntimeError('Cloud training is disabled or unavailable')
    # Resolve only after admission; importing this SDK never imports a product.
    from lds_cloud_training import cloud_training
    return cloud_training


def delete_cloud_checkpoint(*args, **kwargs):
    with state_change_lock:
        _active_product()
        # This moves an already downloaded, terminal run's file to local trash.
        # Keep main's type/whitelist guards; the rental product has no duplicate
        # implementation of this historical storage primitive.
        from app.services.cloud_training import delete_cloud_checkpoint as delete_local
        return delete_local(*args, **kwargs)


def get_active_runs(*args, **kwargs):
    return _active_product().get_active_runs(*args, **kwargs)


def month_spend_usd(*args, **kwargs):
    return _active_product().month_spend_usd(*args, **kwargs)


def full_transformer_token_preflight(*args, **kwargs):
    with state_change_lock:
        return _active_product().full_transformer_token_preflight(*args, **kwargs)
