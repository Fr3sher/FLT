"""Klein improvement recipe over LDS's shared local edit renderer."""
from lds_sdk import klein_edit

def preflight():
    missing = klein_edit.missing_assets()
    nodes = klein_edit.missing_nodes()
    if nodes:
        raise klein_edit.MissingNodes(missing, nodes)
    if any(asset in missing for asset in klein_edit.required_assets()):
        raise klein_edit.MissingAssets(missing)

def enqueue(*, user_id, source_filename, source_path, extra_metadata,
            prompt, profile):
    return klein_edit.enqueue(user_id=user_id, source_filename=source_filename,
                              source_path=source_path, edit_prompt=prompt,
                              extra_metadata=extra_metadata, **profile)

def _number(key, default, ceiling, *, integer=False):
    from lds_sdk import config
    raw = config.get('klein.' + key)
    if key == 'improve_consistency_strength' and raw in (None, default):
        raw = config.get('klein.improve_character_lora_strength', raw)
    try:
        value = int(raw) if integer else float(raw)
    except (TypeError, ValueError):
        return default
    return max(1 if integer else 0.0, min(ceiling, value))

def preset_rows():
    from lds_sdk import config
    return klein_edit.preset_rows(config.get('klein.improve_lora_preset'))

def profile(model=None):
    return {
        'klein_model': model,
        'lora_strength': _number('improve_consistency_strength', 1.0, 1.5),
        'sampler_steps': _number('improve_steps', 4, 50, integer=True),
        'base_lora_strength': _number('improve_base_lora_strength', 0.0, 2.0),
        'output_megapixels': _number('improve_megapixels', 2.0, 8.0),
        'generation_loras': preset_rows(),
    }

def instruction():
    from lds_sdk import config
    return klein_edit.improvement_prompt() if config.get('identity_prompts.klein_improve_enabled', True) else ''
