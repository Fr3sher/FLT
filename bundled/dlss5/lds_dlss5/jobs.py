"""Standalone imported clips and durable result records; no Video tables."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import threading
import uuid

from lds_sdk.lifecycle import state_change_lock
from . import runtime, neural_render as nr

MAX_UPLOAD = 512 * 1024 * 1024
EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v'}
_LOCK = threading.RLock()
_ACTIVE = {}


def root():
    folder = runtime.context().data_dir / 'clips'
    if folder.is_symlink() or folder.resolve() != folder.absolute():
        raise nr.NeuralRenderError('The DLSS clip folder cannot be a linked directory.')
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def folder(ident):
    if not isinstance(ident, str) or len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident):
        raise nr.NeuralRenderError('Clip not found.')
    base = root()
    target = base / ident
    if target.resolve().parent != base or target.is_symlink():
        raise nr.NeuralRenderError('Clip not found.')
    return target


def read(ident):
    path = folder(ident) / 'record.json'
    if path.is_symlink() or not path.is_file():
        raise nr.NeuralRenderError('Clip not found.')
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        raise nr.NeuralRenderError('The clip record is unreadable.') from exc
    if not isinstance(record, dict) or record.get('id') != ident:
        raise nr.NeuralRenderError('The clip record is invalid.')
    return record


def save(record):
    location = folder(record['id'])
    part = location / 'record.json.part'
    final = location / 'record.json'
    if part.is_symlink() or final.is_symlink():
        raise nr.NeuralRenderError('The clip record cannot be a linked file.')
    part.write_text(json.dumps(record), encoding='utf-8')
    os.replace(part, final)


def imported(upload):
    suffix = Path(upload.filename or '').suffix.lower()
    if suffix not in EXTENSIONS:
        raise nr.NeuralRenderError('Choose an MP4, MOV, MKV, WebM, AVI or M4V video.')
    ident = uuid.uuid4().hex
    destination = folder(ident)
    destination.mkdir()
    path = destination / ('original' + suffix)
    size = 0
    try:
        with path.open('xb') as output:
            while chunk := upload.stream.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise nr.NeuralRenderError('Choose a clip smaller than 512 MB.')
                output.write(chunk)
        if not size:
            raise nr.NeuralRenderError('The video file is empty.')
        record = {'id': ident, 'name': Path((upload.filename or 'video').replace('\\', '/')).name,
                  'original': path.name, 'state': 'ready', 'progress': {}, 'error': None,
                  'params': nr.DEFAULT_PARAMS, 'has_result': False}
        save(record)
        return record
    except Exception:
        path.unlink(missing_ok=True)
        destination.rmdir()
        raise


def media_path(ident, result=False):
    record = read(ident)
    if result and not record.get('has_result'):
        raise nr.NeuralRenderError('No rendered result is available.')
    name = 'render.mp4' if result else record.get('original', '')
    base = folder(ident)
    path = base / name
    if Path(name).name != name or path.resolve().parent != base or not path.is_file():
        raise nr.NeuralRenderError('The clip file is unavailable.')
    return path


def listing():
    records = []
    for path in root().iterdir():
        try:
            records.append(read(path.name))
        except nr.NeuralRenderError:
            continue
    return records


def recover():
    for record in listing():
        if record.get('state') in ('queued', 'running', 'cancelling'):
            record.update(state='failed', error='The render was interrupted when LDS stopped. Try again.')
            save(record)


def busy():
    with _LOCK:
        return bool(_ACTIVE)


def cancel(ident):
    read(ident)
    with _LOCK:
        event = _ACTIVE.get(ident)
        if event is not None:
            event.set()
        return event is not None


def start(app, ident, raw):
    params = nr.normalize_params(raw)
    with state_change_lock, _LOCK:
        if _ACTIVE:
            raise nr.NeuralRenderError('A DLSS render is already running. Let it finish or cancel it.')
        record = read(ident)
        source = media_path(ident)
        ready = nr.status()
        if not ready['ready']:
            raise nr.NeuralRenderError('Prepare DLSS 5 first: ' + '; '.join(ready['missing']))
        # Acquire before publishing the job. Disable/remove cannot win between
        # the successful request and the background worker's first instruction.
        lease = ExitStack()
        lease.enter_context(runtime.context().use_plugin_worker())
        event = threading.Event()
        _ACTIVE[ident] = event
        record.update(state='running', error=None, progress={}, params=params)
        try:
            save(record)
        except Exception:
            _ACTIVE.pop(ident, None)
            lease.close()
            raise

    def run():
        with app.app_context(), lease:
            temporary = folder(ident) / 'render.part.mp4'
            try:
                def progress(value):
                    with _LOCK:
                        record['progress'] = {k: v for k, v in value.items()
                                              if k in ('frame', 'frames', 'total', 'fps', 'event')}
                        save(record)
                result = nr.render_video(source, temporary, params,
                                         cancel=event.is_set, on_progress=progress)
                if event.is_set():
                    raise nr.NeuralRenderError('cancelled')
                os.replace(temporary, folder(ident) / 'render.mp4')
                record.update(state='done', has_result=True,
                              params=nr.render_record(params, result))
            except Exception as exc:
                record.update(state='cancelled' if event.is_set() else 'failed',
                              error=str(exc) if isinstance(exc, nr.NeuralRenderError)
                              else 'The render failed. Check DLSS preparation and try again.')
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                    with _LOCK:
                        save(record)
                finally:
                    with _LOCK:
                        _ACTIVE.pop(ident, None)

    try:
        thread = threading.Thread(target=run, name='dlss5-render', daemon=True)
        thread.start()
    except Exception:
        try:
            with _LOCK:
                _ACTIVE.pop(ident, None)
                record.update(state='failed', error='Could not start the rendering worker.')
                save(record)
        finally:
            lease.close()
        raise
    return record
