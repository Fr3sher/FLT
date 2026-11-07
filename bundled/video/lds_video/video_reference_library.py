"""Owned library rows for H3 references: identifiers in, never client paths."""
import math
from pathlib import Path
from urllib.parse import urlencode

from sqlalchemy import or_

from lds_video.models import db
from lds_sdk.video_media_library import list_images, image_path
from lds_video.models import VideoBank, VideoClip, VideoDataset, VideoDatasetClip, VideoSource, VideoTestClip

SOURCES = {'bank': 'Image Bank', 'gallery': 'Gallery', 'dataset': 'Image datasets',
           'video_bank': 'Video Bank', 'video_dataset': 'Video datasets', 'studio': 'Rendered clips'}
IMAGE_SOURCES = {'bank', 'gallery', 'dataset'}
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi'}
COLLECTIONS = {'bank': None, 'dataset': None, 'video_bank': VideoBank,
               'video_dataset': VideoDataset}


def _integer(value, name, *, minimum=1, maximum=2_147_483_647):
    if isinstance(value, bool) or not str(value).isdigit():
        raise ValueError(f'Invalid {name}.')
    number = int(value)
    if not minimum <= number <= maximum:
        raise ValueError(f'Invalid {name}.')
    return number


def _kind(kind, source):
    if kind not in ('image', 'video', 'audio') or source not in SOURCES:
        raise ValueError('Choose a supported reference kind and library.')
    if kind != 'image' and source in IMAGE_SOURCES:
        raise ValueError('This library contains images; choose a video library for video or audio.')


def _collection(user_id, source, collection_id):
    model = COLLECTIONS[source]
    row = model.query.filter_by(id=_integer(collection_id, 'collection'), user_id=str(user_id)).first()
    if row is None:
        raise LookupError('Library collection not found.')
    return row


def _query(user_id, source):
    if source == 'video_bank':
        return (VideoClip.query.join(VideoBank).join(VideoSource, VideoClip.source_id == VideoSource.id)
            .filter(VideoBank.user_id == str(user_id), VideoSource.bank_id == VideoClip.bank_id,
                    VideoClip.end_s > VideoClip.start_s), VideoSource.relpath)
    if source == 'video_dataset':
        return (VideoDatasetClip.query.join(VideoDataset).filter(
            VideoDataset.user_id == str(user_id)), VideoDatasetClip.filename)
    return (VideoTestClip.query.filter(or_(VideoTestClip.user_id == str(user_id),
            VideoTestClip.user_id.is_(None)), VideoTestClip.status == 'done',
            VideoTestClip.filename.isnot(None)), VideoTestClip.filename)


