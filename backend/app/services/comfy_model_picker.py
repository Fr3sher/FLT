"""On-demand scan of ComfyUI's model folders for the "which file?" pickers.

The Klein model-file slots and Krea 2 Edit's base model / identity LoRA were
free-text fields: you typed a filename from memory and found out at generate
time whether it existed. This backs a picker of the files ACTUALLY on disk.

ONE MECHANISM, NOT A SECOND ONE
-------------------------------
Everything here goes through ``comfy_model_paths`` — the module that already
mirrors ComfyUI's ``folder_paths``/``extra_model_paths.yaml`` semantics, and that
the RESOLVERS use. A picker built on its own directory walk would list files the
resolver cannot load (and hide files it can) the day an install has an
``extra_model_paths.yaml``; that divergence is exactly what
``test_model_scanners_agree`` exists to prevent.

For the Krea base model the list is NOT ``list_models('diffusion_models')``: the
resolver only ever elects among ``krea_edit_helper._krea_unet_folders()`` (krea-
named subfolders + search-root level, minus the checkpoints the identity LoRA
renders as noise on). So the picker asks the RESOLVER for its candidates. Offering
a file the resolver would refuse is offering a choice that silently does nothing.

Slots are named, not free-form: the folder type arrives from an HTTP query
parameter, and ``list_models`` takes it straight to the filesystem.

Cache: per slot, keyed on a cheap change-signature of that slot's search roots
(each root's mtime) — mirrors ``klein_lora_picker``. Never scanned at boot, only
when the endpoint is hit, so an install with a slow/remote model mount pays only
when a panel that shows a picker is opened. ``force=True`` (the ↻ button)
bypasses the cache and catches a file added deep inside a subfolder, which a
root-level mtime cannot see.

Degradation is total: no ComfyUI configured / unreadable roots / a scan that
raises all produce an empty list, and the caller keeps a free-text field.
"""
from __future__ import annotations

import logging
import os
import threading

from . import comfy_model_paths

logger = logging.getLogger(__name__)

# slot -> (comfy folder type, the words the UI uses to say WHERE to put a file).
# The folder type is what makes the scan agree with the resolver; the hint is
# what makes the "nothing found" state actionable instead of mute.
SLOTS = {
    'klein_unet': ('diffusion_models', 'ComfyUI’s models/unet (or models/diffusion_models)'),
    'klein_text_encoder': ('text_encoders', 'ComfyUI’s models/text_encoders'),
    'klein_vae': ('vae', 'ComfyUI’s models/vae'),
    'klein_consistency_lora': ('loras', 'ComfyUI’s models/loras'),
    'krea_identity_lora': ('loras', 'ComfyUI’s models/loras'),
    # Special-cased below — the folder type is right, the LIST is the resolver's.
    'krea_base_model': ('diffusion_models', 'a krea-named folder under ComfyUI’s models/unet'),
}

_lock = threading.Lock()
_cache: dict = {}


def _roots_signature(folder_type: str) -> tuple:
    """``(root, mtime)`` per search root — the scan re-runs only when a root's own
    listing changed. A missing/unreadable root contributes ``(root, None)`` so it
    still participates and re-validates the day it appears."""
    sig = []
    for root in comfy_model_paths.search_roots(folder_type):
        try:
            sig.append((root, os.path.getmtime(root)))
        except OSError:
            sig.append((root, None))
    return tuple(sig)


def _scan(slot: str, folder_type: str) -> list[str]:
    if slot == 'krea_base_model':
        # The resolver's own candidate set, so picker == election. Imported here
        # rather than at module import: krea_edit_helper is a heavy module and
        # this one is imported by a settings route.
        from . import krea_edit_helper as krh
        return sorted((os.path.join(sub, name)
                       for sub, names in krh._krea_unet_folders() for name in names),
                      key=str.lower)
    return sorted((rel for rel, _ab in comfy_model_paths.list_models(folder_type)),
                  key=str.lower)


def list_slot_files(slot: str, force: bool = False) -> tuple[list[str], str]:
    """``([relative loader name], folder hint)`` for one picker slot.

    Each name is EXACTLY the string the loader node expects and the resolver
    resolves back — the same value the free-text field stored, which is why
    switching a field to this picker needs no alias: the config key and the
    written string are unchanged.

    Unknown slot -> ``([], '')``. Any scan failure -> ``([], hint)``, never an
    exception: the picker falls back to free text."""
    entry = SLOTS.get(slot)
    if entry is None:
        return [], ''
    folder_type, hint = entry
    sig = _roots_signature(folder_type)
    if not force:
        with _lock:
            hit = _cache.get(slot)
        if hit and hit['sig'] == sig:
            return list(hit['files']), hint
    try:
        files = _scan(slot, folder_type)
    except Exception:
        logger.exception('model-file scan failed for slot %s', slot)
        return [], hint
    with _lock:
        _cache[slot] = {'sig': sig, 'files': files}
    return list(files), hint


def clear_cache() -> None:
    """Drop every slot's scan cache (test hygiene; production self-invalidates on
    the mtime signature)."""
    with _lock:
        _cache.clear()
