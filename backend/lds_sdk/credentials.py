"""Resolve shared administrator credentials without machine-specific fallbacks."""
from __future__ import annotations

import os
import re


def resolve_credential_file(key: str):
    """Path of ``<credentials dir>/<key>.txt``, or None. The folder lives OUTSIDE
    the repository: ``$SCRAPE_COOKIES_DIR``, else the configured ComfyUI output's
    sibling ``scrape_cookies`` folder.
    Never committed."""
    if not key:
        return None
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', key, flags=re.ASCII):
        raise ValueError('Expected a credential name, not a file path.')
    base = os.environ.get('SCRAPE_COOKIES_DIR')
    if not base:
        from app.config import comfyui_dir
        output = comfyui_dir('output')
        if not output:
            return None
        base = os.path.join(os.path.dirname(str(output).rstrip('/\\')), 'scrape_cookies')
    path = os.path.join(base, f'{key}.txt')
    return path if os.path.isfile(path) else None


def civitai_api_key():
    """Civitai API key (Bearer) that unlocks NSFW results, or None (SFW scan only).

    Precedence: env ``CIVITAI_API_KEY`` > ``<credentials dir>/civitai_api_key.txt``.
    Read at runtime, never committed — and never from a path that belongs to
    one machine's tooling (a fallback of that kind shipped once; a public
    codebase names no one's home)."""
    env = (os.environ.get('CIVITAI_API_KEY') or '').strip()
    if env:
        return env
    path = resolve_credential_file('civitai_api_key')
    try:
        if path and os.path.isfile(path):
            with open(path, encoding='utf-8') as stream:
                val = stream.read().strip()
            if val:
                return val
    except OSError:
        pass
    return None


__all__ = ['resolve_credential_file', 'civitai_api_key']
