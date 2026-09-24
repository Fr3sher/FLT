"""Recover old clips which accidentally claimed a LoadVideo input as output."""
import json
import logging
import re
from pathlib import Path
from urllib.parse import quote

import requests
from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)
_INPUT = re.compile(r'lds_vref_[0-9a-f]{32}\.mp4\Z')
_WRITERS = {'SaveVideo', 'H3FastWriteVideo', 'LDSH3FastWriteVideo', 'VHS_VideoCombine'}
_PREFIX = re.compile(r'local_lds_video_test_[0-9a-f]{8}\Z')


def _graph(workflow):
    """Compare executed inputs, ignoring ComfyUI's transient is_changed cache."""
    if not isinstance(workflow, dict) or not workflow:
        return None
    if any(not isinstance(node, dict) or 'class_type' not in node or 'inputs' not in node
           for node in workflow.values()):
        return None
    return {key: {'class_type': node['class_type'], 'inputs': node['inputs']}
            for key, node in workflow.items()}


def _matches_saved_workflow(path, workflow):
    """A filename alone cannot identify a render: require its embedded graph."""
    from .video_probe import _open, _duration_seconds
    try:
        with _open(str(path)) as container:
            if not container.streams.video:
                return False
            stream = container.streams.video[0]
            if not stream.width or not stream.height or not (_duration_seconds(container, stream) or 0) > 0:
                return False
            embedded = json.loads(container.metadata.get('prompt') or '{}')
            return _graph(embedded) == _graph(workflow) is not None
    except (ImportError, OSError, ValueError, TypeError):
        return False


def local_saved_video(workflow, directories):
    """Find an unambiguous local MP4 after ComfyUI has forgotten its history.

    Only this job's generated saver prefix is searched. Full embedded inputs
    must match; source videos, prefix collisions and symlinks are not claimed.
    """
    if _graph(workflow) is None:
        return None
    prefixes = {node['inputs'].get('filename_prefix') for node in workflow.values()
                if node['class_type'] in _WRITERS and isinstance(node['inputs'], dict)}
    if len(prefixes) != 1:
        return None
    prefix = next(iter(prefixes))
    if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix):
        return None
    pattern = re.compile(re.escape(prefix) + r'_\d+_?\.mp4\Z')
    candidates = set()
    for directory in directories:
        if not directory:
            continue
        root = Path(directory).resolve()
        for path in root.glob(prefix + '_*.mp4'):
            if (pattern.fullmatch(path.name) and not path.is_symlink()
                    and path.resolve().parent == root and path.is_file()
                    and _matches_saved_workflow(path, workflow)):
                candidates.add(path.name)
    return next(iter(candidates)) if len(candidates) == 1 else None


def saved_video(entry, workflow):
    """Use the exact job's successful saver output, never a preview or input."""
    status = entry.get('status') or {}
    if status.get('status_str') != 'success' or not status.get('completed'):
        return None
    candidates = set()
    for node_id, output in (entry.get('outputs') or {}).items():
        if (workflow.get(str(node_id)) or {}).get('class_type') not in _WRITERS:
            continue
        for key in ('images', 'gifs'):
            for item in output.get(key) or []:
                name = item.get('filename') if isinstance(item, dict) else None
                if (isinstance(name, str) and name.lower().endswith('.mp4')
                        and not any(c in name for c in ('/', '\\', ':', '\0'))
                        and item.get('type') == 'output' and not item.get('subfolder')):
                    candidates.add(name)
    return next(iter(candidates)) if len(candidates) == 1 else None


def recover(clip):
    """Lazy repair on playback, scoped to an already-authorized clip and job.

    Existing good files and ambiguous/failed jobs are never replaced. The row
    changes only after the exact saved MP4 has reached the clip directory.
    """
    if clip.status != 'done' or not _INPUT.fullmatch(clip.filename or ''):
        return False
    from lds_sdk.video_host import config as cfg
    from lds_sdk.video_host.models import ImageGenerationQueue
    from .models import db
    from . import video_test_studio as studio
    job = ImageGenerationQueue.query.filter_by(job_id=clip.job_id).first()
    if not job or job.user_id != clip.user_id or job.status != 'completed':
        return False
    try:
        workflow = json.loads(job.workflow_data or '{}')
        url = str(cfg.get('comfyui.api_url') or '').rstrip('/')
        entry = {}
        if url and job.comfyui_prompt_id:
            try:
                response = requests.get(f'{url}/history/{quote(job.comfyui_prompt_id, safe="")}', timeout=(3, 5))
                response.raise_for_status()
                entry = response.json().get(job.comfyui_prompt_id) or {}
            except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                log.info('video studio: history unavailable for clip %s (%s); checking saved MP4 metadata',
                         clip.id, type(exc).__name__)
        filename = saved_video(entry, workflow)
        local_match = False
        if not entry:
            from lds_sdk.video_host import studio as lts
            filename = local_saved_video(workflow, (studio.clips_dir(create=False), lts.comfy_output_dir()))
            local_match = bool(filename)
        if not filename:
            return False
        studio._bring_clip_home(filename)
        path = Path(studio.clips_dir()) / filename
        if not path.is_file() or not path.stat().st_size:
            return False
        if local_match and not _matches_saved_workflow(path, workflow):
            return False
        clip.filename = filename
        job.result_filename = filename
        db.session.commit()
        log.info('video studio: recovered the saved output for clip %s', clip.id)
        return True
    except (requests.RequestException, OSError, ValueError, TypeError, AttributeError, SQLAlchemyError) as exc:
        db.session.rollback()
        log.warning('video studio: saved output recovery unavailable for clip %s (%s)',
                    clip.id, type(exc).__name__)
        return False
