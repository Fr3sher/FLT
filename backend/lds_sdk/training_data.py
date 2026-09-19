"""Immutable dataset recipes and provenance records for training providers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetRecipe:
    id: object = None
    user_id: object = None
    name: object = None
    trigger_word: object = None
    ref_filename: object = None
    ref_original_filename: object = None
    ref_extra_filenames: object = None
    best_settings: object = None
    train_base_model: object = None
    train_variant: object = None
    train_vae_path: object = None
    train_te_path: object = None
    train_family_bases: object = None
    train_family_settings: object = None
    train_settings: object = None
    train_slider: object = None
    train_type: object = None
    training_mode: object = None
    kind: object = None
    subject_type: object = None
    fidelity: object = None
    concept_desc: object = None
    concept_terms: object = None
    prompt_suffix: object = None
    prompt_suffixes: object = None
    caption_options: object = None
    klein_model: object = None
    created_at: object = None
    updated_at: object = None


@dataclass(frozen=True)
class TrainingRecord:
    id: object = None
    dataset_id: object = None
    family: object = None
    source: object = None
    cloud_run_id: object = None
    base_model: object = None
    variant: object = None
    masked: object = None
    steps: object = None
    fingerprint: object = None
    manifest: object = None
    settings: object = None
    snapshot: object = None
    version: object = None
    parent_record_id: object = None
    resumed_from: object = None
    lineage_origin: object = None
    note: object = None
    created_at: object = None


def _snapshot(row, cls):
    return cls(**{name: getattr(row, name) for name in cls.__dataclass_fields__}) if row is not None else None


def get_dataset(user_id, dataset_id):
    from app.services.face_dataset_service import get_dataset as operation
    return _snapshot(operation(user_id, dataset_id), DatasetRecipe)


def list_datasets(user_id):
    from app.services.face_dataset_service import list_datasets as operation
    return tuple(_snapshot(row, DatasetRecipe) for row in operation(user_id))


def normalize_train_type(value):
    from app.services.face_dataset_service import normalize_train_type as operation
    return operation(value)


def dataset_ingest_lock(user_id, dataset_id):
    from app.services.face_dataset_service import _dataset_ingest_lock
    return _dataset_ingest_lock(user_id, dataset_id)


def remember_selection(user_id, dataset_id, *, family, variant, training_mode):
    from app.extensions import db
    from app.services.face_dataset_service import get_dataset as operation
    row = operation(user_id, dataset_id)
    if row is None:
        raise ValueError('dataset not found')
    row.train_type, row.train_variant, row.training_mode = family, variant, training_mode
    db.session.commit()
    return _snapshot(row, DatasetRecipe)


def record_by_id(record_id):
    from app.services.checkpoint_registry import record_by_id as operation
    return _snapshot(operation(record_id), TrainingRecord)


def record_for_cloud(run_id):
    if run_id is None:
        return None
    from app.models import TrainingRunRecord
    row = (TrainingRunRecord.query.filter_by(cloud_run_id=int(run_id))
           .order_by(TrainingRunRecord.id.desc()).first())
    return _snapshot(row, TrainingRecord)


def recent_records(limit=20):
    from app.models import TrainingRunRecord
    rows = TrainingRunRecord.query.order_by(TrainingRunRecord.id.desc()).limit(max(1, min(int(limit), 100))).all()
    return tuple(_snapshot(row, TrainingRecord) for row in rows)


def newest_record_for(dataset_id, family, base_model='', variant=None):
    from app.services.checkpoint_registry import newest_record_for as operation
    return _snapshot(operation(dataset_id, family, base_model, variant), TrainingRecord)


def prepare_launch(user_id, dataset_id, base_model=None):
    from app.services.checkpoint_registry import prepare_launch as operation
    prepared = operation(user_id, dataset_id, base_model)
    if prepared is None:
        return None
    return {**prepared, 'ds': _snapshot(prepared['ds'], DatasetRecipe),
            'sig_updates': [(row.id, sig, stat) for row, sig, stat in (prepared.get('sig_updates') or ())]}


def register_launch(user_id, dataset_id, family, source, base_model='',
                    variant=None, masked=True, steps=None, cloud_run_id=None,
                    settings=None, parent_record_id=None, resumed_from=None, prepared=None):
    from app.extensions import db
    from app.models import FaceDatasetImage
    from app.services.checkpoint_registry import register_launch as operation
    if prepared is not None:
        if not get_dataset(user_id, dataset_id) or prepared['ds'].id != dataset_id:
            raise ValueError('dataset not found')
        updates = []
        for image_id, sig, stat in prepared.get('sig_updates') or ():
            row = db.session.get(FaceDatasetImage, image_id)
            if row is None or row.dataset_id != int(dataset_id):
                raise ValueError('Image does not belong to this dataset.')
            updates.append((row, sig, stat))
        prepared = {**prepared, 'sig_updates': updates}
    record = operation(user_id, dataset_id, family, source, base_model, variant, masked,
                       steps, cloud_run_id, settings, parent_record_id, resumed_from, prepared)
    return _snapshot(record, TrainingRecord)


def prepared_generation_identity(prepared):
    from app.services.checkpoint_registry import prepared_generation_identity as operation
    return operation(prepared)


def record_generation_identity(record):
    from app.services.checkpoint_registry import record_generation_identity as operation
    return operation(record)


def network_geometry(record):
    from app.services.checkpoint_registry import network_geometry as operation
    return operation(record)


def records_with_children(record_ids):
    from app.services.checkpoint_registry import records_with_children as operation
    return operation(record_ids)


__all__ = ['DatasetRecipe', 'TrainingRecord', 'get_dataset', 'list_datasets', 'normalize_train_type', 'dataset_ingest_lock', 'remember_selection', 'record_by_id', 'record_for_cloud', 'recent_records', 'newest_record_for', 'prepare_launch', 'register_launch', 'prepared_generation_identity', 'record_generation_identity', 'network_geometry', 'records_with_children']
