"""Readiness, identity prompts and admission through the public LDS queue SDK."""
from __future__ import annotations

import os
import secrets
import uuid

from lds_sdk import comfy, config, local_render

from . import assets, graph


def _settings():
    return graph.settings({key: config.get(f'plugins.qwen_dataset.{key}', default)
                           for key, default in graph.DEFAULTS.items()})


def probe():
    inspection = assets.inspect_assets()
    classes = local_render.fetch_object_info_classes()
    missing_nodes = sorted(graph.REQUIRED_NODES - classes) if classes is not None else []
    result = {
        'ok': False, 'detail': '', 'missing': inspection['missing'],
        'invalid': [item['asset'] for item in inspection['invalid']],
        'models': inspection['models'], 'missing_nodes': missing_nodes,
        'max_references': graph.MAX_REFERENCES,
    }
    if not config.comfyui_dir('input') or classes is None:
        result['detail'] = 'Configure and start ComfyUI, then check Dataset Forge again.'
    elif missing_nodes:
        result['detail'] = ('Update ComfyUI and restart it when idle; missing native nodes: '
                            + ', '.join(missing_nodes))
    elif inspection['missing'] or inspection['invalid']:
        result['detail'] = ('Prepare Dataset Forge models in Plugins settings. '
                            'Select the official Qwen-Image 2.1 INT8 or BF16 files; '
                            'clear a missing or unsupported model selection for automatic discovery.')
    else:
        try:
            opts = _settings()
            enums = local_render.fetch_object_info_enums()
            required = {
                'KSampler': {'sampler_name': opts['sampler_name'], 'scheduler': opts['scheduler']},
                'CLIPLoader': {'type': 'qwen_image'},
                'QwenImage21Cache': {'device': opts['cache_device'], 'dtype': opts['cache_dtype']},
            }
            if enums is None:
                raise ValueError('ComfyUI did not expose its supported settings; check it again.')
            for node, values in required.items():
                for key, value in values.items():
                    choices = enums.get(node, {}).get(key)
                    if choices is None:
                        raise ValueError(f'Update ComfyUI: cannot verify the {node} {key} input.')
                    if value not in choices:
                        raise ValueError(f'Update ComfyUI: {node} does not support {key}={value}.')
            result.update(ok=True, detail='Ready for local dataset variations with Qwen-Image 2.1.')
        except ValueError as exc:
            result['detail'] = str(exc)
    return result


def preflight(*, reference_count=1, aspect_ratio=None, subject_type='human', framing=None):
    try:
        graph.reference_count(reference_count)
        graph.dimensions(aspect_ratio, config.get('variations.output_megapixels', 2.0))
    except ValueError as exc:
        return {'ok': False, 'detail': str(exc), 'max_references': graph.MAX_REFERENCES}
    return probe()


def enqueue(user_id, source_filename, source_path, edit_prompt, extra_ref_paths=(),
            aspect_ratio=None, extra_metadata=None, seed=None, subject_type='human', framing=None):
    references = [source_path, *(extra_ref_paths or ())]
    status = preflight(reference_count=len(references), aspect_ratio=aspect_ratio,
                       subject_type=subject_type, framing=framing)
    if not status['ok']:
        raise ValueError(status['detail'])
    for index, path in enumerate(references, start=1):
        if not path or not os.path.isfile(path):
            raise ValueError(f'Reference {index} is missing; choose it again before generating.')
    prompt = graph.identity_prompt(edit_prompt, len(references), subject_type)
    opts = _settings()
    chosen_seed = secrets.randbits(64) if seed is None else seed
    uid = uuid.uuid4().hex
    # Construct and validate everything before staging any user images.
    staged_names = [f'lds_dataset_forge_{uid}_ref_{index}.png'
                    for index in range(1, len(references) + 1)]
    workflow = graph.build_graph(
        assets=status['models'], references=staged_names, prompt=prompt, seed=chosen_seed,
        aspect_ratio=aspect_ratio, megapixels=config.get('variations.output_megapixels', 2.0),
        options=opts, filename_prefix=f'LDS_DatasetForge_{uid}')
    input_dir = comfy.ensure_input_usable(str(config.comfyui_dir('input')))
    staged_paths = []
    try:
        for path, name in zip(references, staged_names):
            staged_paths.append(comfy.stage_input_image(path, name, input_dir))
        metadata = dict(extra_metadata or {})
        metadata.update(model_name='qwen_dataset', engine='qwen_dataset',
                        staged_inputs=staged_names, seed=chosen_seed)
        comfy.queue.add_job(job_type='image', user_id=str(user_id), workflow_data=workflow,
                            prompt=edit_prompt, job_id=uid, metadata=metadata)
    except Exception:
        # Only these unique task files are ours. Successfully admitted work is
        # cleaned up by the host on success, failure and cancellation.
        for path in staged_paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise
    return uid
