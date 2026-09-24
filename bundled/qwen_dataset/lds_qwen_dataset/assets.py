"""Plugin-owned downloads and exact-family discovery across ComfyUI roots."""
from __future__ import annotations

import math
from pathlib import Path

from lds_sdk import config, models

LICENSE_URL = 'https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE'
_REPO = 'https://huggingface.co/Comfy-Org/Qwen-Image-2.1/resolve/main/'
ASSETS = {
    'unet': {
        'action': 'qwen_dataset_model', 'folder': 'diffusion_models',
        'filename': 'qwen_image_2.1_int8_convrot.safetensors',
        'alternatives': ('qwen_image_2.1_bf16.safetensors',), 'bytes': 7256783064,
    },
    'text_encoder': {
        'action': 'qwen_dataset_text_encoder', 'folder': 'text_encoders',
        'filename': 'qwen3vl_8b_int8_convrot.safetensors',
        'alternatives': ('qwen3vl_8b_bf16.safetensors',), 'bytes': 9350798360,
    },
    'vae': {
        'action': 'qwen_dataset_vae', 'folder': 'vae',
        'filename': 'qwen_image_2.1_vae_bf16.safetensors',
        'alternatives': (), 'bytes': 675509688,
    },
}
ACTIONS = tuple(spec['action'] for spec in ASSETS.values())


def _supported_name(slot, name):
    spec = ASSETS[slot]
    basename = Path(str(name).replace('\\', '/')).name.casefold()
    return basename in {spec['filename'].casefold(), *(n.casefold() for n in spec['alternatives'])}


def resolve(slot):
    spec = ASSETS[slot]
    pin = str(config.get(f'plugins.qwen_dataset.{slot}', '') or '').strip()
    if pin:
        if not _supported_name(slot, pin):
            return None
        # A stale explicit pin remains visible; never silently render a different model.
        name, state = models.resolve_ref(spec['folder'], pin)
        if state == 'ok' and _supported_name(slot, name):
            return name
        return None
    candidates = models.list_models(spec['folder'])
    for filename in (spec['filename'], *spec['alternatives']):
        matches = [name for name, _path in candidates
                   if Path(name.replace('\\', '/')).name.casefold() == filename.casefold()]
        if matches:
            return sorted(matches, key=lambda name: (len(Path(name).parts), name))[0]
    return None


def inspect_assets():
    resolved, missing, invalid = {}, [], []
    for slot, spec in ASSETS.items():
        name = resolve(slot)
        resolved[slot] = name
        path = models.resolve_model_file(spec['folder'], name) if name else None
        if not path:
            missing.append(spec['action'])
            continue
        verdict = models.validate_model_file(path)
        if verdict.get('blocking') or verdict.get('verdict') == 'missing':
            invalid.append({'asset': spec['action'], 'blocking': True,
                            'reason': 'The selected weight file is incomplete or unreadable.'})
    return {'models': resolved, 'missing': missing, 'invalid': invalid}


def download_roots(slot):
    """Allow the host installer to reuse exact compatible names in subfolders."""
    spec = ASSETS[slot]
    names = {spec['filename'].casefold(), *(n.casefold() for n in spec['alternatives'])}
    roots = list(models.search_roots(spec['folder']))
    for name, path in models.list_models(spec['folder']):
        if Path(name.replace('\\', '/')).name.casefold() in names:
            parent = str(Path(path).parent)
            if parent not in roots:
                roots.append(parent)
    return roots


def candidates(slot):
    spec = ASSETS[slot]
    groups = {}
    for name, _path in models.list_models(spec['folder']):
        if _supported_name(slot, name):
            relative = Path(name.replace('\\', '/'))
            prefix = '' if relative.parent == Path('.') else str(relative.parent)
            groups.setdefault(prefix, []).append(relative.name)
    return [(prefix, sorted(names)) for prefix, names in sorted(groups.items())]


def register(ctx):
    for slot, spec in ASSETS.items():
        ctx.register_model_download(
            spec['action'], url=_REPO + spec['folder'] + '/' + spec['filename'],
            dest=(spec['folder'], spec['filename']),
            min_free_gb=math.ceil(spec['bytes'] / 1024**3) + 1,
            min_bytes=spec['bytes'] // 2, expected_bytes=spec['bytes'],
            legacy_names=spec['alternatives'], license_url=LICENSE_URL,
            extra_roots=lambda slot=slot: download_roots(slot))
        ctx.register_model_slot(spec['action'], folder_type=spec['folder'],
                                hint='Choose compatible Qwen-Image 2.1 weights',
                                candidates=lambda slot=slot: candidates(slot))
    ctx.register_install_group('qwen_dataset', ACTIONS,
                               missing_key='qwen_dataset_missing', invalid_key='qwen_dataset_invalid')
