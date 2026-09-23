"""Bounded extraction from the server-resolved reference libraries."""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path
import tempfile
import uuid

from lds_video import video_reference_library as library, video_references as refs


def media_info(user_id, descriptor):
    selected = library.resolve(user_id, descriptor)
    if selected['media_kind'] == 'image':
        return selected | {'duration': None, 'has_audio': False}
    prefix, meta = refs._probe(selected['path'], 'video', bounded=False)
    end = selected['end'] if selected['end'] is not None else meta['duration']
    if end > meta['duration'] + .05 or selected['start'] >= end:
        raise ValueError('The library clip bounds no longer match its source video.')
    return selected | {'end': end, 'duration': end - selected['start'],
                       'has_audio': meta['has_audio'], 'prefix': prefix}


def info(user_id, descriptor):
    facts = media_info(user_id, descriptor)
    return {key: facts[key] for key in ('duration', 'has_audio', 'media_kind')}


def _frame(facts, frame, destination, *, thumbnail=False):
    from lds_video.video_test_studio import _run_ffmpeg
    if frame not in ('first', 'last'):
        raise ValueError('Choose the first or last video frame.')
    # Reverse only a bounded tail, rather than decode the original rush in full.
    span = min(1.0, facts['duration'])
    at = facts['start'] if frame == 'first' else max(facts['start'], facts['end'] - span)
    filters = ['reverse'] if frame == 'last' else []
    if thumbnail:
        filters.append('scale=384:384:force_original_aspect_ratio=decrease')
    command = [*facts['prefix'], '-ss', str(at), '-t', str(span), '-i', str(facts['path']),
               '-an', '-map', '0:v:0', '-frames:v', '1', '-threads', '2', '-map_metadata', '-1']
    if filters:
        command += ['-vf', ','.join(filters)]
    result = _run_ffmpeg([*command, '-y', str(destination)], timeout=25)
    if result.returncode or not destination.is_file() or not destination.stat().st_size:
        raise ValueError('The selected video frame could not be decoded.')


@contextmanager
def image_source(user_id, descriptor, frame='first'):
    facts = media_info(user_id, descriptor)
    if frame not in ('first', 'last'):
        raise ValueError('Choose the first or last video frame.')
    if facts['media_kind'] == 'image':
        yield facts['path']
    else:
        with tempfile.TemporaryDirectory(prefix='lds-reference-frame-') as scratch:
            path = Path(scratch) / 'frame.png'
            _frame(facts, frame, path)
            yield path


def stage_guide(user_id, descriptor, frame='first'):
    from lds_sdk.video_host import config as cfg
    from lds_sdk.video_host import comfy_fs
    from PIL import Image
    with image_source(user_id, descriptor, frame) as source:
        folder = comfy_fs.ensure_input_usable(cfg.comfyui_dir('input'))
        name = f'lds_vstudio_{uuid.uuid4().hex[:10]}.png'
        path = comfy_fs.stage_input_image(str(source), name, folder)
        with Image.open(path) as image:
            ratio = image.width / image.height
    return {'image': name, 'ratio': ratio}


def _interval(facts, kind, start, duration):
    try:
        if isinstance(start, bool) or isinstance(duration, bool):
            raise ValueError
        start = float(0 if start is None else start)
        duration = facts['duration'] - start if duration is None else float(duration)
    except (TypeError, ValueError):
        raise ValueError('Reference interval must use numeric seconds.') from None
    minimum = 2.0 if kind == 'video' else .2
    if not all(math.isfinite(v) for v in (start, duration)) or start < 0:
        raise ValueError('Reference interval must use finite, nonnegative seconds.')
    if not minimum <= duration <= refs.MAX_SECONDS:
        raise ValueError(f'Choose an excerpt between {minimum:g} and 15 seconds; longer clips are not cut automatically.')
    if start + duration > facts['duration'] + .001:
        raise ValueError('The selected excerpt goes beyond this library clip.')
    return start, duration


def stage(user_id, *, kind, descriptor, frame='first', start_seconds=None,
          duration_seconds=None, role='', include_audio=False):
    if kind not in ('image', 'video', 'audio') or not isinstance(include_audio, bool):
        raise ValueError('Choose a valid reference kind and soundtrack option.')
    facts = media_info(user_id, descriptor)
    if frame not in ('first', 'last'):
        raise ValueError('Choose the first or last video frame.')
    provenance = {'library_source': facts['source'], 'source_label': facts['path'].name}
    if kind == 'image':
        provenance['frame'] = frame if facts['media_kind'] == 'video' else None
    else:
        if facts['media_kind'] != 'video':
            raise ValueError('Choose a video library item for a video or audio reference.')
        if (kind == 'audio' or include_audio) and not facts['has_audio']:
            raise ValueError('This library video has no audio track.')
        start, duration = _interval(facts, kind, start_seconds, duration_seconds)
        provenance.update(start_seconds=start, duration_seconds=duration)
    provenance['key'] = json.dumps({'kind': kind, **{key: value for key, value in provenance.items()
        if key != 'source_label'}}, sort_keys=True, separators=(',', ':'))
    if kind == 'image':
        if include_audio:
            raise ValueError('An image reference has no soundtrack.')
        if facts['media_kind'] == 'image':
            return refs.stage_reference(kind=kind, source=facts['path'], user_id=user_id,
                                        role=role, provenance=provenance)
        with tempfile.TemporaryDirectory(prefix='lds-reference-frame-') as scratch:
            path = Path(scratch) / 'frame.png'
            _frame(facts, frame, path)
            return refs.stage_reference(kind=kind, source=path, user_id=user_id,
                                        role=role, provenance=provenance)
    return refs.stage_reference(kind=kind, source=facts['path'],
        source_window=(facts['start'] + start, duration), user_id=user_id,
        role=role, include_audio=include_audio, provenance=provenance)


def preview(user_id, descriptor):
    from lds_sdk.video_host import config as cfg
    from PIL import Image, ImageOps
    facts = media_info(user_id, descriptor)
    stat = facts['path'].stat()
    key = hashlib.sha256(json.dumps([str(facts['path']), stat.st_size, stat.st_mtime_ns,
        facts['start'], facts['end']], sort_keys=True).encode()).hexdigest()
    root = cfg.data_dir() / 'video_reference_previews'
    root.mkdir(parents=True, exist_ok=True)
    target = root / f'{key}.jpg'
    if target.is_file():
        return target
    scratch = root / f'{key}.{uuid.uuid4().hex}.jpg'
    try:
        if facts['media_kind'] == 'video':
            _frame(facts, 'first', scratch, thumbnail=True)
        else:
            with Image.open(facts['path']) as source:
                image = ImageOps.exif_transpose(source)
                image.thumbnail((384, 384))
                image.convert('RGB').save(scratch, 'JPEG', quality=80)
        scratch.replace(target)
    finally:
        scratch.unlink(missing_ok=True)
    return target
