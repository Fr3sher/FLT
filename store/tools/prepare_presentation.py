"""Prepare reviewed real screenshots as a separate, unsigned catalogue bundle.

Never publishes, signs, edits an archive or connects to the running app. The
operator still reviews every pixel and caption before the normal publish step.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path

from PIL import Image

try:
    from .repository import OperatorParser, _media
except ImportError:  # Direct CLI execution.
    from repository import OperatorParser, _media


def prepare(catalog, plugin_id, version, shots, output):
    result = copy.deepcopy(catalog)
    release = next((entry for product in result['products'] if product['id'] == plugin_id
                    for entry in product['releases'] if entry['manifest']['version'] == version), None)
    if release is None or not isinstance(shots, list) or not 1 <= len(shots) <= _media.MAX_MEDIA_IMAGES:
        raise ValueError('Select an existing release and one to eight reviewed screenshots.')
    output = Path(output)
    if output.exists():
        raise ValueError('Use a new presentation output folder.')
    images, artifacts = [], {}
    for shot in shots:
        source = Path(shot['file'])
        if source.stat().st_size > _media.MAX_MEDIA_BYTES:
            raise ValueError('The input screenshot is too large.')
        with Image.open(source) as original:
            if (original.width * original.height > _media.MAX_MEDIA_PIXELS
                    or max(original.size) > 8192 or getattr(original, 'n_frames', 1) != 1):
                raise ValueError('Use a bounded, still screenshot.')
            # Fresh RGB/RGBA pixels remove EXIF, PNG text, XMP and profiles;
            # no resizing, synthetic content or lossy re-encoding is involved.
            pixels = Image.new('RGBA' if 'A' in original.getbands() else 'RGB', original.size)
            pixels.paste(original.convert(pixels.mode))
            buffer = io.BytesIO()
            pixels.save(buffer, format='PNG')
            data = buffer.getvalue()
            target = f'media/{plugin_id}/{version}/{hashlib.sha256(data).hexdigest()}.png'
            item = {'id': shot['id'], 'target': target, 'alt': shot['alt'], 'caption': shot.get('caption', ''),
                    'width': pixels.width, 'height': pixels.height}
            _media.validate_image(data, item)
            images.append(item)
            artifacts[target] = data
    presentation = {'schema_version': 1, 'images': images}
    _media.parse_presentation(presentation, plugin_id, version)
    release['presentation'] = presentation
    output.mkdir(parents=True)
    for target, data in artifacts.items():
        destination = output / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    (output / 'catalog.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    (output / 'media-artifacts.json').write_text(json.dumps({target: target for target in artifacts}, indent=2) + '\n', encoding='utf-8')
    return result, artifacts


def main():
    parser = OperatorParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--plugin', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--shots', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        _, artifacts = prepare(json.loads(args.catalog.read_text(encoding='utf-8')), args.plugin, args.version,
                               json.loads(args.shots.read_text(encoding='utf-8')), args.output)
    except Exception:
        parser.exit(1, json.dumps({'error': 'invalid_presentation_inputs'}) + '\n')
    print(json.dumps({'status': 'prepared_unsigned', 'images': len(artifacts)}))


if __name__ == '__main__':
    main()