def _positive(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def _item(row, source):
    descriptor = {'type': source, 'id': row.id}
    duration, media_kind = None, 'image' if source in IMAGE_SOURCES else 'video'
    if source in COLLECTIONS:
        descriptor['collection_id'] = row.bank_id if source in ('bank', 'video_bank') else row.dataset_id
    label = getattr(row, 'filename', None) or getattr(row, 'relpath', None)
    if source == 'video_bank':
        origin = db.session.get(VideoSource, row.source_id)
        label = f'{Path(origin.relpath).name} · {row.start_s:g}–{row.end_s:g}s'
        duration = _positive(row.end_s - row.start_s)
    elif source == 'video_dataset':
        dataset = db.session.get(VideoDataset, row.dataset_id)
        media_kind = 'image' if Path(row.filename).suffix.lower() in IMAGE_EXTENSIONS else 'video'
        if media_kind == 'video' and dataset.frames and dataset.fps:
            duration = _positive(dataset.frames / dataset.fps)
    elif source == 'studio' and row.frames and row.fps:
        duration = _positive(row.frames / row.fps)
    preview = '/api/video-studio/reference-library/preview?' + urlencode(descriptor)
    return {'key': f'{source}:{row.id}', 'label': str(label or f'Clip {row.id}').replace('\\', '/').rsplit('/', 1)[-1],
            'source': descriptor, 'preview_url': preview, 'media_kind': media_kind,
            'duration': duration, 'has_audio': False if media_kind == 'image' else None}


def list_library(user_id, *, kind='image', source=None, collection_id=None, offset=0, limit=40, q=''):
    source = source or ('bank' if kind == 'image' else 'video_bank')
    _kind(kind, source)
    offset = _integer(offset, 'offset', minimum=0, maximum=100_000)
    limit = _integer(limit, 'limit', maximum=60)
    if not isinstance(q, str) or len(q) > 200:
        raise ValueError('Search text must contain at most 200 characters.')
    if source in IMAGE_SOURCES:
        page = list_images(user_id, source, collection_id=collection_id, offset=offset, limit=limit, q=q)
        rows = page['rows']
        return {'sources': [{'id': key, 'label': title} for key, title in SOURCES.items()],
                'collections': page['collections'], 'items': [_item(row, source) for row in rows[:limit]],
                'has_more': len(rows) > limit, 'next_offset': offset + limit if len(rows) > limit else None}
    query, label = _query(user_id, source)
    model = query.column_descriptions[0]['entity']
    collections = []
    if source in COLLECTIONS:
        collections = [{'id': row.id, 'label': row.name} for row in
            COLLECTIONS[source].query.filter_by(user_id=str(user_id)).order_by(
                COLLECTIONS[source].name, COLLECTIONS[source].id).limit(200)]
        if collection_id not in (None, ''):
            parent = _collection(user_id, source, collection_id)
            column = model.bank_id if source in ('bank', 'video_bank') else model.dataset_id
            query = query.filter(column == parent.id)
    elif collection_id not in (None, ''):
        raise ValueError('This library has no collection selector.')
    if source == 'video_dataset' and kind != 'image':
        query = query.filter(or_(*(model.filename.ilike('%' + ext) for ext in VIDEO_EXTENSIONS)))
    if q.strip():
        escaped = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(label.ilike('%' + escaped + '%', escape='\\'))
    rows = query.order_by(model.id.desc()).offset(offset).limit(limit + 1).all()
    return {'sources': [{'id': key, 'label': title} for key, title in SOURCES.items()
                        if kind == 'image' or key not in IMAGE_SOURCES],
            'collections': collections, 'items': [_item(row, source) for row in rows[:limit]],
            'has_more': len(rows) > limit, 'next_offset': offset + limit if len(rows) > limit else None}


def _contained(path, *roots):
    if path is None:
        raise LookupError('That library file is no longer available.')
    target = Path(path).resolve()
    if not target.is_file() or not any(target.is_relative_to(Path(root).resolve()) for root in roots):
        raise LookupError('That library file is no longer available.')
    return target


def resolve(user_id, descriptor):
    """Resolve one owned row to its displayed media and source PTS interval."""
    if not isinstance(descriptor, dict) or set(descriptor) - {'type', 'id', 'collection_id'}:
        raise ValueError('Select a library item by its identifier.')
    source = descriptor.get('type')
    if not isinstance(source, str) or source not in SOURCES:
        raise ValueError('Unsupported reference library.')
    ident = _integer(descriptor.get('id'), 'library item')
    if source in IMAGE_SOURCES:
        collection_id = descriptor.get('collection_id')
        path = image_path(user_id, source, ident, collection_id=collection_id)
        canonical = {'type': source, 'id': ident}
        if source != 'gallery':
            canonical['collection_id'] = int(collection_id)
        return {'path': path, 'media_kind': 'image', 'start': 0.0, 'end': None, 'source': canonical}
    query, _ = _query(user_id, source)
    model = query.column_descriptions[0]['entity']
    row = query.filter(model.id == ident).first()
    if row is None:
        raise LookupError('Library item not found.')
    if source in COLLECTIONS:
        parent = _collection(user_id, source, descriptor.get('collection_id'))
        actual = row.bank_id if source in ('bank', 'video_bank') else row.dataset_id
        if parent.id != actual:
            raise LookupError('Library item not found in this collection.')
    elif descriptor.get('collection_id') is not None:
        raise ValueError('This library item has no collection identifier.')
    start, end = 0.0, None
    media_kind = 'image' if source in IMAGE_SOURCES else 'video'
    if source == 'video_bank':
        from lds_video import video_bank_service as banks
        path = banks.source_media_path(user_id, row.bank_id, row.source_id)
        path = _contained(path, parent.source_path)
        start, end = float(row.start_s), float(row.end_s)
        if not all(math.isfinite(t) for t in (start, end)) or start < 0 or end <= start:
            raise ValueError('This video clip has invalid time bounds.')
    elif source == 'video_dataset':
        from lds_video import video_bank_service as banks
        path = _contained(banks.dataset_clip_media_path(user_id, row.dataset_id, row.id), parent.output_dir)
        media_kind = 'image' if path.suffix.lower() in IMAGE_EXTENSIONS else 'video'
    else:
        from lds_video import video_test_studio as studio
        root = studio.clips_dir()
        path = _contained(root / row.filename, root)
    canonical = {'type': source, 'id': ident}
    if source in COLLECTIONS:
        canonical['collection_id'] = parent.id
    return {'path': path, 'media_kind': media_kind, 'start': start, 'end': end,
            'source': canonical}
