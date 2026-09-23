"""One server-owned continuation at a time, paused across application restarts.

The queue keeps clips durable; this small journal only remembers the take and
the next action. A staged basename identifies an enqueue even if its reply is
lost. Captioning never runs in the queue's completion callback.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from pathlib import Path

from lds_sdk.video_host import config as cfg
from lds_sdk.video_host import capabilities
from lds_video.models import db
from lds_sdk.video_runtime import queue as queue_manager, require_comfyui_enqueue_ready
from lds_sdk.video_runtime import job as queue_job
from lds_video.models import VideoTestClip
from lds_sdk.media import redact_tokens, redact_user_paths
from lds_video import video_motion_prompt as vmp
from lds_video import video_test_studio as vts
from lds_sdk.video_host import vision_llm

logger = logging.getLogger(__name__)
_MANAGER_LOCK = threading.Lock()
_SETTINGS = frozenset({
    'lora', 'lora_strength', 'run_id', 'dataset_id', 'seed', 'steps', 'frames',
    'megapixels', 'aspect', 'turbo', 'accel', 'eros', 'light', 'sparse',
    'latent_upscale', 'shots', 'refmods', 'references',
})


def _limit(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000:
        raise ValueError('Clip limit must be a whole number between 0 and 10000 (0 means unlimited).')
    return value


def _direction(value):
    if not isinstance(value, str) or len(value) > 4000:
        raise ValueError('Direction must be text, at most 4000 characters.')
    return value.strip()


def _clip(clip_id):
    return VideoTestClip.query.filter_by(id=clip_id).populate_existing().first()


def _ready(clip):
    return bool(clip and clip.status == 'done' and clip.filename and (
        not clip.continues_of or str(clip.filename).endswith('_joined.mp4')))


def _require_supported_parent(clip):
    if clip is not None and clip.mode == 'ref2va':
        # The refusal stands — the settings a take carries hold no references
        # and every step enqueues i2v, so an automatic continuation would drop
        # the cast — but its REASON changed on 2026-09-07: frame guides are now
        # exactly how a reference clip IS continued, by hand.
        raise ValueError('Automatic continuation carries on from the last frame alone and would '
                         'leave this clip\'s references behind. Continue it by hand to keep its cast.')


CHAIN_MAX = 200     # parts a take is walked back through to find its LoRA


def _chain_lora(clip, limit=CHAIN_MAX):
    """⏭ The character of a take: the LoRA of the clip being continued, or
    of the nearest part above it that carries one, up to the root. None when
    no part of the chain has a LoRA. {lora, lora_strength, clip_id}.

    The nearest part rather than the root alone: a chain rendered before this
    rule carries its LoRA on the root only (twelve parts of one take, none
    with a LoRA, 2026-09-06), and a chain continued by hand with another
    LoRA carries that later choice on the part where it was made."""
    seen = set()
    while clip is not None and clip.id not in seen and len(seen) < limit:
        seen.add(clip.id)
        if clip.user_id not in (None, str(cfg.LOCAL_USER)):
            break
        name = str(clip.lora or '').strip()
        if name:
            strength = clip.lora_strength
            return {'lora': name, 'clip_id': clip.id,
                    'lora_strength': float(strength) if strength is not None else 1.0}
        clip = _clip(clip.continues_of) if clip.continues_of else None
    return None


def _explain(exc, settings=None) -> str:
    """The sentence the panel shows for a failure. A model file the graph
    needs and ComfyUI does not have names its path — and the take's LoRA when
    it is the one missing: a chain can name a weight deleted since it was
    rendered, which the panel could never offer (refutation, 2026-09-06: the
    pause read '2 file(s), 0 node(s)' where the manual launch lists them)."""
    from lds_sdk.video_host import studio as lts
    if not isinstance(exc, lts.StudioAssetsMissing):
        return str(exc)
    paths = [str(f.get('path') or '') for f in (exc.missing_files or []) if isinstance(f, dict)]
    names = ', '.join(p for p in paths if p) or 'unknown files'
    lora = str((settings or {}).get('lora') or '')
    base = lora.replace('\\', '/').rsplit('/', 1)[-1]
    note = (f" The take's LoRA ({lora}) is no longer deployed in ComfyUI."
            if base and any(base in p for p in paths) else '')
    return (f'Model files this take needs are missing in ComfyUI: {names}.{note} '
            'Place them, then Resume.')


def manager(app):
    with _MANAGER_LOCK:
        runner = app.extensions.get('video_auto_continue')
        if runner is None:
            runner = AutoContinuation(app, Path(cfg.data_dir()) / 'video_auto_continue.json')
            app.extensions['video_auto_continue'] = runner
        return runner


class AutoContinuation:
    def __init__(self, app, path):
        self.app, self.path = app, Path(path)
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.thread = None
        self.record = None
        self.recovered_image = None
        if self.path.exists():
            try:
                self.record = json.loads(self.path.read_text(encoding='utf-8'))
                state = self.record['state']
                if not isinstance(state['id'], str) or not isinstance(self.record['settings'], dict):
                    raise ValueError('invalid journal')
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise RuntimeError('The Auto continuation journal could not be read.') from exc
            if state['phase'] not in ('complete', 'stopped') or self.record.get('pending'):
                self.recovered_image = (self.record.get('pending') or {}).get('image')
                state.update(enabled=False, phase='paused',
                             error='The app restarted. Review the take, then Resume when ready.')
                self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        try:
            tmp.write_text(json.dumps(self.record, ensure_ascii=False, allow_nan=False), encoding='utf-8')
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

    def _busy(self):
        return bool(self.thread and self.thread.is_alive())

    def _state(self):
        if self.record is None:
            return None
        state = dict(self.record['state'])
        pending = self.record.get('pending')
        state['draining'] = not state['enabled'] and bool(pending or self._busy())
        state['can_resume'] = (state['phase'] == 'paused' and not pending and not self._busy())
        state['can_abandon'] = self._can_abandon()
        state['job_id'] = pending.get('job_id') if pending else None
        return state

    def _abandonable_child(self):
        """Release only a recovered child whose terminal callback was interrupted.

        A queue row is the authority for GPU completion. The clip row being
        'done' alone is insufficient, and this never repairs or replays a join.
        Its original file remains in history when the user abandons the take.
        """
        pending = self.record.get('pending') if self.record else None
        if (not pending or pending['image'] != self.recovered_image
                or self.record['state']['enabled']):
            return None
        row = (VideoTestClip.query.filter_by(source_image=pending['image'],
                                            continues_of=pending['parent_id'])
               .populate_existing().first())
        if not row or (row.status != 'pending' and (
                row.status != 'done' or not row.filename or _ready(row))):
            return None
        job = queue_job(row.job_id)
        return row if job and job.status in ('completed', 'failed', 'cancelled') else None

    def _can_abandon(self):
        return self._abandonable_child() is not None

    def _check_id(self, session_id):
        if not self.record or session_id != self.record['state']['id']:
            raise RuntimeError('This Auto session has changed. Refresh its state first.')

    def status(self):
        with self.lock:
            # Also reconciles a clip that finished while this process was down.
            if self.record and not self._busy():
                self._reconcile()
            return self._state()

    def start(self, data):
        if not isinstance(data, dict):
            raise ValueError('Expected Auto continuation settings.')
        limit, direction = _limit(data.get('max_clips', 0)), _direction(data.get('direction', ''))
        if isinstance(data.get('clip_id'), bool) or not isinstance(data.get('clip_id'), int):
            raise ValueError('Pick a completed clip to continue.')
        settings = data.get('settings', {})
        if not isinstance(settings, dict):
            raise ValueError('Render settings must be an object.')
        settings = {key: value for key, value in settings.items() if key in _SETTINGS}
        try:
            settings = json.loads(json.dumps(settings, allow_nan=False))
        except (ValueError, TypeError) as exc:
            raise ValueError('Render settings must contain finite values.') from exc
        from lds_sdk.video_host import studio as lts
        if settings.get('lora') and (not isinstance(settings['lora'], str)
                                    or lts.is_unsafe_external_lora_name(settings['lora'])):
            raise ValueError('invalid LoRA name')
        with self.lock:
            if self.record:
                self._reconcile()
                if self.record['state']['enabled'] or self.record.get('pending') or self._busy():
                    raise RuntimeError('An Auto continuation is still running or finishing its current clip.')
            root = _clip(data['clip_id'])
            if not _ready(root):
                raise ValueError('That clip has not finished rendering and joining yet.')
            _require_supported_parent(root)
            model = data.get('model')
            if model is not None and not isinstance(model, str):
                raise ValueError('Choose a motion model by name.')
            model = vmp._writer_model(model) or vision_llm.vision_model()
            # Continue inherits its parent's base, and keeps the original panel
            # length. A joined clip's frames are the cumulative take length.
            settings.update(eros=root.base_model == vts.BASE_EROS,
                            light=root.base_model == vts.BASE_LIGHT)
            if json.loads(root.generation_settings or '{}').get('refmods') is True:
                from . import video_references
                settings.update(refmods=True, references=video_references.references_of(root))
            record = {
                'version': 1, 'settings': settings, 'model': model,
                'provider': vision_llm.provider(), 'parent_clip_id': root.id,
                'pending': None,
                'state': {'id': uuid.uuid4().hex, 'root_clip_id': root.id,
                          'current_clip_id': root.id, 'phase': 'extracting',
                          'enabled': True, 'direction': direction,
                          'max_clips': limit, 'completed': 0, 'error': None,
                          'lora': settings.get('lora') or None,
                          'lora_strength': settings.get('lora_strength') if settings.get('lora') else None,
                          'lora_from_clip_id': None, 'panel_lora': None},
            }
            # ⏭ And its character: the LoRA of the chain, not the panel's
            # choice at the tick (empty for twelve parts of one take,
            # 2026-09-06). Adopted before the record exists: a refused name
            # leaves no journal behind.
            self._adopt_chain_lora(root, replace=True, record=record)
            self.record = record
            self.recovered_image = None
            self._save()
            self._launch_worker()
            return self._state()

    def _adopt_chain_lora(self, clip, *, replace, record=None):
        """⏭ The take takes its chain's LoRA (`_chain_lora`): at the start in
        place of the panel's choice (`replace`), and on Resume only when the
        journal has none — a take journaled before the rule, whose parts carry
        their LoRA on the root alone, gains it there (refutation, 2026-09-06);
        a take that has one keeps it, its settings frozen at the start. The
        origin ids a panel sends belong to ITS LoRA; the enqueue re-derives
        them from the deployed file."""
        record = self.record if record is None else record
        settings = record['settings']
        if settings.get('lora') and not replace:
            return
        inherited = _chain_lora(clip)
        if not inherited:
            return
        from lds_sdk.video_host import studio as lts
        from .video_best_settings import _deployed_path
        if lts.is_unsafe_external_lora_name(inherited['lora']):
            raise ValueError('invalid LoRA name')
        if not _deployed_path(inherited['lora']):
            # A chain can name a weight deleted since it was rendered — a case
            # the panel could never produce. Refused before any journal, with
            # the LoRA and the part named (review, 2026-09-06).
            raise ValueError(
                f"The LoRA kept from clip #{inherited['clip_id']} "
                f"({inherited['lora'].replace(chr(92), '/').rsplit('/', 1)[-1]}) is no longer "
                'deployed in ComfyUI. Deploy it again, or render one part by hand with another LoRA.')
        panel = str(settings.get('lora') or '')
        settings.update(lora=inherited['lora'], lora_strength=inherited['lora_strength'])
        settings.pop('run_id', None)
        settings.pop('dataset_id', None)
        record['state'].update(lora=inherited['lora'], lora_strength=inherited['lora_strength'],
                               lora_from_clip_id=inherited['clip_id'],
                               panel_lora=(panel if panel and panel != inherited['lora'] else None))

    def update(self, data):
        if not isinstance(data, dict):
            raise ValueError('Expected Auto continuation settings.')
        with self.lock:
            self._check_id(data.get('session_id'))
            direction = _direction(data['direction']) if 'direction' in data else None
            limit = _limit(data['max_clips']) if 'max_clips' in data else None
            if direction is not None:
                self.record['state']['direction'] = direction
            if limit is not None:
                self.record['state']['max_clips'] = limit
            self._save()
            self.wake.set()
            return self._state()

    def stop(self, session_id):
        with self.lock:
            self._check_id(session_id)
            state = self.record['state']
            child = self._abandonable_child()
            if child is not None:
                if child.status == 'pending':
                    job = queue_job(child.job_id)
                    filename = job.result_filename if job.status == 'completed' else None
                    if filename and (filename in ('.', '..') or any(c in filename for c in '/\\:\0')):
                        filename = None
                    if filename:
                        vts._bring_clip_home(filename)
                    child.filename = filename
                    child.status = 'done' if child.filename else 'failed'
                    child.error = ('continuation not joined: the app restarted before recording this result. '
                                   'Auto was stopped; any recovered clip has not been joined.')
                    state['error'] = child.error
                else:
                    child.error = 'continuation not joined: the app restarted during assembly; Auto was stopped.'
                    state['error'] = ('Auto was abandoned after the restart: the previous clip finished '
                                      'but its join was interrupted. Its unjoined clip remains in history.')
                db.session.commit()
                self.record['pending'] = None
            state.update(enabled=False, phase='generating' if self.record.get('pending') else 'stopped')
            self._save()
            self.wake.set()
            return self._state()

    def resume(self, session_id):
        with self.lock:
            self._check_id(session_id)
            self._reconcile()
            if not self._state()['can_resume']:
                raise RuntimeError('This take cannot resume while its previous operation is still finishing.')
            parent = _clip(self.record['parent_clip_id'])
            if not _ready(parent):
                raise RuntimeError('The last completed clip is no longer available.')
            _require_supported_parent(parent)
            self._adopt_chain_lora(parent, replace=False)
            self.record['state'].update(enabled=True, error=None, phase='extracting')
            self._save()
            self._launch_worker()
            return self._state()

    def _launch_worker(self):
        if self._busy():
            return
        self.wake.clear()
        self.thread = threading.Thread(target=self._run, name='video-auto-continue', daemon=True)
        try:
            self.thread.start()
        except RuntimeError:
            self.thread = None
            self._pause('The Auto worker could not start. Try Resume.')
            raise

    def _pause(self, error):
        state = self.record['state']
        state.update(enabled=False, phase='paused',
                     error=redact_tokens(redact_user_paths(str(error)))[:600])
        self._save()

    def _reconcile(self):
        pending = self.record.get('pending')
        if not pending:
            return
        # The basename is minted before the enqueue and persisted before any
        # write. This also finds a committed child whose enqueue reply was lost.
        row = (VideoTestClip.query.filter_by(source_image=pending['image'],
                                            continues_of=pending['parent_id'])
               .populate_existing().first())
        if row is None:
            if pending.get('clip_id'):
                self.record['pending'] = None
                self._pause('The current clip was removed. Resume from the last completed clip.')
            elif not self._busy():
                self.record['pending'] = None
                self._save()
            return
        pending.update(clip_id=row.id, job_id=row.job_id)
        state = self.record['state']
        state['current_clip_id'] = row.id
        job = queue_job(row.job_id)
        if _ready(row) and (job is None or job.status == 'completed'):
            self.record['parent_clip_id'] = row.id
            self.record['pending'] = None
            state['completed'] += 1
            if state['phase'] != 'paused':
                state['phase'] = 'extracting' if state['enabled'] else 'stopped'
            self._save()
        elif row.status in ('failed', 'cancelled') or (row.status == 'done' and row.error):
            self.record['pending'] = None
            self._pause(row.error or 'The clip did not finish. Resume to try again from the last completed clip.')
        elif job and job.status in ('stalled', 'cancel_requested'):
            self._pause('The current generation needs recovery in the queue before this take can resume.')
        elif job is None and row.status == 'pending':
            self._pause('The current clip has no queue job. Resolve it before resuming this take.')

    def _run(self):
        try:
            while True:
                with self.app.app_context():
                    try:
                        if not self.step():
                            break
                    except Exception as exc:  # noqa: BLE001 — a writer failure pauses the take
                        db.session.rollback()
                        logger.exception('Auto continuation paused')
                        with self.lock:
                            self._reconcile()
                            # An explicit stop stays stopped when its in-flight
                            # writer returns late, including a late exception.
                            if self.record['state']['enabled']:
                                self._pause(_explain(exc, self.record['settings']))
                        break
                    finally:
                        db.session.remove()
                self.wake.wait(1)
                self.wake.clear()
        finally:
            with self.lock:
                self.thread = None

    def step(self):
        """Advance once. Slow vision work holds no session lock or DB transaction."""
        from lds_video.routes.video_studio import _clip_seconds, _motion_window, enqueue_video_clip, stage_clip_last_frame
        with self.lock:
            self._reconcile()
            state = self.record['state']
            if self.record.get('pending'):
                return state['phase'] != 'paused'
            if not state['enabled']:
                return False
            if state['max_clips'] and state['completed'] >= state['max_clips']:
                state.update(enabled=False, phase='complete')
                self._save()
                return False
            parent_id = self.record['parent_clip_id']
            _require_supported_parent(_clip(parent_id))
            model = self.record['model']
            settings = dict(self.record['settings'])
            if not vmp.uses_chatgpt(model) and vision_llm.provider() != self.record['provider']:
                raise RuntimeError('The local model provider changed. Restore it before resuming this take.')
            state['phase'] = 'extracting'
            self._save()
        require_comfyui_enqueue_ready()
        if not capabilities.probe_comfyui().get('ok'):
            raise RuntimeError('ComfyUI is not reachable. Start it, then Resume.')
        # Local writers need the queue to be empty, including work from other
        # surfaces. The vision window atomically enforces this again on entry.
        # A local observer — JoyCaption reading the last frame — needs both
        # for a GPT writer too: the frame is read on this machine's card.
        from . import video_reference_prompt as vrp
        local_observer = vrp.observer_is_local()
        if (not vmp.uses_chatgpt(model) or local_observer) and queue_manager.has_comfyui_work():
            raise RuntimeError('ComfyUI has queued work. Let it finish, then Resume this take.')
        staged = stage_clip_last_frame(parent_id)
        previous = vts.previous_parts(parent_id)
        db.session.rollback()
        with self.lock:
            if not state['enabled']:
                return False
            state['phase'] = 'writing'
            direction = state['direction']
            self._save()
        with _motion_window(model, flag_ttl=600, local_observer=local_observer) as writer_model:
            prompt = vmp.suggest_from_frame(
                staged['image'], model=writer_model, seconds=_clip_seconds(settings),
                shots=settings.get('shots', 1), previous=previous, direction=direction,
                **({'mode': 'ref2va', 'references': settings['references']} if settings.get('refmods') else {}))
        if settings.get('refmods'):
            from lds_video.h3_refmods import first_frame_prompt
            prompt = first_frame_prompt(prompt)
        else:
            prompt = vmp.inject_alignment_header(prompt)
        if not vmp.has_motion(prompt):
            raise ValueError('The model returned no usable motion. Resume to try again.')
        with self.lock:
            # The stop and enqueue share this lock. A delayed writer cannot
            # queue after Stop has acknowledged, nor after a limit was lowered.
            if not state['enabled']:
                return False
            if state['max_clips'] and state['completed'] >= state['max_clips']:
                state.update(enabled=False, phase='complete')
                self._save()
                return False
            require_comfyui_enqueue_ready()
            self.record['pending'] = {'image': staged['image'], 'parent_id': parent_id}
            state['phase'] = 'generating'
            self._save()
            out = enqueue_video_clip({**settings, 'continues': parent_id, 'ratio': staged['ratio']},
                                     prompt, mode='i2v', image=staged['image'], end_image=None)
            self.record['pending'].update(clip_id=out['clip_id'], job_id=out['job_id'])
            state['current_clip_id'] = out['clip_id']
            self._save()
            return True
