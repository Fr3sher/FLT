"""Bounded reference media, stable labels and replayable H3 inputs.

Only minted names backed by this instance's manifest may reach a media loader.
Videos are decoded into a short 24 fps MP4; audio becomes a bounded WAV. Clip
sidecars keep the actual inputs so clearing ComfyUI's input folder is harmless.
"""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_SECONDS = 15.0
MAX_ROLE_CHARS = 500
VIDEO_SHORT_EDGE = 768
VIDEO_MAX_PIXELS = 768 * 1344
EXTENSIONS = {
    'image': {'.png', '.jpg', '.jpeg', '.webp', '.bmp'},
    'video': {'.mp4', '.mov', '.mkv', '.webm', '.avi'},
    'audio': {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac'},
}



# Rendering primitives are shared with independently installed Live.
from lds_sdk.h3_reference_graph import (
    LIMITS as LIMITS,
    NAME as NAME,
    VIDEO_GRID as VIDEO_GRID,
    safe_name as _safe_name,
    graft as graft,
    label_references as label_references,
    reference_format_ratio as reference_format_ratio,
)
def _owner(user_id=None):
    from lds_sdk.video_host.config import LOCAL_USER
    return str(LOCAL_USER if user_id is None else user_id)


def _manifest_dir():
    from lds_sdk.video_host import config as cfg
    folder = cfg.data_dir() / 'video_reference_inputs'
    folder.mkdir(parents=True, exist_ok=True)
    return folder




def _manifest(name, user_id=None):
    name = _safe_name(name)
    try:
        data = json.loads((_manifest_dir() / f'{name}.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('that reference is no longer available — pick it again') from exc
    if not isinstance(data, dict) or data.get('owner') != _owner(user_id):
        raise ValueError('that reference belongs to another workspace')
    return data


def _input_path(name):
    from lds_sdk.video_host import config as cfg
    from lds_sdk.video_host import comfy_fs
    folder = Path(comfy_fs.ensure_input_usable(cfg.comfyui_dir('input'))).resolve()
    path = folder / _safe_name(name)
    if path.resolve().parent != folder or path.is_symlink():
        raise ValueError('invalid reference path')
    return path


def sidecar(clip_id, index, name):
    from lds_video.video_test_studio import clips_dir
    return clips_dir() / f'clip_{int(clip_id)}_ref_{int(index)}{Path(_safe_name(name)).suffix}'


def path_for(name, user_id=None, restage=True):
    """Resolve only an input minted by this instance and owned by this user."""
    _manifest(name, user_id)
    path = _input_path(name)
    if path.is_file():
        return path
    if restage:
        from lds_video.models import VideoTestClip
        rows = VideoTestClip.query.filter(VideoTestClip.references_json.isnot(None)).all()
        for clip in rows:
            if getattr(clip, 'user_id', None) not in (None, _owner(user_id)):
                continue
            for index, ref in enumerate(references_of(clip)):
                if ref.get('name') != name:
                    continue
                kept = sidecar(clip.id, index, name)
                if kept.is_file() and not kept.is_symlink():
                    tmp = path.with_name(f'{name}.part-{uuid.uuid4().hex}')
                    try:
                        shutil.copyfile(kept, tmp)
                        os.replace(tmp, path)
                    finally:
                        tmp.unlink(missing_ok=True)
                    return path
    raise ValueError('that reference is no longer staged — pick it again')




def validate_references(references, *, restage=True, user_id=None, enforce_limits=True):
    if not isinstance(references, list) or not references:
        raise ValueError('Add at least one image, video or audio reference.')
    if enforce_limits and len(references) > sum(LIMITS.values()):
        raise ValueError('Too many references: at most 9 images, 3 videos and 3 audio files.')
    counts = dict.fromkeys(LIMITS, 0)
    out = []
    for ref in references:
        if (not isinstance(ref, dict) or not isinstance(ref.get('kind'), str)
                or ref['kind'] not in LIMITS):
            raise ValueError('invalid reference kind')
        kind = ref['kind']
        counts[kind] += 1
        if enforce_limits and counts[kind] > LIMITS[kind]:
            raise ValueError(f'Too many {kind} references (maximum {LIMITS[kind]}).')
        meta = _manifest(ref.get('name'), user_id)
        if meta['kind'] != kind:
            raise ValueError('reference kind does not match its staged media')
        if kind == 'video' and meta.get('frame_count') is not None:
            _require_video_length(meta['frame_count'])
        if restage:
            path_for(ref['name'], user_id=user_id)
        role = ref.get('role') or ''
        if not isinstance(role, str) or len(role) > MAX_ROLE_CHARS:
            raise ValueError(f'Reference roles must be text of at most {MAX_ROLE_CHARS} characters.')
        include_audio = ref.get('include_audio', False)
        if not isinstance(include_audio, bool):
            raise ValueError('include_audio must be true or false')
        if include_audio and (kind != 'video' or not meta.get('has_audio')):
            raise ValueError('that reference has no video soundtrack to include')
        out.append({k: v for k, v in meta.items() if k != 'owner'} | {
            'role': role.strip(), 'include_audio': include_audio,
        } | ({'use_format': ref['use_format']} if 'use_format' in ref else {}))
    reference_format_ratio(out)
    return label_references(out)




def _probe(path, kind, *, bounded=True):
    """Probe only supported container demuxers; playlists cannot read other files."""
    from lds_sdk.video_host import ffmpeg_tools
    from lds_video.video_test_studio import _run_ffmpeg
    ffmpeg = ffmpeg_tools.ffmpeg_path()
    if not ffmpeg:
        raise ValueError('Reference video and audio need ffmpeg — install the video extras in Setup.')
    formats = ('mov,matroska,avi' if kind == 'video'
               else 'mov,matroska,avi,mp3,wav,flac,ogg,aac')
    prefix = [str(ffmpeg), '-hide_banner', '-nostdin', '-protocol_whitelist', 'file,pipe',
              '-format_whitelist', formats]
    result = _run_ffmpeg([*prefix, '-i', str(path)], timeout=20)
    text = result.stderr or ''
    match = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', text)
    if not match:
        raise ValueError('Could not read the reference duration; use an MP4 video or WAV audio file.')
    seconds = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    minimum = 2.0 if kind == 'video' else 0.2
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Could not read a positive media duration.')
    if bounded and not minimum <= seconds <= MAX_SECONDS + 0.05:
        raise ValueError(f'Reference {kind} must last between {minimum:g} and {MAX_SECONDS:g} seconds.')
    video = re.search(r'Stream #\d+:\d+.*?: Video:.*? (\d{2,5})x(\d{2,5})', text)
    has_audio = re.search(r'Stream #\d+:\d+.*?: Audio:', text) is not None
    if kind == 'video' and not video:
        raise ValueError('That file has no readable video stream.')
    if kind == 'audio' and not has_audio:
        raise ValueError('That file has no readable audio stream.')
    if video and (int(video[1]) > 8192 or int(video[2]) > 8192
                  or int(video[1]) * int(video[2]) > 16_777_216):
        raise ValueError('Reference video dimensions are too large; resize it before uploading.')
    fps_match = re.search(r'Video:[^\n]*?([\d.]+) fps', text) if video else None
    width, height = (int(video[1]), int(video[2])) if video else (None, None)
    video_details = re.split(r'\n\s*Stream #', text[video.end():], maxsplit=1)[0] if video else ''
    rotation = re.search(r'rotation of\s+(-?[\d.]+)\s+degrees', video_details)
    if video and rotation and round(float(rotation[1]) / 90) % 2:
        width, height = height, width  # ffmpeg autorotates before the scale filter.
    return prefix, {'duration': round(min(seconds, MAX_SECONDS) if bounded else seconds, 3), 'has_audio': has_audio,
                    'width': width, 'height': height,
                    'fps_native': float(fps_match[1]) if fps_match else None}


def video_canvas(width, height):
    """H3's native reference canvas, rounded to 32 without enlarging inputs.

    Native MiniMaxH3ReferenceToVideo applies adapt_canvas only AFTER its input
    video has been decoded into a float32 frame batch. Encoding this size here
    avoids materializing full-resolution frames that it immediately discards.
    Small sources stay below their original dimensions, including grid rounding.
    """
    width, height = int(width), int(height)
    if min(width, height) < VIDEO_GRID:
        raise ValueError('Reference video must be at least 32 pixels on each side.')
    scale = min(1.0, VIDEO_SHORT_EDGE / min(width, height),
                math.sqrt(VIDEO_MAX_PIXELS / (width * height)))
    return tuple(min(source // VIDEO_GRID * VIDEO_GRID,
                     max(VIDEO_GRID, round(source * scale / VIDEO_GRID) * VIDEO_GRID))
                 for source in (width, height))


def _require_video_length(frame_count):
    # Container duration can come entirely from a longer audio track. H3
    # consumes the decoded images, so the promised two seconds means 48 images.
    if int(frame_count) < 48:
        raise ValueError('Reference video must contain at least 2 seconds of video (48 frames at 24 fps).')


def stage_reference(*, kind, upload=None, source=None, user_id=None, role='', include_audio=False,
                    source_window=None, provenance=None):
    if not isinstance(kind, str) or kind not in LIMITS:
        raise ValueError('Choose an image, video or audio reference.')
    if not isinstance(role, str) or len(role) > MAX_ROLE_CHARS:
        raise ValueError('Reference role is too long.')
    temp = None
    dest = None
    try:
        if upload is not None:
            suffix = Path(str(upload.filename or '')).suffix.lower()
            if suffix not in EXTENSIONS[kind]:
                raise ValueError(f'Unsupported {kind} file type.')
            fd, temp = tempfile.mkstemp(suffix=suffix)
            size = 0
            with os.fdopen(fd, 'wb') as target:
                while chunk := upload.stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ValueError('Reference file is too large (maximum 256 MiB).')
                    target.write(chunk)
            source = temp
        elif source is None or (kind != 'image' and source_window is None):
            raise ValueError('Attach a reference file.')
        suffix = {'image': '.png', 'video': '.mp4', 'audio': '.wav'}[kind]
        name = f'lds_vref_{uuid.uuid4().hex}{suffix}'
        dest = _input_path(name)
        if kind == 'image':
            from lds_sdk.video_host import comfy_fs
            from PIL import Image
            comfy_fs.stage_input_image(str(source), name, str(dest.parent))
            with Image.open(dest) as image:
                meta = {'width': image.width, 'height': image.height,
                        'duration': None, 'has_audio': False}
        else:
            from lds_video.video_test_studio import _run_ffmpeg
            prefix, meta = _probe(source, kind, bounded=source_window is None)
            seek, duration = [], MAX_SECONDS
            if source_window is not None:
                start, duration = map(float, source_window)
                minimum = 2.0 if kind == 'video' else .2
                if (not all(math.isfinite(v) for v in (start, duration)) or start < 0
                        or not minimum <= duration <= MAX_SECONDS
                        or start + duration > meta['duration'] + .05):
                    raise ValueError('The selected reference interval is outside this media file.')
                seek = ['-ss', f'{start:.3f}']          # fixed decimals: ffmpeg refuses 1e-05
                meta['duration'] = duration
            command = [*prefix, *seek, '-i', str(source), '-t', str(duration), '-map_metadata', '-1',
                       '-map_chapters', '-1', '-threads', '2']
            if kind == 'video':
                width, height = video_canvas(meta['width'], meta['height'])
                meta.update(source_width=meta['width'], source_height=meta['height'],
                            width=width, height=height, duration_original=meta['duration'])
                # After an input seek the first decoded frame carries a timestamp
                # offset of up to one frame; fps=24 rounded it to slot 1 and a
                # 2.0 s cut came out 47 frames (measured for 16 of 40 starts at
                # the panel's 0.1 s step, review of 2026-09-06). Rebasing the
                # timestamps first keeps every frame of the interval.
                filters = ('setpts=PTS-STARTPTS,' if seek else '') + f'scale={width}:{height}:flags=lanczos,setsar=1,fps=24'
                command += ['-map', '0:v:0', '-map', '0:a:0?', '-vf', filters,
                            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
                            '-c:a', 'aac', '-ac', '2', '-ar', '48000', '-movflags', '+faststart',
                            '-progress', 'pipe:1', '-nostats']
            else:
                command += ['-map', '0:a:0', '-vn', '-c:a', 'pcm_s16le', '-ac', '1', '-ar', '48000']
            result = _run_ffmpeg([*command, '-y', str(dest)], timeout=90)
            if result.returncode or not dest.is_file() or dest.stat().st_size == 0:
                raise ValueError('Could not decode that reference; export it as MP4 video or WAV audio.')
            if kind == 'video':
                counts = re.findall(r'^frame=(\d+)\s*$', result.stdout or '', flags=re.MULTILINE)
                if not counts or int(counts[-1]) < 1:
                    raise ValueError('Could not measure the normalized reference video frame count.')
                meta['frame_count'] = int(counts[-1])
                _require_video_length(meta['frame_count'])
                meta['duration'] = meta['frame_count'] / 24
                if source_window is not None:
                    # The source can have audio only outside this excerpt.
                    # Persist the output's tracks before offering LoadAudio.
                    _, output_meta = _probe(dest, 'video', bounded=False)
                    meta['has_audio'] = output_meta['has_audio']
            else:
                import wave
                with wave.open(str(dest)) as audio:
                    meta['duration'] = audio.getnframes() / audio.getframerate()
                if meta['duration'] < .2:
                    raise ValueError('The selected interval needs at least 0.2 seconds of audio.')
            meta['fps'] = 24 if kind == 'video' else None
        if include_audio and (kind != 'video' or not meta['has_audio']):
            raise ValueError('That reference has no video soundtrack to include.')
        record = {'name': name, 'kind': kind, 'owner': _owner(user_id),
                  'role': role.strip(), 'include_audio': bool(include_audio), **meta}
        if provenance:
            # `source_width`/`source_height` from a cut's parent win over the
            # copy's grid-32 canvas measured above: the format a video fixes
            # must not move a notch when it is cut (review, 2026-09-06).
            record.update({k: provenance[k] for k in ('key', 'library_source', 'source_label',
                'frame', 'start_seconds', 'duration_seconds', 'cut_from', 'cut_source_duration',
                'source_width', 'source_height') if k in provenance})
        manifest = _manifest_dir() / f'{name}.json'
        manifest.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        return {k: v for k, v in record.items() if k != 'owner'}
    except (OSError, subprocess.TimeoutExpired) as exc:
        if dest is not None:
            dest.unlink(missing_ok=True)
        raise ValueError('The reference could not be stored or decoded in time; '
                         'check free disk space and try a smaller file.') from exc
    except Exception:
        if dest is not None:
            dest.unlink(missing_ok=True)
        raise
    finally:
        if temp:
            Path(temp).unlink(missing_ok=True)


def cut_reference(name, start_seconds, duration_seconds, *, user_id=None, role='', include_audio=False):
    """✂ A shorter excerpt of a staged reference VIDEO, prepared as a NEW
    reference from the staged copy itself (an upload is not kept): the same
    normalisation as an upload, the interval checked as a library excerpt is.
    The source copy stays on disk for the clips that already reference it.

    Why it exists (2026-09-06): the graph reads a reference video up to the
    CLIP's length (Video Slice at frames/24, then the H3 node trims to 17k+5),
    so only a cut shorter than the clip lightens the sequence — 107 reference
    frames instead of 175 for a 5 s cut behind a 7.3 s clip, about a sixth of
    the tokens (measured in refutation). A reference render that paged for an
    hour on a 24 GB card had a 7.3 s clip at 1.25 MP, a 1344×768 reference
    canvas and four pictures: the cut is one lever among those, and it belongs
    in the panel where the video is."""
    meta = _manifest(name, user_id)
    if meta.get('kind') != 'video':
        raise ValueError('Only a video reference can be cut.')
    from . import video_reference_selection as selection
    facts = {'duration': float(meta.get('duration') or 0)}
    try:
        start, duration = selection._interval(facts, 'video', start_seconds, duration_seconds)
    except ValueError as exc:
        # The library's sentences, said for a video: there is no library clip here.
        raise ValueError(str(exc).replace('this library clip', 'this video')
                         .replace('; longer clips are not cut automatically', '')) from None
    if start <= .0005 and duration >= facts['duration'] - .0005:
        raise ValueError('Choose a shorter interval than the whole video.')
    # The library key is not carried: it names the parent's excerpt, not this one.
    provenance = {k: meta[k] for k in ('library_source', 'source_label', 'source_width', 'source_height')
                  if k in meta}
    offset = float(meta.get('start_seconds') or 0)
    provenance.update(cut_from=name, cut_source_duration=round(facts['duration'], 3),
                      start_seconds=round(offset + start, 3), duration_seconds=round(duration, 3))
    return stage_reference(kind='video', source=path_for(name, user_id=user_id), user_id=user_id,
                           role=role, include_audio=include_audio, source_window=(start, duration),
                           provenance=provenance)


def references_of(clip):
    try:
        result = json.loads(clip.references_json or '[]')
        return result if isinstance(result, list) else []
    except (TypeError, ValueError, AttributeError):
        return []


def keep_clip_references(clip_id, references, user_id=None):
    """Copy before the queue transaction commits: no unreplayable history row."""
    made = []
    try:
        for index, ref in enumerate(references):
            dest = sidecar(clip_id, index, ref['name'])
            shutil.copyfile(path_for(ref['name'], user_id=user_id), dest)
            made.append(dest)
    except Exception as exc:
        for path in made:
            path.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise ValueError('The reference could not be kept with the clip; check free disk space.') from exc
        raise


def delete_clip_references(clip):
    for index, ref in enumerate(references_of(clip)):
        try:
            sidecar(clip.id, index, ref['name']).unlink(missing_ok=True)
        except (OSError, ValueError, KeyError):
            pass
