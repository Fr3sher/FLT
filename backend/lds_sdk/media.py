"""A neutral PNG for the outside world — the disclosure boundary every
publisher draws before a picture leaves the machine.

Rebuilding the pixels into a fresh image strips EXIF/XMP/GPS/PNG text chunks
(a ComfyUI output carries its whole workflow as text, local paths included)
and bakes the camera orientation in; merely calling ``save`` on a decoded
source can let Pillow reproduce ``image.info``. The original master is read
only and never rewritten.

Core on purpose: the Hugging Face publisher and the Civitai publisher share
this one boundary, and each is (or will be) a plugin of its own. Raises
``ValueError``; each publisher wraps it in its own error type.
"""
from __future__ import annotations

from PIL import Image, ImageOps, UnidentifiedImageError
from app.utils.redact import redact_tokens, redact_user_paths


def write_sanitized_publish_png(source_path, destination_path) -> None:
    """Write ``destination_path`` as a metadata-free PNG of ``source_path``."""
    try:
        with Image.open(source_path) as source:
            source.load()
            oriented = ImageOps.exif_transpose(source)
            has_alpha = ('A' in oriented.getbands()
                         or 'transparency' in getattr(oriented, 'info', {}))
            mode = 'RGBA' if has_alpha else 'RGB'
            # Image.new has no inherited `.info`, unlike a copy/convert of the
            # source, so save() has no metadata payload to reproduce.
            neutral = Image.new(mode, oriented.size)
            neutral.paste(oriented.convert(mode))
            neutral.save(destination_path, 'PNG', compress_level=6)
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        raise ValueError('could not prepare a metadata-free image for publishing') from exc


__all__ = ['redact_tokens', 'redact_user_paths', 'write_sanitized_publish_png']
