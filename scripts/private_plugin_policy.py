"""Paths reserved for private product development and Store distribution.

This guards known publishing paths, not arbitrary renamed or transformed code.
Product metadata and the public SDK remain part of the core application.
"""

from __future__ import annotations


def private_plugin_path_reason(path: str) -> str | None:
    """Return a refusal reason for a Git, ZIP or staged-directory member."""
    parts = [part for part in path.replace('\\', '/').casefold().split('/') if part]
    if 'bundled' in parts:
        return 'Private plugin source must not be published with the core'
    if parts and parts[-1].endswith('.ldsplugin'):
        return 'Plugin archives belong in the separately controlled Store distribution'
    if parts and parts[-1] == 'transition-pack.zip':
        return 'The product transition pack is private distribution material'
    return None
