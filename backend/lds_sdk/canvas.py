"""API 1.9: bounded image history and Studio operations for alternate workspaces.

Returns payloads/snapshots only; Canvas owns its layouts, routes and policy.
The host owns dataset identity, image generation admission and durable previews.
"""
from app.services.lora_test_studio import StudioGenSettings, StudioArchMismatch, StudioAssetsMissing




from app.services import face_dataset_service as fds


def require_comfyui():
    from app.routes._common import _require_comfyui
    return _require_comfyui()


def studio_arch_mismatch_response(error):
    from app.routes._common import _studio_arch_mismatch_response
    return _studio_arch_mismatch_response(error)


def studio_missing_response(error):
    from app.routes._common import _studio_missing_response
    return _studio_missing_response(error)


def save_external_loras(rows):
    from app import config
    config.save_config({'canvas': {'external_loras': rows}})


def gallery_snapshots(user_id, image_ids, *, dataset_id=None, completed=False):
    from app.models import LoraTestImage
    from app.services.cloud_training import gallery_image
    owned = {d.id for d in fds.list_datasets(user_id)}
    if dataset_id is not None:
        owned &= {int(dataset_id)}
    if not owned or not image_ids:
        return {}
    rows = LoraTestImage.query.filter(LoraTestImage.id.in_(image_ids),
                                      LoraTestImage.dataset_id.in_(owned))
    if completed:
        rows = rows.filter(LoraTestImage.status == 'done', LoraTestImage.filename.isnot(None))
    return {row.id: gallery_image(row) for row in rows.all()}


def generate_checkpoint_comparison(user_id, selections, strengths, settings=None, *,
                                   prompts=None, external_loras=None, combine=None):
    from app.services.cloud_training import canvas_generate
    return canvas_generate(user_id, selections, strengths, settings, prompts=prompts,
                           external_loras=external_loras, combine=combine)


def history_dataset_index(user_id):
    from app.services.cloud_training import canvas_dataset_index
    return canvas_dataset_index(user_id)


__all__ = ['StudioArchMismatch', 'StudioAssetsMissing', 'StudioGenSettings', 'gallery_snapshots', 'generate_checkpoint_comparison', 'history_dataset_index', 'require_comfyui', 'save_external_loras', 'studio_arch_mismatch_response', 'studio_missing_response']
