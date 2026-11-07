"""Native Qwen-Image 2.1 editing graph; one dataset shot per host queue job.

The reference encoder and cache follow ComfyUI's official image-edit template.
LDS supplies the shot loop, output geometry and result harvesting.
"""
from __future__ import annotations

import math

MAX_REFERENCES = 10
DEFAULTS = {
    'unet': '', 'text_encoder': '', 'vae': '',
    'steps': 25, 'cfg': 3.0, 'sampler_name': 'res_multistep',
    'scheduler': 'simple', 'reference_resolution': 1024,
    'negative_prompt': '', 'cache_device': 'auto', 'cache_dtype': 'default',
}
REQUIRED_NODES = frozenset({
    'UNETLoader', 'CLIPLoader', 'VAELoader', 'LoadImage',
    'TextEncodeQwenImage21', 'QwenImage21Cache', 'EmptyLatentImage',
    'KSampler', 'VAEDecode', 'SaveImage',
})
CHOICES = {
    'sampler_name': ('res_multistep', 'euler', 'dpmpp_2m'),
    'scheduler': ('simple', 'normal', 'karras'),
    'cache_device': ('auto', 'gpu', 'cpu', 'off'),
    'cache_dtype': ('default', 'int8', 'int4'),
}


def number(value, low, high, label, *, integer=False):
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a number')
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'Invalid {label}') from exc
    if not math.isfinite(parsed) or not low <= parsed <= high:
        raise ValueError(f'{label} must be between {low} and {high}')
    if integer and not parsed.is_integer():
        raise ValueError(f'{label} must be an integer')
    return int(parsed) if integer else parsed


def settings(values=None):
    out = {**DEFAULTS, **(values or {})}
    out['steps'] = number(out['steps'], 1, 100, 'Steps', integer=True)
    out['cfg'] = number(out['cfg'], 0, 30, 'CFG')
    out['reference_resolution'] = number(
        out['reference_resolution'], 256, 2048, 'Reference resolution', integer=True)
    if out['reference_resolution'] % 32:
        raise ValueError('Reference resolution must be a multiple of 32')
    for key, choices in CHOICES.items():
        if out[key] not in choices:
            raise ValueError(f'Unsupported {key}; choose {", ".join(choices)}')
    if not isinstance(out['negative_prompt'], str) or len(out['negative_prompt']) > 20000:
        raise ValueError('Negative prompt must be text of at most 20000 characters')
    return out


def reference_count(value):
    return number(value, 1, MAX_REFERENCES, 'Reference count', integer=True)


def dimensions(aspect_ratio, megapixels):
    """Match the shared variation pixel budget, with the model's 32px alignment."""
    mp = number(megapixels, 0.5, 2.0, 'Variation megapixels')
    parts = str(aspect_ratio or '1:1').split(':')
    if len(parts) != 2:
        raise ValueError('Shot aspect ratio must use width:height')
    width = number(parts[0], 1, 100, 'Aspect width')
    height = number(parts[1], 1, 100, 'Aspect height')
    ratio = width / height
    if not 0.25 <= ratio <= 4:
        raise ValueError('Shot aspect ratio must be between 1:4 and 4:1')
    return (max(32, round(math.sqrt(mp * 1_000_000 * ratio) / 32) * 32),
            max(32, round(math.sqrt(mp * 1_000_000 / ratio) / 32) * 32))


def identity_prompt(edit_prompt, count, subject_type='human'):
    reference_count(count)
    if not isinstance(edit_prompt, str) or not edit_prompt.strip():
        raise ValueError('A shot prompt is required')
    subject = {
        'human': 'person, preserving facial identity, age, hair and body proportions',
        'anime': 'character, preserving its face, hair, proportions and illustration style',
        'animal': 'animal, preserving its species, markings, coat and body proportions',
        'creature': 'creature, preserving its anatomy, markings, materials and proportions',
        'object': 'object, preserving its shape, colors, materials and distinguishing details',
    }.get(subject_type, 'subject, preserving its defining appearance and proportions')
    refs = ', '.join(f'<image{i}>' for i in range(1, count + 1))
    return (f'Create one new image of the same {subject}. '
            f'{refs} show the same subject and are identity references. '
            'Follow the requested shot, pose, expression, lighting and scene. '
            'Show one subject in one frame.\n\n' + edit_prompt.strip())


def _filename(value, label, *, model=False):
    if not isinstance(value, str) or not value or value.startswith(('/', '\\')):
        raise ValueError(f'{label} must be a relative filename')
    parts = value.replace('\\', '/').split('/')
    if ':' in value or any(ord(c) < 32 for c in value) or any(p in ('', '.', '..') for p in parts):
        raise ValueError(f'{label} must stay inside ComfyUI folders')
    if model and not value.lower().endswith(('.safetensors', '.sft')):
        raise ValueError(f'{label} must be a native safetensors model')
    return value


def build_graph(*, assets, references, prompt, seed, aspect_ratio='1:1',
                megapixels=2.0, options=None, filename_prefix='LDS_DatasetForge'):
    reference_count(len(references))
    opts = settings(options)
    width, height = dimensions(aspect_ratio, megapixels)
    # Avoid float conversion: uint64 seeds must retain every bit.
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
        raise ValueError('Seed must be an unsigned 64-bit integer')
    for key in ('unet', 'text_encoder', 'vae'):
        _filename(assets[key], key, model=True)
    _filename(filename_prefix, 'Output prefix')
    graph = {
        '1': {'class_type': 'UNETLoader', 'inputs': {
            'unet_name': assets['unet'], 'weight_dtype': 'default'}},
        '2': {'class_type': 'CLIPLoader', 'inputs': {
            'clip_name': assets['text_encoder'], 'type': 'qwen_image', 'device': 'default'}},
        '3': {'class_type': 'VAELoader', 'inputs': {'vae_name': assets['vae']}},
        '4': {'class_type': 'TextEncodeQwenImage21', 'inputs': {
            'clip': ['2', 0], 'vae': ['3', 0], 'prompt': prompt,
            'negative_prompt': opts['negative_prompt'], 'resolution': opts['reference_resolution']}},
        '5': {'class_type': 'QwenImage21Cache', 'inputs': {
            'model': ['1', 0], 'device': opts['cache_device'], 'dtype': opts['cache_dtype']}},
        '6': {'class_type': 'EmptyLatentImage', 'inputs': {
            'width': width, 'height': height, 'batch_size': 1}},
        '7': {'class_type': 'KSampler', 'inputs': {
            'model': ['5', 0], 'positive': ['4', 0], 'negative': ['4', 1],
            'latent_image': ['6', 0], 'seed': seed, 'steps': opts['steps'], 'cfg': opts['cfg'],
            'sampler_name': opts['sampler_name'], 'scheduler': opts['scheduler'], 'denoise': 1.0}},
        '8': {'class_type': 'VAEDecode', 'inputs': {'samples': ['7', 0], 'vae': ['3', 0]}},
        '9': {'class_type': 'SaveImage', 'inputs': {
            'images': ['8', 0], 'filename_prefix': filename_prefix}},
    }
    for index, reference in enumerate(references, start=1):
        node_id = str(10 + index)
        graph[node_id] = {'class_type': 'LoadImage', 'inputs': {
            'image': _filename(reference, 'Reference')}}
        # Autogrow uses dotted input names in the ComfyUI API, not a nested dict.
        graph['4']['inputs'][f'images.image_{index}'] = [node_id, 0]
    return graph
