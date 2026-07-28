#!/usr/bin/env python3
"""Point the app at the ComfyUI that shares its container.

Runs on every boot of the GPU image (Dockerfile.gpu), before ComfyUI itself starts.
The four ComfyUI folder overrides and the API URL live in config.json only — there
is no environment override for them (see backend/app/config.py) — so a container
that ships its own ComfyUI has to write them down, or the user would have to type
container-internal paths into Settings by hand.

Only keys that are EMPTY or MISSING are filled, so a path changed in Settings
survives every restart: this seeds a default, it does not enforce one.

Plain stdlib JSON, run by the system python3 without activating either venv: a boot
step that decides where ComfyUI lives must not be able to fail because an app import
chain broke.
"""
import json
import os
import sys
from pathlib import Path

COMFY_ROOT = '/comfy/mnt/ComfyUI'      # holds main.py + models/ -> a valid base_dir
API_URL = 'http://127.0.0.1:8188'      # same container, so loopback


def wanted(base_directory: str, ollama_url: str) -> dict:
    """The values this container knows to be true, as a nested config fragment."""
    comfy = {'base_dir': COMFY_ROOT, 'api_url': API_URL}
    if base_directory:
        # Upstream's BASE_DIRECTORY layout moves models/input/output out of the
        # ComfyUI checkout, so base_dir alone no longer derives them.
        comfy['models_dir'] = f'{base_directory}/models'
        comfy['loras_dir'] = f'{base_directory}/models/loras'
        comfy['input_dir'] = f'{base_directory}/input'
        comfy['output_dir'] = f'{base_directory}/output'
    fragment = {'comfyui': comfy}
    if ollama_url:
        fragment['ollama'] = {'url': ollama_url}
    return fragment


def fill_empty(current: dict, defaults: dict) -> tuple:
    """Merge `defaults` into `current`, keeping every value `current` already has.

    Returns (merged, filled) where `filled` names the dotted keys actually written.
    Whitespace-only counts as empty, matching config.resolve_comfyui_dir — a stray
    space in a path field is a blank field, not a choice."""
    filled = []
    for section, values in defaults.items():
        node = current.get(section)
        if not isinstance(node, dict):
            node = {}
            current[section] = node
        for key, value in values.items():
            existing = node.get(key)
            if isinstance(existing, str):
                if existing.strip():
                    continue
            elif existing is not None:
                continue                  # a non-string the user or app set: leave it
            node[key] = value
            filled.append(f'{section}.{key}')
    return current, filled


def main() -> int:
    """Always returns 0. The launcher that calls this must never abort the boot."""
    path = Path(os.environ.get('LDS_CONFIG', '/data/config.json'))
    try:
        current = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    except (OSError, ValueError) as exc:
        print(f'[studio] {path} is unreadable ({exc.__class__.__name__}) — leaving '
              f'it untouched. Set the ComfyUI folders in Settings > Local tools.',
              flush=True)
        return 0
    if not isinstance(current, dict):
        current = {}

    merged, filled = fill_empty(current, wanted(
        (os.environ.get('BASE_DIRECTORY') or '').strip().rstrip('/'),
        (os.environ.get('LDS_OLLAMA_URL') or '').strip()))

    if not filled:
        print('[studio] ComfyUI folders already configured — nothing seeded',
              flush=True)
        return 0

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False),
                       encoding='utf-8')
        tmp.replace(path)
    except OSError as exc:
        print(f'[studio] could not write {path} ({exc.__class__.__name__}) — set '
              f'the ComfyUI folders in Settings > Local tools.', flush=True)
        return 0

    print('[studio] seeded: ' + ', '.join(filled), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
