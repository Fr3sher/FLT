"""Named studio operations shared with the host; no module handle escapes."""

def comfy_output_dir(*args, **kwargs):
    from app.services.lora_test_studio import _comfy_output_dir
    return _comfy_output_dir(*args, **kwargs)


def is_unsafe_external_lora_name(*args, **kwargs):
    from app.services.lora_test_studio import _is_unsafe_external_lora_name
    return _is_unsafe_external_lora_name(*args, **kwargs)


def preflight_family(*args, **kwargs):
    from app.services.lora_test_studio import preflight_family
    return preflight_family(*args, **kwargs)


from app.services.lora_test_studio import StudioAssetsMissing as StudioAssetsMissing  # noqa: E402 — stable value/type identity

__all__ = ['comfy_output_dir', 'is_unsafe_external_lora_name', 'preflight_family', 'StudioAssetsMissing',
           'list_all_testable_checkpoints', 'get_krea_models', 'studio_payload_run',
           'enhance_with_instructions', 'create_comparison_run', 'delete_gallery_images', 'normalize_writer_model',
           'build_krea_image']


def list_all_testable_checkpoints(*args, **kwargs):
    from app.services.lora_test_studio import list_all_testable_checkpoints
    return list_all_testable_checkpoints(*args, **kwargs)


def get_krea_models(*args, **kwargs):
    from app.services.lora_test_studio import get_krea_models
    return get_krea_models(*args, **kwargs)


def studio_payload_run(*args, **kwargs):
    from app.services.lora_test_studio import studio_payload_run
    return studio_payload_run(*args, **kwargs)


def enhance_with_instructions(*args, **kwargs):
    from app.services.lora_test_studio import enhance_with_instructions
    return enhance_with_instructions(*args, **kwargs)


def create_comparison_run(user_id, selections, strengths, payload):
    from app.services.lora_test_studio import StudioGenSettings, create_comparison_run as create
    return create(user_id, selections, strengths, StudioGenSettings.from_payload(payload))


def delete_gallery_images(image_ids):
    from app.services.cloud_training import delete_gallery_images
    return delete_gallery_images(image_ids)


def normalize_writer_model(value):
    from app.services.ollama_control import normalize_ollama_model_ref
    return normalize_ollama_model_ref(value, allow_empty=True) or None


def build_krea_image(user_id, *, lora, base_model, prompt, seed, width, height,
                     strength=1.0, steps=8, cfg=1.0, sampler='er_sde',
                     scheduler='simple', weight_dtype='fp8_e4m3fn'):
    """API 1.18: prepare one Krea image without a dataset or database writes.

    The product owns its recipe, durable intent and result. The host retains
    the existing Krea graph, model allowlists, architecture and asset preflight.
    Submit the returned workflow through ``comfy.add_plugin_job``; this method
    neither reserves the GPU nor creates a training/Studio record.
    """
    import math
    from app.services import lora_test_studio as studio

    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
        raise ValueError('Describe the image (up to 12000 characters).')
    for value, low, high, label in ((seed, 1, 2**31 - 1, 'seed'),
                                   (width, 64, 4096, 'width'), (height, 64, 4096, 'height'),
                                   (steps, 1, 50, 'steps')):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'Invalid image {label}.')
    if width % 8 or height % 8 or width * height > 4096**2:
        raise ValueError('Image dimensions must be multiples of eight.')
    for value, low, high, label in ((strength, 0, 2, 'LoRA strength'), (cfg, 1, 10, 'CFG')):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not low <= value <= high or not math.isfinite(value)):
            raise ValueError(f'Invalid image {label}.')
    if (not all(isinstance(v, str) for v in (sampler, scheduler, weight_dtype))
            or sampler not in studio.KREA_ALLOWED_SAMPLERS
            or scheduler not in studio.KREA_ALLOWED_SCHEDULERS
            or weight_dtype not in studio.KREA_ALLOWED_WEIGHT_DTYPES):
        raise ValueError('Unsupported Krea sampling settings.')
    # A product-supplied string must be in the scanned namespace before any
    # resolver/header read. Never silently elect a different base or LoRA.
    allowed = {item['filename'] for item in studio.get_krea_loras()}
    if not isinstance(lora, str) or lora not in allowed:
        raise ValueError('The recipe LoRA is not installed in the Krea model folder.')
    if not isinstance(base_model, str) or base_model not in studio.get_krea_models():
        raise ValueError('The recipe Krea base model is not installed.')
    reason = studio.gpu_busy_reason()
    if reason:
        raise studio.GpuBusyError(reason)
    try:
        studio._preflight_checkpoint_arch('krea', [lora])
    except studio.StudioArchMismatch as exc:
        raise RuntimeError(str(exc)) from exc
    workflow = studio._build_cell_workflow(
        user_id, lora, strength, prompt.strip(), seed, base_model, allowed,
        width=width, height=height, cfg=cfg, steps=steps, dataset_id=None,
        train_type='krea', sampler=sampler, scheduler=scheduler,
        weight_dtype=weight_dtype, trigger_word=None, hires_scale=1,
        available_classes=studio._target_node_classes())
    try:
        studio.preflight_family('krea', [workflow])
    except studio.StudioAssetsMissing as exc:
        raise RuntimeError(str(exc)) from exc
    return workflow


# Compatibility with the original public SDK exports.
_LEGACY_EXPORTS = {'StudioAssetsMissing': ('app.services.lora_test_studio',
                         'StudioAssetsMissing'),
 'comfy_output_dir': ('app.services.lora_test_studio', '_comfy_output_dir'),
 'is_unsafe_external_lora_name': ('app.services.lora_test_studio',
                                  '_is_unsafe_external_lora_name'),
 'unsafe_lora_name': ('app.services.lora_test_studio',
                      '_is_unsafe_external_lora_name')}

def __getattr__(name):
    if name not in _LEGACY_EXPORTS:
        raise AttributeError(name)
    from importlib import import_module
    module, symbol = _LEGACY_EXPORTS[name]
    return getattr(import_module(module), symbol)

__all__ = list(dict.fromkeys([*__all__, *_LEGACY_EXPORTS]))
