"""Recover old clips which accidentally claimed a LoadVideo input as output."""
import json
import logging
import re
from pathlib import Path
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)
_INPUT = re.compile(r'lds_vref_[0-9a-f]{32}\.mp4\Z')
_WRITERS = {'SaveVideo', 'H3FastWriteVideo', 'LDSH3FastWriteVideo', 'VHS_VideoCombine'}


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
    if not job or job.user_id != clip.user_id or not job.comfyui_prompt_id:
        return False
    try:
        workflow = json.loads(job.workflow_data or '{}')
        url = str(cfg.get('comfyui.api_url') or '').rstrip('/')
        if not url:
            return False
        response = requests.get(f'{url}/history/{quote(job.comfyui_prompt_id, safe="")}', timeout=10)
        response.raise_for_status()
        entry = response.json().get(job.comfyui_prompt_id) or {}
        filename = saved_video(entry, workflow)
        if not filename:
            return False
        studio._bring_clip_home(filename)
        path = Path(studio.clips_dir()) / filename
        if not path.is_file() or not path.stat().st_size:
            return False
        clip.filename = filename
        job.result_filename = filename
        db.session.commit()
        log.info('video studio: recovered the saved output for clip %s', clip.id)
        return True
    except (requests.RequestException, OSError, ValueError, TypeError, AttributeError):
        log.warning('video studio: saved output recovery unavailable for clip %s', clip.id)
        return False
