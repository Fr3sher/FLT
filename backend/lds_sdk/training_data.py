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


def _snapshot(row, cls):
    return cls(**{name: getattr(row, name) for name in cls.__dataclass_fields__}) if row is not None else None


def get_dataset(user_id, dataset_id):
    from app.services.face_dataset_service import get_dataset as operation
    return _snapshot(operation(user_id, dataset_id), DatasetRecipe)


def list_datasets(user_id):
    from app.services.face_dataset_service import list_datasets as operation
    return tuple(_snapshot(row, DatasetRecipe) for row in operation(user_id))


__all__ = ['get_dataset', 'list_datasets']
