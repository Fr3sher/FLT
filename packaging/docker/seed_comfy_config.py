#!/usr/bin/env python3
"""Point the app at the ComfyUI that shares its container.

Runs on every boot of the GPU image (Dockerfile.gpu), before ComfyUI itself starts.
base_dir and the API URL live in config.json only — there is no environment
override for them (see backend/app/config.py) — so a container that ships its own
ComfyUI has to write them down, or the user would have to type container-internal
paths into Settings by hand.

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

# Where ComfyUI's models actually live decides everything else. Two layouts exist:
# with upstream's BASE_DIRECTORY set (our compose file does set it) models/, input/
# and output/ move to /basedir and the checkout keeps only code; without it they stay
# inside the checkout. Probing beats reading BASE_DIRECTORY from the environment,
# because upstream re-execs its init script through `sudo su comfy` and the variable
# does not survive — it is absent from the /tmp/comfy_env.txt it saves.
COMFY_ROOT_CANDIDATES = ('/basedir', '/comfy/mnt/ComfyUI')
FALLBACK_COMFY_ROOT = '/comfy/mnt/ComfyUI'
API_URL = 'http://127.0.0.1:8188'      # same container, so loopback


def comfy_root(candidates=None):
    """The folder the app should treat as the ComfyUI install: the first candidate
    that actually holds a models/ directory. That is also exactly what
    capabilities._is_comfyui_dir checks, so a root chosen here cannot be rejected
    there."""
    for candidate in (candidates or COMFY_ROOT_CANDIDATES):
        if Path(candidate, 'models').is_dir():
            return candidate
    return FALLBACK_COMFY_ROOT


def wanted(base_dir: str, ollama_url: str) -> dict:
    """The values this container knows to be true, as a nested config fragment.

    No models_dir/input_dir/output_dir/loras_dir: config.resolve_comfyui_dir derives
    all four from base_dir, and writing them would only pin paths that are already
    right — while going stale the moment the layout changes."""
    fragment = {'comfyui': {'base_dir': base_dir, 'api_url': API_URL}}
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
        comfy_root(),
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
