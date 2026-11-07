"""User-owned gallery integration for externally produced still frames.

The caller owns frame selection, copying and naming. LDS owns collections,
image identity and the shared gallery format, which stays readable without Video.
"""
from dataclasses import dataclass
from pathlib import PurePath
from lds_sdk.dataset_exports import DatasetExports


@dataclass(frozen=True)
class GalleryRecord:
    id: object
    dataset_id: object
    checkpoint: object
    strength: object
    filename: object
    job_id: object
    rating: object
    seed: object
    run_seed: object
    run_id: object
    status: object
    error: object
    z_model: object
    aspect: object
    prompt: object
    cfg: object
    steps: object
    steps2: object
    extra_loras: object
    krea_rebalance: object
    negative: object
    sampler: object
    sampler_preset: object
    scheduler: object
    weight_dtype: object
    enhancer_strength: object
    detail_amount: object
    resolution_tier: object
    resolution_multiplier: object
    init_image: object
    denoise: object
    hires_scale: object
    hires_denoise: object
    finish_sharpen: object
    finish_grain: object
    inject_trigger: object
    face_score: object
    face_state: object
    record_id: object
    step: object
    created_at: object
    parent_image_id: object
    derivation_kind: object
    improve_profile: object
    camera_pose: object


def _snapshot(row):
    return GalleryRecord(**{name: getattr(row, name) for name in GalleryRecord.__dataclass_fields__}) if row else None


def gallery(user_id, image_id):
    from app.extensions import db
    from app.models import LoraTestImage
    row = db.session.get(LoraTestImage, int(image_id))
    if row is None or DatasetExports(user_id).get_dataset(row.dataset_id) is None:
        return None
    return _snapshot(row)


def collection(user_id, dataset_id):
    return DatasetExports(user_id).get_dataset(int(dataset_id))


def ensure_collection(user_id, name, *, legacy_names=(), trigger_word=''):
    if (not isinstance(name, str) or not name or len(name) > 100 or len(legacy_names) > 10
            or any(not isinstance(old, str) or not old or len(old) > 100 for old in legacy_names)):
        raise ValueError('Invalid collection identity.')
    from app.extensions import db
    from app.models import FaceDataset
    row = FaceDataset.query.filter_by(user_id=str(user_id), name=name).first()
    if row is None:
        for old in legacy_names:
            row = FaceDataset.query.filter_by(user_id=str(user_id), name=old).first()
            if row is not None:
                row.name = name
                break
        if row is None:
            row = FaceDataset(user_id=str(user_id), name=name, trigger_word=trigger_word)
            db.session.add(row)
        db.session.commit()
    return row.id


def dataset_directory(user_id, dataset_id):
    if collection(user_id, dataset_id) is None:
        raise LookupError('Image dataset not found.')
    from app.services.dataset_storage import ensure_dataset_dir
    return ensure_dataset_dir(int(dataset_id))


def existing(user_id, dataset_id, filename):
    if collection(user_id, dataset_id) is None:
        raise LookupError('Image dataset not found.')
    from app.models import LoraTestImage
    return _snapshot(LoraTestImage.query.filter_by(dataset_id=int(dataset_id), filename=filename,
        status='done').order_by(LoraTestImage.id.desc()).first())


def create_frame(user_id, dataset_id, *, filename, checkpoint, prompt, derivation_kind):
    from app.models import VIDEO_FRAME_KINDS, VIDEO_FRAME_CHECKPOINTS, LoraTestImage
    from app.extensions import db
    if (derivation_kind not in VIDEO_FRAME_KINDS or checkpoint not in VIDEO_FRAME_CHECKPOINTS
            or not isinstance(filename, str) or not filename or PurePath(filename).name != filename
            or any(ch in filename for ch in '/\\:\0') or filename in ('.', '..')):
        raise ValueError('Invalid frame identity.')
    previous = existing(user_id, dataset_id, filename)
    if previous is not None:
        return previous
    row = LoraTestImage(dataset_id=int(dataset_id), filename=filename, status='done',
                        checkpoint=checkpoint, prompt=prompt, derivation_kind=derivation_kind,
                        strength=0.0, seed=None, run_id=None)
    db.session.add(row)
    db.session.commit()
    return _snapshot(row)


__all__ = ['GalleryRecord', 'gallery', 'collection', 'ensure_collection', 'dataset_directory', 'existing', 'create_frame']
