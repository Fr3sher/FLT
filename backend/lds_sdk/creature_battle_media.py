"""Bounded access to historical Battle clips without activating Video.

New Battle clips belong to the product. This compatibility adapter only accepts
an explicit historical clip or reference identity owned by the current user and
carrying the old Battle signature. It exposes no global Video history or ORM.
"""
import json
from pathlib import Path
import re

__all__ = ['clip', 'clip_path', 'reference_path']


def _battle(row):
    try:
        references = json.loads(row.get('references_json') or '[]')
        settings = json.loads(row.get('generation_settings') or '{}')
    except (TypeError, ValueError):
        return False
    roles = {ref.get('role') for ref in references if isinstance(ref, dict)
             and ref.get('kind') == 'image'} if isinstance(references, list) else set()
    return ({'pokemon 1', 'pokemon 2'} <= roles
            or isinstance(settings, dict) and settings.get('execution') == 'battle_cloud')


def _query(user_id):
    import sqlalchemy as sa
    from app.extensions import db
    from ._video_schema import video_test_clip
    from .config import local_user
    owner = video_test_clip.c.user_id == str(user_id)
    if str(user_id) == str(local_user()):
        owner = sa.or_(owner, video_test_clip.c.user_id.is_(None))
    return db, video_test_clip, sa.select(video_test_clip).where(owner)


def clip(user_id, clip_id):
    if not re.fullmatch(r'[1-9][0-9]{0,18}', str(clip_id)) or int(clip_id) > 2**63 - 1:
        raise LookupError('Historical Battle clip not found.')
    db, table, query = _query(user_id)
    row = db.session.execute(query.where(table.c.id == int(clip_id))).mappings().first()
    if row is None or not _battle(row):
        raise LookupError('Historical Battle clip not found.')
    allowed = ('id', 'status', 'error', 'filename', 'prompt', 'mode', 'job_id', 'source_image',
               'end_image', 'seed', 'steps', 'frames', 'megapixels', 'fps', 'base_model',
               'lora', 'lora_strength', 'accel', 'sparse', 'ref_base', 'ref_image_size',
               'aspect', 'generation_settings', 'references_json', 'continues_of',
               'render_seconds', 'rating')
    return {key: row[key] for key in allowed}


def _safe_file(name):
    from .config import data_dir
    root = (Path(data_dir()) / 'video_tests').resolve()
    path = root / name
    if Path(name).name != name or path.is_symlink() or path.resolve().parent != root or not path.is_file():
        raise LookupError('Historical Battle media is no longer available.')
    return path


def clip_path(user_id, clip_id):
    row = clip(user_id, clip_id)
    if row['status'] != 'done' or not row['filename']:
        raise LookupError('Historical Battle clip is not ready.')
    return _safe_file(row['filename'])


def reference_path(user_id, name):
    from .h3_reference_graph import safe_name
    name = safe_name(name)
    db, table, query = _query(user_id)
    # A named input narrows the query before reading rows; user ownership and
    # the Battle signature are independently checked before any file is read.
    rows = db.session.execute(query.where(table.c.references_json.contains(name)).limit(200)).mappings()
    for row in rows:
        if not _battle(row):
            continue
        for index, reference in enumerate(json.loads(row['references_json'] or '[]')):
            if isinstance(reference, dict) and reference.get('name') == name:
                try:
                    return _safe_file(f"clip_{row['id']}_ref_{index}{Path(name).suffix}")
                except LookupError:
                    continue
    raise LookupError('Historical Battle reference is no longer available.')
