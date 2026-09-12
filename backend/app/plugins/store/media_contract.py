"""Bounded, inert presentation assets, shared by the reader and operator tool.

This module has no app imports: the standalone operator loads this same contract
without starting LDS. Media are public, reviewed images, never product archives.
"""
from __future__ import annotations

import hashlib
import io
import re
import warnings
import zlib

MAX_MEDIA_BYTES = 5 * 1024 * 1024
MAX_MEDIA_PIXELS = 16_000_000
MAX_MEDIA_IMAGES = 8
PREPARATION_HINT = 'Re-export with store/tools/prepare_presentation.py.'


def _dimensions(width, height):
    return 1 <= width <= 8192 and 1 <= height <= 8192 and width * height <= MAX_MEDIA_PIXELS


def _png_container(data):
    """Screenshot profile: one 8-bit frame, image data, end; no ancillary data."""
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return False
    position, row_bytes, height, compressed = 8, 0, 0, []
    while position + 12 <= len(data):
        length = int.from_bytes(data[position:position + 4], 'big')
        kind = data[position + 4:position + 8]
        payload = data[position + 8:position + 8 + length]
        if position + length + 12 > len(data) or kind not in (b'IHDR', b'IDAT', b'IEND'):
            return False
        if zlib.crc32(kind + payload) != int.from_bytes(data[position + 8 + length:position + 12 + length], 'big'):
            return False
        if kind == b'IHDR':
            if position != 8 or length != 13:
                return False
            width, height = int.from_bytes(payload[:4], 'big'), int.from_bytes(payload[4:8], 'big')
            channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(payload[9])
            if not channels or payload[8] != 8 or payload[10:] != b'\0\0\0' or not _dimensions(width, height):
                return False
            row_bytes = width * channels + 1
        elif kind == b'IDAT':
            if not row_bytes:
                return False
            compressed.append(payload)
        else:
            if length or position + 12 != len(data) or not compressed:
                return False
            try:
                stream = zlib.decompressobj()
                decoded = stream.decompress(b''.join(compressed), row_bytes * height + 1)
                return (stream.eof and not stream.unused_data and not stream.unconsumed_tail
                        and len(decoded) == row_bytes * height
                        and all(decoded[offset] <= 4 for offset in range(0, len(decoded), row_bytes)))
            except zlib.error:
                return False
        position += length + 12
    return False


def parse_presentation(value, plugin_id, version):
    # Keep legacy JPEG/WebP entries readable as catalogue data. Their bytes are
    # refused at publication/serving until re-exported; other products stay usable.
    if value is None:
        return ()
    if (not isinstance(value, dict) or set(value) != {'schema_version', 'images'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or not isinstance(value['images'], list) or len(value['images']) > MAX_MEDIA_IMAGES):
        raise ValueError('Invalid presentation format.')
    images, ids, targets = [], set(), set()
    for item in value['images']:
        if not isinstance(item, dict) or set(item) != {'id', 'target', 'alt', 'caption', 'width', 'height'}:
            raise ValueError('Invalid presentation image.')
        image_id, target = item['id'], item['target']
        prefix = f'media/{plugin_id}/{version}/'
        if (not isinstance(image_id, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', image_id)
                or image_id in ids or not isinstance(target, str) or target in targets
                or not target.startswith(prefix)
                or not re.fullmatch(r'[0-9a-f]{64}\.(png|jpg|webp)', target[len(prefix):])
                or not re.fullmatch(r'[a-z][a-z0-9_.-]{0,127}', plugin_id)
                or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.!+_-]{0,127}', version)):
            raise ValueError('Invalid presentation identity or target.')
        for key, maximum, minimum in (('alt', 240, 1), ('caption', 500, 0)):
            text = item[key]
            if (not isinstance(text, str) or not minimum <= len(text.strip()) <= maximum
                    or any(ord(char) < 32 or ord(char) == 127 for char in text)):
                raise ValueError('Invalid presentation text.')
        if (any(type(item[key]) is not int or not 1 <= item[key] <= 8192 for key in ('width', 'height'))
                or item['width'] * item['height'] > MAX_MEDIA_PIXELS):
            raise ValueError('Invalid presentation dimensions.')
        images.append(dict(item))
        ids.add(image_id)
        targets.add(target)
    return tuple(images)


def validate_image(data, item):
    """Reject mismatched, active, animated, oversized or metadata-bearing media."""
    from PIL import Image

    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_MEDIA_BYTES:
        raise ValueError('Presentation image exceeds the supported size.')
    filename = item['target'].rsplit('/', 1)[-1]
    digest, extension = filename.split('.')
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError('Presentation image digest differs from its target.')
    if extension != 'png':
        raise ValueError('Distributed presentation images must be cleaned PNG files. ' + PREPARATION_HINT)
    if not _png_container(data):
        raise ValueError('Unsupported or appended presentation data. ' + PREPARATION_HINT)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                if (image.format != 'PNG'
                        or image.size != (item['width'], item['height'])
                        or image.width * image.height > MAX_MEDIA_PIXELS
                        or getattr(image, 'n_frames', 1) != 1
                        or image.getexif()
                        or 'icc_profile' in image.info
                        or any(key.lower() in ('exif', 'xmp', 'comment', 'xml:com.adobe.xmp')
                               for key in image.info)
                        or getattr(image, 'text', {})):
                    raise ValueError('Presentation image format, dimensions or metadata are invalid.')
                image.load()
    except Exception as exc:
        raise ValueError('Presentation image could not be validated.') from exc
    return 'image/png'
