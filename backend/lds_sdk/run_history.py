"""Durable checkpoint history and artifact operations shared with products.

These named operations retain history while a training provider is absent.
No provider module, credential, or host ORM model is exported.
"""

ACTIVE_STATES = frozenset({'preparing', 'provisioning', 'uploading', 'training', 'downloading', 'terminating'})

DENSE_ON_DISK = 'local'
DENSE_ON_HUB = 'hub'
DENSE_GONE = 'none'

__all__ = ['checkpoint_store_dir', 'run_checkpoint_files', 'run_checkpoint_path', 'adopt_checkpoints_into_store', 'run_param', 'run_family', 'run_training_mode', 'is_full_transformer_run', 'dense_artifact_state', 'latest_run_for', 'run_for', 'is_locked_error', 'cloud_resume_state', 'run_staging_checkpoints', 'cost_estimate', 'dataset_name', 'staging_save_count', 'latest_sample_name', 'run_samples_dir', 'record_id_for_cloud', 'gallery_image', 'delete_cloud_checkpoint', 'ACTIVE_STATES', 'DENSE_ON_DISK', 'DENSE_ON_HUB', 'DENSE_GONE']



def checkpoint_store_dir(run, create=False):
    from app.services.cloud_training import checkpoint_store_dir as operation
    return operation(run, create)



def run_checkpoint_files(run):
    from app.services.cloud_training import run_checkpoint_files as operation
    return operation(run)



def run_checkpoint_path(run, filename):
    from app.services.cloud_training import run_checkpoint_path as operation
    return operation(run, filename)



def adopt_checkpoints_into_store(run):
    from app.services.cloud_training import _adopt_checkpoints_into_store as operation
    return operation(run)



def run_param(run, key):
    from app.services.cloud_training import _run_param as operation
    return operation(run, key)



def run_family(run):
    from app.services.cloud_training import _run_family as operation
    return operation(run)



def run_training_mode(run):
    from app.services.cloud_training import _run_training_mode as operation
    return operation(run)



def is_full_transformer_run(run):
    from app.services.cloud_training import _is_full_transformer_run as operation
    return operation(run)



def dense_artifact_state(run):
    from app.services.cloud_training import dense_artifact_state as operation
    return operation(run)



def latest_run_for(dataset_id, train_type=None, dataset_table='face_dataset'):
    from app.services.cloud_training import latest_run_for as operation
    return operation(dataset_id, train_type, dataset_table)



def run_for(dataset_id, run_id=None, train_type=None, dataset_table='face_dataset'):
    from app.services.cloud_training import run_for as operation
    return operation(dataset_id, run_id, train_type, dataset_table)



def is_locked_error(exc):
    from app.services.cloud_training import _is_locked_error as operation
    return operation(exc)



def cloud_resume_state():
    from app.services.cloud_training import _cloud_resume_state as operation
    return operation()



def run_staging_checkpoints(run):
    from app.services.cloud_training import _run_staging_checkpoints as operation
    return operation(run)



def cost_estimate(run):
    from app.services.cloud_training import _cost_estimate as operation
    return operation(run)



def dataset_name(dataset_id):
    from app.services.cloud_training import _dataset_name as operation
    return operation(dataset_id)



def staging_save_count(run):
    from app.services.cloud_training import _staging_save_count as operation
    return operation(run)



def latest_sample_name(samples_dir):
    from app.services.cloud_training import _latest_sample_name as operation
    return operation(samples_dir)



def run_samples_dir(crun, rec):
    from app.services.cloud_training import _run_samples_dir as operation
    return operation(crun, rec)



def record_id_for_cloud(cloud_run_id):
    from app.services.cloud_training import _record_id_for_cloud as operation
    return operation(cloud_run_id)



def gallery_image(r):
    from app.services.cloud_training import gallery_image as operation
    return operation(r)



def delete_cloud_checkpoint(dataset_id, run_id, filename, dataset_table='face_dataset'):
    from app.services.cloud_training import delete_cloud_checkpoint as operation
    return operation(dataset_id, run_id, filename, dataset_table)
