"""API 1.9: the core's shared Klein edit renderer and source readiness."""
from app.services.klein_edit_helper import KleinModelsMissing as MissingAssets
from app.services.face_dataset_service import KleinNodesMissing as MissingNodes


def missing_assets():
    from app.services.klein_edit_helper import klein_missing_assets
    return klein_missing_assets()


def missing_nodes():
    from app.services.klein_edit_helper import klein_missing_nodes
    return klein_missing_nodes()


def required_assets():
    from app.services.klein_edit_helper import KLEIN_REQUIRED
    return tuple(KLEIN_REQUIRED)


def enqueue(*, user_id, source_filename, source_path, edit_prompt,
            extra_metadata, klein_model=None, lora_strength=None,
            sampler_steps=None, base_lora_strength=None, generation_loras=None,
            output_megapixels=None):
    from app.services.klein_edit_helper import enqueue_klein_edit
    return enqueue_klein_edit(user_id=user_id, source_filename=source_filename,
                              source_path=source_path, edit_prompt=edit_prompt,
                              extra_metadata=extra_metadata, klein_model=klein_model,
                              lora_strength=lora_strength, sampler_steps=sampler_steps,
                              base_lora_strength=base_lora_strength,
                              generation_loras=generation_loras,
                              output_megapixels=output_megapixels)


def preset_rows(name):
    from app.services.klein_edit_helper import resolve_generation_lora_preset
    return resolve_generation_lora_preset(name)


def improvement_prompt():
    from app.services.face_variations import get_identity_prompt
    return get_identity_prompt('klein_improve')


__all__ = ['MissingAssets', 'MissingNodes', 'enqueue', 'improvement_prompt', 'missing_assets', 'missing_nodes', 'preset_rows', 'required_assets']
