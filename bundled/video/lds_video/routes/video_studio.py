"""🎬 Video Test Studio API — one clip at a time, from a video LoRA.

The image studio runs a GRID: a dozen cells cost a dozen seconds and the answer
is in the contact sheet. Video does not work that way. A clip is minutes, so the
same shape here would be half an hour of waiting before the first thing anyone
could look at. This lane therefore queues ONE clip per launch and keeps a
history, and "compare" means playing two rows of that history side by side.

Everything else is deliberately the image studio's: the enqueue goes through the
same queue manager, the missing-asset refusal is the same structured 409, and
the completion callback rides the same worker thread. A user should not be able
to tell there are two services behind the app.

No login — single local user (`cfg.LOCAL_USER`), like every other blueprint here.
"""
import sqlalchemy as sa
import logging
import os
import uuid
from contextlib import contextmanager, nullcontext

from flask import Blueprint, current_app, jsonify, request, send_file

from lds_sdk.video_host.config import LOCAL_USER
from lds_sdk.video_host.gpu import gpu_exclusive_vision_window
from lds_sdk.video_host import studio as lts
from lds_sdk import dlss5 as _nr
from lds_video import video_test_studio as vts
from lds_video import video_references as vrefs
from lds_sdk.video_host.http import map_error as _map_error
from lds_sdk.video_host.http import require_comfyui as _require_comfyui
from lds_sdk.video_host.http import require_no_stalled_comfyui as _require_no_stalled_comfyui
from lds_sdk.video_host.http import studio_missing_response as _studio_missing_response

logger = logging.getLogger(__name__)

# ✨ How many start frames ONE vision window will write for in a row.
# Not a performance guard: it is the honest ceiling of a single held window.
# Each frame is model work during which no clip can render, so past this the
# right answer is two batches, not a longer freeze nobody can interrupt.
MAX_WRITE_BATCH = 12

# The window's TTL has to cover the WHOLE batch, not one click: a TTL cut for a
# single ✨ press would expire halfway through twelve frames and let a queued
# clip take the card out from under the writer. Generous per frame on purpose —
# a cold model on a slow machine is the case that must not trip it — and the
# window is released as soon as the loop ends.
_WRITE_TTL_PER_FRAME = 180
_WRITE_TTL_FLOOR = 600


def _write_batch_ttl(count):
    return max(_WRITE_TTL_FLOOR, _WRITE_TTL_PER_FRAME * max(1, int(count)))

bp = Blueprint('video_studio', __name__, url_prefix='/api/video-studio')


def _joined_state(clip):
    """⏭ True (the file is the joint), False (left as the part — every failure
    path writes why in `error`), None (no verdict: still rendering, or the
    join is running right now)."""
    if clip.status != 'done':
        return None
    if clip.filename and str(clip.filename).endswith('_joined.mp4'):
        return True
    if clip.error and 'continuation not joined' in str(clip.error):
        return False
    return None


def _json_or_none(text):
    if not text:
        return None
    try:
        import json
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _clip_dict(clip):
    """One clip row as the panel reads it.

    Every setting that shaped the clip travels with it, because the whole point
    of a history here is answering "what was different about that one" without
    reading a ComfyUI graph.
    """
    return {
        'id': clip.id, 'status': clip.status, 'error': clip.error,
        'filename': clip.filename, 'prompt': clip.prompt, 'mode': clip.mode,
        # The queue job behind a pending clip, so the card can match the
        # progress bar the listing carries to the one clip it belongs to.
        'job_id': clip.job_id,
        # The staged start frame, so ↻ Reuse can hand it back: without it a
        # reused image-to-video clip lands in i2v mode with nothing to animate
        # and Generate stays blocked — every dial restored except the one that
        # decides whether the button works at all.
        'source_image': clip.source_image,
        'references': vrefs.references_of(clip),
        'ref_base': getattr(clip, 'ref_base', None),
        'ref_image_size': getattr(clip, 'ref_image_size', None) or 'match',
        'aspect': getattr(clip, 'aspect', None) or 'auto',
        'end_image': getattr(clip, 'end_image', None),
        # ↗ The clip this one was smoothed from, so the card can say so.
        'vfi_of': getattr(clip, 'vfi_of', None),
        # ⏭ The clip this one continues (joined behind it), and whether the join happened.
        'continues_of': getattr(clip, 'continues_of', None),
        # Three states, not two: joined; left as the part, which every failure
        # path says in `error`; or no verdict yet — the part still rendering,
        # or landed seconds ago with the join under way (the completion is
        # committed before the join runs). The card's "(not joined)" is for
        # the middle one only.
        'joined': _joined_state(clip),
        # ✨ The clip this one was neural-rendered from, same reading.
        'nr_of': getattr(clip, 'nr_of', None),
        # ✨ The dials that made a neural render, or null — the pills read them.
        'nr_params': _json_or_none(getattr(clip, 'nr_params', None)),
        'seed': clip.seed, 'steps': clip.steps, 'frames': clip.frames,
        'megapixels': clip.megapixels, 'fps': clip.fps,
        'base_model': clip.base_model, 'lora': clip.lora,
        'lora_strength': clip.lora_strength, 'turbo': bool(clip.turbo),
        # ⚡ Which acceleration ran; rows older than the choice say `turbo` from the flag.
        'accel': (getattr(clip, 'accel', None) or ('turbo' if clip.turbo else '')),
        'sparse': clip.sparse or '', 'latent_upscale': bool(clip.latent_upscale),
        'eros': (clip.base_model == vts.BASE_EROS),
        'light': (clip.base_model == vts.BASE_LIGHT),
        'rating': clip.rating, 'run_id': clip.run_id,
        'dataset_id': clip.dataset_id,
        'generation_settings': _json_or_none(clip.generation_settings),
        'created_at': clip.created_at.isoformat() if clip.created_at else None,
        'seconds': (round((clip.frames - 1) / clip.fps, 2)
                    if clip.frames and clip.fps else None),
        # ⏱ How long the queue spent on it, or null when the queue could not say.
        'render_seconds': clip.render_seconds,
    }


@bp.post('/clip/<int:clip_id>/best')
def video_studio_clip_best(clip_id):
    from lds_video import video_best_settings as best
    try:
        saved = best.save_best(LOCAL_USER, clip_id)
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    return jsonify({'ok': True, 'best_settings': saved})


@bp.get('/best-settings')
def video_studio_best_settings():
    from lds_video import video_best_settings as best
    try:
        ds_id, run_id = best.resolve_lora(LOCAL_USER, request.args.get('lora'),
                                        run_id=request.args.get('run_id'),
                                        dataset_id=request.args.get('dataset_id'))
        ds = best.get_dataset(LOCAL_USER, ds_id) if ds_id else None
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    return jsonify({'dataset_id': ds_id, 'run_id': run_id,
                    'dataset_name': ds.name if ds else None,
                    'best_settings': best.read_best(ds) if ds else None})


@bp.get('/options')
def video_studio_options():
    """Everything the panel would otherwise hard-code.

    Clip lengths, the sparse levels, the megapixel bounds and the step defaults
    all live in the service (and, for lengths and fps, in the shared target
    catalogue behind it). Publishing them keeps the two halves from drifting:
    a front-end that restates `22, 39, 56…` is a front-end that will still offer
    them the day the catalogue changes.

    Also says whether the third-party 10Eros weight is actually on this disk, so
    the checkbox can be offered as unavailable rather than silently ignored.
    """
    profile = vts._profile()
    # ONE probe for the whole payload: which node classes this ComfyUI
    # registers decides both the per-option availability and whether Sage will
    # be in the graph. Asking twice could answer differently in the same reply.
    classes = vts.registered_classes()
    missing = vts.missing_weights()
    # ONE /system_stats read for the reply: the launch advice and the lighter
    # base's version verdict must describe the same server.
    argv, ram_gb, comfy_version = vts.comfyui_launch_facts()
    from lds_video import h3_performance
    return jsonify({
        # What this machine is still missing, and what Setup can do about it.
        # `action` is a setup_installer action name, so the Setup screen turns
        # each row into its own button; None means the app will not fetch that
        # file and `place_in` says where to put it by hand.
        'missing_weights': missing,
        'ready': vts.studio_ready(missing),
        'reference': vts.reference_status(classes, comfy_version),
        'options_available': vts.option_availability(classes),
        'sage': vts.sage_available(classes),
        'performance': h3_performance.status(classes),
        'frame_choices': list(profile.get('frame_choices') or ()),
        # The catalogue's own default is a TRAINING clip length (39 frames,
        # 1.6 s). Publishing it here would open the studio on a clip too short
        # to judge motion in, so the generation default is the studio's own and
        # the training one is published beside it rather than in its place.
        'frame_default': vts.FRAMES_DEFAULT,
        'training_frame_default': profile.get('frame_default'),
        'fps': profile.get('fps'),
        'frames_min': vts.FRAMES_MIN, 'frames_max': vts.FRAMES_MAX,
        'megapixels': {'min': vts.MP_MIN, 'max': vts.MP_MAX,
                       'default': vts.MP_DEFAULT},
        'sparse_modes': list(vts.SPARSE_MODES),
        'turbo_steps': vts.TURBO_STEPS, 'default_steps': vts.DEFAULT_STEPS,
        # ⚡ The arena's three and VDN-H3, each with whether THIS machine has
        # it — and, for VDN-H3, the card's VRAM: on a 24 GB card its hint asks
        # for the lighter base, which is what the launch will insist on.
        'accelerations': vts.accelerations_status(classes, vram_gb=vts.comfyui_vram_gb()),
        'base_official': vts.BASE_OFFICIAL, 'base_eros': vts.BASE_EROS,
        'eros_available': vts.eros_on_disk(),
        # 🪶 The lighter base: file + version verdict, and the sentence for a
        # greyed box, decided here so the panel never guesses which of the two.
        'base_light': vts.BASE_LIGHT,
        'light': vts.light_status(comfy_version),
        # ✨ DLSS 5 neural rendering — ready + the sentences naming what is
        # missing, so the clip history's button can refuse in words.
        'neural_render': _nr.status(),
        # How the running ComfyUI was started, judged against this machine's
        # RAM: None, or the flag that turns minutes per clip into seconds.
        'launch_advice': vts.launch_advice(argv, ram_gb, comfy_version),
    })


@bp.get('/loras')
def video_studio_loras():
    """What can be tested: LoRAs already visible to ComfyUI, and trained runs.

    Two lists rather than one, because they are two different actions. A
    deployed LoRA is one click from a clip; a trained checkpoint has to be
    copied into ComfyUI first, and pretending otherwise would hide a 300 MB
    file operation behind a Generate button.
    """
    return jsonify({'deployed': vts.deployed_loras(),
                    'trained': vts.trained_loras()})


@bp.post('/deploy')
def video_studio_deploy():
    """Copy one trained checkpoint where ComfyUI can load it."""
    data = request.get_json(silent=True) or {}
    try:
        name = vts.deploy_checkpoint(data.get('run_id'), data.get('filename'))
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    except OSError as exc:
        logger.exception('video studio: deploy failed')
        return jsonify({'ok': False,
                        'error': f'Could not copy the checkpoint into ComfyUI: {exc}'}), 500
    return jsonify({'ok': True, 'filename': name})


@bp.post('/clip/<int:clip_id>/vfi')
def video_studio_clip_vfi(clip_id):
    """↗ Smooth a finished clip — RIFE frame interpolation, as a new clip.

    The same recipe the maintainer's image generator uses (rife49, x2, ensemble)
    so a clip smoothed here is the clip smoothed there. A new row, never an edit
    of the original: the studio exists to compare, and overwriting the thing
    being compared would end that.
    """
    data = request.get_json(silent=True) or {}
    try:
        out = vts.interpolate_clip(LOCAL_USER, clip_id,
                                   multiplier=data.get('multiplier'))
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    return jsonify({'ok': True, **out})


@bp.get('/clip/<int:clip_id>/last-frame.png')
def video_studio_clip_last_frame_png(clip_id):
    """⏭ The clip's last frame, as the strip's preview."""
    try:
        path = vts.last_frame_png(clip_id)
    except LookupError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 404
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    resp = send_file(path, mimetype='image/png', conditional=True, max_age=0)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.post('/clip/<int:clip_id>/last-frame')
def video_studio_clip_last_frame(clip_id):
    """⏭ Stage the clip's last frame as the next start frame — the same staging
    as the Bank, Gallery and upload routes, so the graph loads it the same way.
    The reply names the clip so the launch can say it continues it."""
    try:
        out = stage_clip_last_frame(clip_id)
    except LookupError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 404
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    except Exception as exc:                      # noqa: BLE001
        logger.exception('video studio: staging the last frame of clip %s failed', clip_id)
        return jsonify({'ok': False, 'error': str(exc)}), 409
    return jsonify({'ok': True, **out})


def stage_clip_last_frame(clip_id):
    """The same staged frame for manual and automatic continuation."""
    from lds_sdk.video_host import comfy_fs
    from lds_sdk.video_host import config as cfg
    png = vts.last_frame_png(clip_id)
    input_dir = comfy_fs.ensure_input_usable(cfg.comfyui_dir('input'))
    dest = f'lds_vstudio_{uuid.uuid4().hex[:10]}.png'
    staged = comfy_fs.stage_input_image(png, dest, input_dir)
    return {'image': dest, 'ratio': _image_ratio(staged), 'continues': int(clip_id),
            'preview': f'/api/video-studio/clip/{int(clip_id)}/last-frame.png'}


def _clip_seconds(data: dict):
    """How long the clip the panel is set to will be, for the motion writer.

    The panel sends `seconds` — its own readback of the Length dial. A body
    that carries only `frames` (the launch itself) is converted here with the
    SAME arithmetic the readback uses: the snapped count, N-1 intervals at the
    target's fps. Either way the writer paces the action to the clip that
    will actually render, which is the whole point of passing it. None when
    neither is known: the writer then paces nothing rather than guessing.
    """
    if data.get('seconds') is not None:
        try:
            return float(data.get('seconds'))
        except (TypeError, ValueError):
            return None
    if data.get('frames') is None:
        return None
    fps = float(vts._profile().get('fps') or 24.0)
    return (vts.snap_frames(data.get('frames')) - 1) / fps


_UNSET = object()


def _writer_context(data, *, continues=_UNSET):
    """⏭🎞 What the ✨ writers are handed beyond the frame and the text: the
    previous parts when the frame continues a clip, and the staged last frame
    when one is picked. Keyword arguments ONLY when present, so a writer
    called without them is called exactly as before. `continues` given by the
    caller (the batch, per picture) wins over the body's — None included: a
    picture that continues nothing must not fall back to the strip's list.
    A text-only launch continues nothing either (no first frame to carry on
    from), as the panel's own rule says — and ONLY text-only: a reference
    launch that carries `continues` has a first frame by construction since
    2026-09-07 (enqueue_clip refuses one without it), so it is the next part
    of a take and the writer has to be told. Excluding it, as this line did
    from 2026-09-04, cost the continuity rule — same people, same wardrobe,
    same light, never reintroduced as new — and let the camera instruction
    back in AT THE SEAM."""
    extra = {}
    if str(data.get('mode') or '').lower() == 'ref2va' or data.get('refmods') is True:
        extra['mode'] = 'ref2va'
        extra['references'] = vrefs.validate_references(data.get('references'), user_id=LOCAL_USER,
                                                       enforce_limits=data.get('refmods') is not True)
    cont = data.get('continues') if continues is _UNSET else continues
    if str(data.get('mode') or '').lower() == 't2v':
        cont = None
    if cont not in (None, '', False):          # a list, or any non-id, is rejected by previous_parts itself
        previous = vts.previous_parts(cont)
        if previous:
            extra['previous'] = previous
    end = os.path.basename(str(data.get('end_image') or '')) or None
    if end:
        extra['end_image'] = end
    if data.get('direction'):
        extra['direction'] = str(data['direction'])
    return extra


def _observes_locally(data) -> bool:
    """⚙ A still or a reference read by JoyCaption runs on THIS machine's GPU
    even when the writer is GPT: the window has to open for the observer, not
    only for the writer — the old rule was written when the writer was the
    only local step a ✨ press could take. Since 2026-09-06 that is every
    press with a frame (the start frame, a last frame) or a reference to
    read, not only one with a reference video."""
    from lds_video.video_reference_prompt import uses_local_observer
    references = (data.get('references') or []
                  if str(data.get('mode') or '').lower() == 'ref2va' or data.get('refmods') is True else [])
    # A strip (`images`, the per-picture batch) reads every one of its frames.
    image = data.get('image') or next((x for x in (data.get('images') or []) if x), None)
    return uses_local_observer(references, image=image, end_image=data.get('end_image'))


@contextmanager
def _motion_window(model=None, *, flag_ttl=600, local_observer=False):
    from lds_video import video_motion_prompt as vmp
    resolved = vmp._writer_model(model)
    window = (nullcontext() if vmp.uses_chatgpt(resolved) and not local_observer
              else gpu_exclusive_vision_window(flag_ttl=flag_ttl))
    with window:
        # Pin GPT for the entire request, including every frame in a batch.
        # A settings change must not start a local model outside its GPU window.
        yield resolved


def _reference_writer_warnings(data):
    if str(data.get('mode') or '').lower() != 'ref2va':
        return {}
    from lds_video.video_reference_prompt import context_warnings
    return {'warnings': context_warnings(data.get('references') or [])}


@bp.post('/motion/suggest')
def video_studio_motion_suggest():
    """✨ Propose the movement, by looking at the staged start frame.

    A PROPOSAL and the wording says so: the model sees a still, so it can read
    who is there and how they are posed, never what happens next. The user
    edits it like any other text. `seconds` (or `frames`) is the clip length
    the dials are set to — the proposal is paced to fill exactly that.

    Runs inside the GPU-exclusive vision window, like the image studio's
    twin (`/api/studio/describe`): the writer is a vision pass, and a vision
    pass that fights a queued clip for VRAM loses — H3 alone fills most of
    the card. The window refuses while ComfyUI has work queued or rendering
    (503, the reason in `detail`), and on entry asks ComfyUI to let go of its
    models, so the NEXT clip pays H3's load again. That cost is the app's
    standing GPU arbitration, paid once per ✨ click, not a choice of this
    route; the two routes below share it.
    """
    from lds_video import video_motion_prompt as vmp
    data = request.get_json(silent=True) or {}
    try:
        with _motion_window(data.get('model'), flag_ttl=600,
                            local_observer=_observes_locally(data)) as writer_model:
            out = vmp.suggest_from_frame(
                data.get('image'),
                instruction=data.get('instruction'),
                model=writer_model,
                seconds=_clip_seconds(data),
                shots=data.get('shots', 1),
                **_writer_context(data))
    except Exception as exc:
        # Like the image studio's twin: a bad ask is 400, the Ollama/LM Studio
        # fence 409 with its code (the panel offers the unload), the window's
        # refusal 503 with its reason, any other transport failure a 409
        # sentence. The narrow clause this replaced let the fence through as
        # a bare 500 with no message to show.
        return _map_error(exc)
    return jsonify({'ok': True, 'prompt': out, **_reference_writer_warnings(data)})


@bp.post('/motion/write-batch')
def video_studio_motion_write_batch():
    """✨ One prompt PER start frame, written inside a SINGLE vision window.

    WHY THE LOOP IS HERE AND NOT IN THE PANEL. Entering the vision window asks
    ComfyUI to let go of its models, so the next clip pays the video model's
    load again — tens of gigabytes for H3 (the cost is stated in
    `/motion/suggest`). A panel that called the single-frame writers once per
    picture would pay that reload once per picture. Holding one window for the
    whole strip pays it once, which is the entire point of writing every prompt
    BEFORE the first clip is queued.

    Body `{images: [...], prompt?, model?, seconds?|frames?, shots?}` — the same
    pieces the two ✨ buttons send. A `prompt` present means ENRICH each frame
    from it (what `/motion/enhance` does for one); absent means PROPOSE from the
    frame alone (`/motion/suggest`). The panel's own rule, applied N times.

    PARTIAL RESULTS ARE THE CONTRACT. Every entry answers `{index, image,
    prompt}` or `{index, image, error}`, and the call is 200 as long as the
    window opened: one unreadable frame must not cost the eleven others their
    prompt. Only a failure to OPEN the window is an error status — there is
    nothing partial to keep then.
    """
    from lds_video import video_motion_prompt as vmp
    data = request.get_json(silent=True) or {}
    images = [str(n) for n in (data.get('images') or []) if str(n or '').strip()]
    if str(data.get('mode') or '').lower() == 'ref2va':
        return jsonify({'ok': False, 'error': 'References are written together; use Auto or Enrich once.'}), 400
    if not images:
        return jsonify({'ok': False, 'error': 'No start frame to write for.'}), 400
    if len(images) > MAX_WRITE_BATCH:
        return jsonify({'ok': False,
                        'error': (f'{len(images)} pictures at once is more than one '
                                  f'window writes for (max {MAX_WRITE_BATCH}).')}), 400
    typed = str(data.get('prompt') or '').strip()
    # `instruction` is the Motion field as a STEER for ✨ Auto — the frame says
    # what is there, this says what should happen in it. Distinct from `prompt`
    # (enrich THIS text): the panel sends whichever gesture it means. The first
    # port of this route passed instruction='' on the propose branch, so the
    # per-picture batch silently ignored what the user had typed — the exact
    # sentence ✨ Auto honours on a single frame.
    instruction = str(data.get('instruction') or '').strip()
    seconds = _clip_seconds(data)
    shots = data.get('shots', 1)
    model = data.get('model')
    # ⏭ One entry per picture (a frame staged by ⏭ Continue carries the clip
    # it continues; the others carry nothing), or one value for the strip.
    cont = data.get('continues')
    continues = cont if isinstance(cont, list) else [cont] * len(images)
    out = []
    try:
        # ONE window for the whole strip — the reason this route exists — and
        # it opens for a local observer with a GPT writer too (review,
        # 2026-09-06: the strip's frames are read on this card).
        with _motion_window(model, flag_ttl=_write_batch_ttl(len(images)),
                            local_observer=_observes_locally(data)) as writer_model:
            # JoyCaption as the observer: every frame of the strip and the last
            # frame described in ONE worker, before the writers; a refusal ends
            # the batch with its sentence, as the window's own refusals do.
            end = os.path.basename(str(data.get('end_image') or '')) or None
            vmp.prime_stills(list(images) + ([end] if end else []), model=writer_model)
            for i, name in enumerate(images):
                try:
                    extra = _writer_context(data, continues=(continues[i] if i < len(continues) else None))
                    if typed:
                        written = vmp.enhance(typed, image=name, model=writer_model,
                                              seconds=seconds, shots=shots, **extra)
                    else:
                        written = vmp.suggest_from_frame(name, instruction=instruction,
                                                         model=writer_model, seconds=seconds,
                                                         shots=shots, **extra)
                    out.append({'index': i, 'image': name, 'prompt': written})
                except Exception as exc:          # noqa: BLE001
                    logger.warning('video studio: batch write failed on %s: %s', name, exc)
                    out.append({'index': i, 'image': name,
                                'error': str(exc) or exc.__class__.__name__})
    except Exception as exc:
        # The window itself: fence, refusal, transport. Nothing was written.
        return _map_error(exc)
    return jsonify({'ok': True, 'results': out,
                    'written': sum(1 for r in out if str(r.get('prompt') or '').strip()),
                    'failed': sum(1 for r in out if r.get('error'))})


@bp.post('/motion/enhance')
def video_studio_motion_enhance():
    """✨ The same intent, with more of the detail a sampler can use.

    Never destructive: the field is only written on success, and a model
    that answers nothing usable is a 409 with the sentence to show — never
    an empty prompt handed back as if it had worked.

    `image` — the staged start frame, when the panel has one — anchors the
    rewrite on the picture that will actually be animated, so an instruction
    cannot enrich the prompt with scenery the frame does not contain. Without
    one the clip is text-to-video and the writer is told so: no picture is
    referenced. `seconds` (or `frames`) paces the rewrite to the clip length.
    Same GPU-exclusive vision window as `/motion/suggest` (see there).
    """
    from lds_video import video_motion_prompt as vmp
    data = request.get_json(silent=True) or {}
    original = str(data.get('prompt') or '').strip()
    try:
        with _motion_window(data.get('model'), flag_ttl=600,
                            local_observer=_observes_locally(data)) as writer_model:
            out = vmp.enhance(data.get('prompt'), image=data.get('image'),
                              model=writer_model, seconds=_clip_seconds(data),
                              shots=data.get('shots', 1), **_writer_context(data))
    except Exception as exc:
        return _map_error(exc)
    # `unchanged` is how the panel tells "the model had nothing to add" from
    # "the request worked": the two look identical in the field.
    return jsonify({'ok': True, 'prompt': out,
                    **_reference_writer_warnings(data),
                    'unchanged': str(out or '').strip() == original})


@bp.get('/motion/models')
def video_studio_motion_models():
    """⚙ Which local models can write the motion, and which one does today."""
    from lds_video import video_motion_prompt as vmp
    return jsonify(vmp.model_choices())


def _json_object(data):
    """A PUT body as the dict it must be: an absent body is an empty choice (the
    old `or {}`), an array or a scalar is a 400 sentence — not an AttributeError
    on `.get` turned into a bare 500."""
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return None, (jsonify({'error': 'Send a JSON object.'}), 400)
    return data, None


@bp.get('/motion/dials')
def video_studio_motion_dials():
    """⚙ The writer's sampling dials as they will be used, next to the shipped
    defaults and the bounds — so the window can draw a slider that cannot be
    dragged outside what the provider accepts, and a ↺ that means something."""
    from lds_video import video_motion_prompt as vmp
    return jsonify({'ok': True, 'dials': vmp.configured_dials(),
                    'defaults': vmp.dial_defaults(),
                    'bounds': {k: [lo, hi] for k, (lo, hi, _) in vmp.DIAL_BOUNDS.items()}})


@bp.put('/motion/dials')
def video_studio_motion_dials_set():
    """⚙ Save the dials. Answers what was KEPT after clamping, and the window
    shows that — a 40 typed into temperature comes back as 2.0 on screen rather
    than silently becoming something else at the next launch."""
    from lds_video import video_motion_prompt as vmp
    data, refused = _json_object(request.get_json(silent=True))
    if refused:
        return refused
    return jsonify({'ok': True, 'dials': vmp.set_dials(data.get('dials'))})


@bp.put('/motion/model')
def video_studio_motion_model_set():
    """⚙ Remember the model that writes the motion. Empty returns to the
    provider's own vision model."""
    from lds_video import video_motion_prompt as vmp
    data, refused = _json_object(request.get_json(silent=True))
    if refused:
        return refused
    return jsonify({'ok': True, 'model': vmp.set_model(data.get('model'))})


@bp.get('/motion/reference-observer')
def video_studio_reference_observer():
    """⚙ How reference VIDEOS are read before the writer sees them: the method
    in use, the two on offer, and whether JoyCaption can run on this install."""
    from lds_video import video_reference_prompt as vrp
    return jsonify({'ok': True, **vrp.observer_choices()})


@bp.put('/motion/reference-observer')
def video_studio_reference_observer_set():
    """⚙ Remember the method. Anything but the two names is a 400, never a
    value stored and silently read back as the default."""
    from lds_video import video_reference_prompt as vrp
    data, refused = _json_object(request.get_json(silent=True))
    if refused:
        return refused
    try:
        return jsonify({'ok': True, 'observer': vrp.set_observer(data.get('observer'))})
    except ValueError as exc:
        return _map_error(exc)


@bp.post('/lora/import')
def video_studio_lora_import():
    """Bring a LoRA the user already has into the picker.

    Multipart `file`, or JSON `{path}` for a file on this machine — the second
    is the one that matters for a 300 MB weight, since nothing crosses HTTP.
    The picker listed only what this app trained and what was already in
    ComfyUI's folder, so anything downloaded had to be moved there by hand with
    the app open beside a file explorer.

    400 for every refusal, because all of them are things the user can fix: the
    wrong extension, an unusable name, a file that is not there, or a DIFFERENT
    weight already under that name (never overwritten — that would silently
    change what every clip made with that name meant).
    """
    upload = request.files.get('file')
    data = request.get_json(silent=True) or {}
    try:
        out = vts.import_external_lora(
            src_path=(str(data.get('path')).strip() if data.get('path') else None),
            upload=upload,
            filename=(upload.filename if upload is not None else None))
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    except OSError as exc:
        logger.exception('video studio: lora import failed')
        return jsonify({'ok': False,
                        'error': f'Could not copy that LoRA into ComfyUI: {exc}'}), 500
    return jsonify({'ok': True, **out})


@bp.post('/source')
def video_studio_source():
    """Stage the i2v start image into ComfyUI's input folder.

    Three ways in, because a video LoRA is tested against three different kinds
    of picture and making the user export to disk first would be busywork:

      * an UPLOAD (multipart `image`) — the general case;
      * a BANK image (`bank_id` + `image_id`) — animating the very portrait the
        LoRA was trained from;
      * an image from the app's own GALLERY (`gallery_image_id`) — the picture
        someone just generated, animated without a round trip through disk;
      * the FIRST FRAME of a dataset clip (`dataset_id` + `filename`) — the
        honest baseline, since that frame is material the LoRA actually saw.

    Whatever the route in, the file lands through `stage_input_image`, which
    strips EXIF/GPS and bounds the decode: ComfyUI's input folder may be a
    different machine, so it is a disclosure boundary rather than a copy.

    Returns the staged NAME (what the graph's LoadImage will reference) and the
    aspect ratio, which the latent upscale needs to size its target.
    """
    data = request.get_json(silent=True) or {}
    if 'library_source' in data:
        from lds_video import video_reference_selection as selection
        try:
            return jsonify({'ok': True, **selection.stage_guide(
                LOCAL_USER, data['library_source'], data.get('frame', 'first'))})
        except Exception as exc:
            return _reference_library_error(exc)
    try:
        src_path, cleanup = _resolve_source(request)
    except ValueError as exc:
        return _map_error(exc)
    try:
        from lds_sdk.video_host import comfy_fs
        from lds_sdk.video_host import config as cfg
        input_dir = comfy_fs.ensure_input_usable(cfg.comfyui_dir('input'))
        dest = f'lds_vstudio_{uuid.uuid4().hex[:10]}.png'
        staged = comfy_fs.stage_input_image(src_path, dest, input_dir)
        ratio = _image_ratio(staged)
    except ValueError as exc:
        return _map_error(exc)
    except Exception as exc:                      # noqa: BLE001
        logger.exception('video studio: staging the source image failed')
        return jsonify({'ok': False, 'error': str(exc)}), 409
    finally:
        if cleanup:
            try:
                os.unlink(src_path)
            except OSError:
                pass
    return jsonify({'ok': True, 'image': dest, 'ratio': ratio})


@bp.get('/source')
def video_studio_source_preview():
    """Preview a staged frame guide, including a frame restored by Reuse."""
    name = request.args.get('image')
    if not isinstance(name, str) or not vts.STAGED_FRAME_NAME.fullmatch(name):
        return jsonify({'error': 'not a staged frame name'}), 400
    try:
        if not vts.restage_frame(name):
            raise ValueError('That frame is no longer staged — pick it again.')
        path = vts.staged_frame_path(name)
    except (ValueError, RuntimeError) as exc:
        return _map_error(exc)
    except LookupError as exc:
        return jsonify({'error': str(exc)}), 404
    response = send_file(path, mimetype='image/png', conditional=True, max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/reference')
def video_studio_reference_stage():
    """Stage bounded media from an upload or an existing library picture."""
    data = request.get_json(silent=True) or {}
    form = request.form if request.files else data
    kind = form.get('kind') or 'image'
    upload = request.files.get('file')
    cleanup = False
    source = None
    try:
        if 'library_source' in data:
            from lds_video import video_reference_selection as selection
            ref = selection.stage(LOCAL_USER, kind=kind, descriptor=data['library_source'],
                frame=data.get('frame', 'first'), start_seconds=data.get('start_seconds'),
                duration_seconds=data.get('duration_seconds'), role=data.get('role', ''),
                include_audio=data.get('include_audio', False))
            return jsonify({'ok': True, 'reference': ref})
        if data.get('cut_from'):
            # ✂ A staged video cut to an interval: a new reference from the
            # staged copy, the panel swaps it in place (2026-09-06).
            include_audio = data.get('include_audio', False)
            if not isinstance(include_audio, bool):
                raise ValueError('include_audio must be true or false')
            ref = vrefs.cut_reference(data['cut_from'], data.get('start_seconds'),
                                      data.get('duration_seconds'), user_id=LOCAL_USER,
                                      role=str(data.get('role') or ''), include_audio=include_audio)
            return jsonify({'ok': True, 'reference': ref})
        if upload is None:
            if kind != 'image':
                raise ValueError('Upload a video or audio reference file.')
            if data.get('image'):
                if not vts.restage_frame(data['image']):
                    raise ValueError('That image is no longer staged — pick it again.')
                source = vts.staged_frame_path(data['image'])
            else:
                source, cleanup = _resolve_source(request)
        include_audio = form.get('include_audio', False)
        if isinstance(include_audio, str):
            include_audio = include_audio.lower() == 'true'
        ref = vrefs.stage_reference(kind=kind, upload=upload, source=source,
            role=form.get('role', ''), include_audio=bool(include_audio), user_id=LOCAL_USER)
    except Exception as exc:
        if 'library_source' in data:
            return _reference_library_error(exc)
        return _map_error(exc)
    finally:
        if cleanup and source:
            try:
                os.unlink(source)
            except OSError:
                pass
    return jsonify({'ok': True, 'reference': ref})


def _reference_library_error(exc):
    import subprocess
    if isinstance(exc, LookupError):
        return jsonify({'error': str(exc)}), 404
    if isinstance(exc, (OSError, subprocess.TimeoutExpired)):
        return jsonify({'error': 'This library file could not be read in time. Select it again or use a smaller excerpt.'}), 409
    return _map_error(exc)


@bp.get('/reference-library')
def video_studio_reference_library():
    from lds_video import video_reference_library as library
    try:
        return jsonify(library.list_library(LOCAL_USER, kind=request.args.get('kind', 'image'),
            source=request.args.get('source'), collection_id=request.args.get('collection_id'),
            offset=request.args.get('offset', 0), limit=request.args.get('limit', 40),
            q=request.args.get('q', '')))
    except Exception as exc:
        return _reference_library_error(exc)


@bp.get('/reference-library/info')
def video_studio_reference_library_info():
    from lds_video import video_reference_selection as selection
    try:
        return jsonify(selection.info(LOCAL_USER, request.args.to_dict()))
    except Exception as exc:
        return _reference_library_error(exc)


@bp.get('/reference-library/preview')
def video_studio_reference_library_preview():
    from lds_video import video_reference_selection as selection
    try:
        path = selection.preview(LOCAL_USER, request.args.to_dict())
        return send_file(path, mimetype='image/jpeg', conditional=True, max_age=60)
    except Exception as exc:
        return _reference_library_error(exc)


@bp.get('/reference')
def video_studio_reference_media():
    try:
        name = request.args.get('name')
        path = vrefs.path_for(name, user_id=LOCAL_USER)
    except (ValueError, OSError, RuntimeError) as exc:
        return _map_error(exc)
    mime = {'.png': 'image/png', '.mp4': 'video/mp4', '.wav': 'audio/wav'}[path.suffix]
    response = send_file(path, mimetype=mime, conditional=True, max_age=0)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/frame/adopt')
def video_studio_frame_adopt():
    """🔍 A start frame as a library row — what the shared viewer needs.

    Body `{dataset_id?, image?: staged name | gallery_image_id?: int}`. No
    `dataset_id` = the holding dataset of the video lane. Answers `{ok, image}`
    where `image` is the Gallery's own serializer output, so the viewer opened
    on it reads exactly what it reads on the Gallery page
    (services/video_test_studio.adopt_frame says why a row, and why one)."""
    data = request.get_json(silent=True) or {}
    try:
        row = vts.adopt_frame(data.get('dataset_id'), image=data.get('image'),
                              gallery_image_id=data.get('gallery_image_id'),
                              user_id=LOCAL_USER)
    except LookupError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 404
    except ValueError as exc:
        return _map_error(exc)
    from lds_sdk.run_history import gallery_image
    return jsonify({'ok': True, 'image': gallery_image(row)})

def _resolve_source(req):
    """(path to read the picture from, whether the caller must delete it).

    Kept apart from the route so each source is one readable branch, and so the
    temp-file lifetime is explicit: only the upload branch creates one.
    """
    upload = req.files.get('image')
    if upload is not None:
        import tempfile
        fd, tmp = tempfile.mkstemp(suffix='.upload')
        with os.fdopen(fd, 'wb') as fh:
            fh.write(upload.read())
        return tmp, True

    data = req.get_json(silent=True) or {}
    if data.get('bank_id') and data.get('image_id'):
        # `resolved_image_path` and nothing else: it is THE reader-side resolver
        # (watermark-cleaned blob, manual rotation, bank-side crop), and a reader
        # calling `abs_image_path` directly would quietly animate the version the
        # user already cleaned.
        from lds_sdk.video_media_library import image_path
        try:
            path = image_path(LOCAL_USER, 'bank', int(data['image_id']), collection_id=int(data['bank_id']))
        except LookupError as exc:
            raise ValueError('that bank image is not on disk') from exc
        if not path or not os.path.isfile(path):
            raise ValueError('that bank image is not on disk')
        return str(path), False

    if data.get('dataset_id') and data.get('filename'):
        return _dataset_clip_frame(int(data['dataset_id']), data['filename']), True

    if data.get('gallery_image_id'):
        # An image the app itself generated — the Gallery feed's own row id.
        # Served at full size from the dataset folder it lives in, exactly as
        # /api/dataset/<id>/img/<name> serves it, so what gets animated is the
        # picture the user is looking at rather than a thumbnail of it.
        from lds_sdk.video_media_library import LibraryFileUnavailable, image_path
        try:
            path = image_path(LOCAL_USER, 'gallery', int(data['gallery_image_id']))
        except LibraryFileUnavailable as exc:
            raise ValueError('that generated image is no longer on disk') from exc
        except LookupError as exc:
            raise ValueError('that generated image is not in the gallery any more') from exc
        if not os.path.isfile(path):
            raise ValueError('that generated image is no longer on disk')
        return str(path), False

    raise ValueError('attach an image, or name a bank image, a dataset clip or '
                     'a gallery image')


def _dataset_clip_frame(dataset_id, filename):
    """Decode the FIRST frame of a dataset clip to a temp PNG, full size.

    Not the bank's thumbnail: that one is capped at 480 px for a gallery, and
    feeding a 480 px still to a 1 MP generation would blame the LoRA for a
    softness the source never had.
    """
    from lds_video import video_bank_service as vbs
    name = os.path.basename(str(filename or ''))
    if not name:
        raise ValueError('clip not found')
    path = os.path.join(str(vbs.dataset_dir(dataset_id)), name)
    if not os.path.isfile(path):
        raise ValueError('clip not found')
    try:
        import av
        import tempfile
    except ImportError:
        raise ValueError('reading a frame needs the video extras — install them '
                         'from the Setup screen')
    fd, tmp = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        with av.open(path) as container:
            stream = container.streams.video[0]
            for frame in container.decode(stream):
                frame.to_image().convert('RGB').save(tmp, 'PNG')
                return tmp
    except Exception as exc:                      # noqa: BLE001 — any decode error
        raise ValueError(f'could not read a frame from that clip: {exc}')
    raise ValueError('that clip has no decodable frame')


def _staged_image_ratio(name):
    """width / height of an ALREADY staged start frame, by its staged name.

    The ratio travels with the pick; a caller replaying a past clip has only
    the name. Reading it back costs one PIL open of a file this app wrote
    itself, and returns None on anything unreadable — the same fine answer
    _image_ratio gives, with the same single consumer.
    """
    safe = os.path.basename(str(name or ''))
    if not safe:
        return None
    try:
        from lds_sdk.video_host import config as cfg
        folder = cfg.comfyui_dir('input')
    except Exception:  # noqa: BLE001 — no input folder is "no ratio", not a 500
        return None
    if not folder:
        return None
    return _image_ratio(os.path.join(str(folder), safe))


def _image_ratio(path):
    """width / height of the staged picture, or None when it cannot be read.

    None is a fine answer: the only consumer is the latent upscale's target
    size, which falls back to the node's own defaults.
    """
    try:
        from PIL import Image
        with Image.open(path) as im:
            return round(im.width / max(1, im.height), 4)
    except Exception:                             # noqa: BLE001
        return None


@bp.post('/generate')
def video_studio_generate():
    """Queue one clip.

    Gated like the image studio's `/run`: ComfyUI has to be reachable and must
    not be sitting on a stalled prompt, because a job queued behind a wedged one
    looks exactly like a job that is simply slow — and here "simply slow" is a
    plausible five minutes.

    The answer names the `prompt` that ran (the rewrite when ✨ Enrich at
    launch worked, the text as typed when it did not) next to the `seed` the
    graph got: a batch of start frames launches its first clip, then sends
    the rest with THAT prompt and THAT seed, since the vision window is shut
    to it as soon as this clip sits in ComfyUI's queue.
    """
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'error': 'Expected video settings.'}), 400
    if 'cloud_session_id' in data:
        return jsonify({'error': 'Open Creature Battle to render with its cloud GPU session.'}), 400
    blocked = _require_comfyui() or _require_no_stalled_comfyui()
    if blocked:
        return blocked
    prompt = str(data.get('prompt') or '').strip()
    try:
        mode = vts.normalise_mode(data.get('mode'))
        from lds_video.h3_refmods import validate as validate_refmods
        validate_refmods(mode, data.get('image'), data.get('references'), data.get('refmods', False))
        references = (vrefs.validate_references(data.get('references'), user_id=LOCAL_USER,
                                               enforce_limits=not data.get('refmods', False))
                      if mode == 'ref2va' or data.get('refmods') else [])
    except (ValueError, RuntimeError) as exc:
        return _map_error(exc)
    image = data.get('image')
    # 🎞 The last frame: a staged name, reduced to its basename like the
    # LoadImage it feeds expects (ComfyUI resolves it under its input dir).
    end_image = os.path.basename(str(data.get('end_image') or '')) or None
    # A staged frame the boot sweep has cleared (↻ Reuse of a clip older than
    # 48 h) comes back from the clip's own copy — or the launch is refused
    # with a sentence now, not by ComfyUI's 400 a minute later.
    for role, name in (('start', image if mode in ('i2v', 'ref2va') else None), ('last', end_image)):
        try:
            present = not name or vts.restage_frame(name)
            if name and mode == 'ref2va':
                if str(name) != os.path.basename(str(name)):
                    raise ValueError('A guide frame must be a staged image name.')
                vts.staged_frame_path(name, role=role)
        except (ValueError, RuntimeError) as exc:           # ComfyFolderUnavailable: the folder itself
            return _map_error(exc)
        except LookupError:
            present = False
        if not present:
            return jsonify({'ok': False,
                            'error': f'that {role} frame is no longer staged — pick it again'}), 409
    # ✨ Enrich at launch. Done HERE, before the graph is built, so the clip row
    # records the prompt that actually ran — a card naming a prompt the sampler
    # never read would be the one lie this screen cannot afford. A failed
    # enrichment keeps the original rather than refusing the launch: the user
    # asked for a clip, not for an essay. The writer gets what the ✨ Enrich
    # button gets: the start frame (only when one will be animated) and the
    # clip length, so the launch and the button write the same prompt.
    from lds_video import video_motion_prompt as vmp
    enrich_skipped = None
    if data.get('enhance') and prompt:
        try:
            # The same GPU-exclusive vision window as the ✨ buttons (see
            # `/motion/suggest`): a clip already queued or rendering refuses
            # it, and that refusal is one more reason to launch un-enriched.
            with _motion_window(flag_ttl=600, local_observer=_observes_locally(data)) as writer_model:
                prompt = vmp.enhance(prompt, image=(image if mode in ('i2v', 'ref2va') else None),
                                     model=writer_model,
                                     seconds=_clip_seconds(data),
                                     shots=data.get('shots', 1),
                                     **_writer_context(data))
        except Exception as exc:
            # Every failure, the fence and the window included: the clip still
            # launches, and the answer carries the reason so the panel can say it.
            enrich_skipped = str(exc) or exc.__class__.__name__
            logger.warning('video studio: launch enrichment skipped: %s', exc)
    if mode == 'i2v' and not image:
        return jsonify({'ok': False,
                        'error': 'Pick a start image, or switch to text-to-video.'}), 400
    if not prompt:
        return jsonify({'ok': False,
                        'error': 'Describe the motion you want to see.'}), 400
    # The official I2V header, in code, at generation — the reference writer's
    # own rule: a prompt typed by hand or pasted from elsewhere gets the line
    # that tells the encoder the picture IS the first frame, and one the ✨
    # writers wrote, or a clip reused, is never headed twice. Text-to-video is
    # the mirror: a prompt written for a start frame and then launched without
    # one names a picture the encoder is not given — the header, the identity
    # sentence and the tag go. Done before the row is written, so the card
    # shows the prompt that ran.
    if mode == 'ref2va':
        from lds_video.video_reference_prompt import validate_prompt_references
        try:
            prompt = validate_prompt_references(prompt, references)
        except ValueError as exc:
            return _map_error(exc)
    elif data.get('refmods') is True:
        from lds_video.h3_refmods import first_frame_prompt
        prompt = first_frame_prompt(prompt, has_first_frame=mode == 'i2v' and bool(image))
    else:
        prompt = (vmp.inject_alignment_header(prompt) if mode == 'i2v'
                  else vmp.strip_picture_references(prompt))
    if not vmp.has_motion(prompt):
        # Judged AFTER the rewrite, on the description alone: a prompt that
        # was nothing but the header, or labels around nothing — a clip's
        # prompt pasted back with its motion deleted — passed the check above
        # and reached the sampler empty.
        return jsonify({'ok': False,
                        'error': 'The prompt carries no motion once its header and '
                                 'labels are set aside — describe what you want to '
                                 'see move.'}), 400
    try:
        out = enqueue_video_clip(data, prompt, mode=mode, image=image, end_image=end_image,
                                 references=references)
    except lts.StudioAssetsMissing as exc:
        return _studio_missing_response(exc)
    except (ValueError, TypeError) as exc:
        return _map_error(exc)
    if enrich_skipped:
        out = {**out, 'enrich_skipped': enrich_skipped}
    return jsonify({'ok': True, 'prompt': prompt,
                    **(_reference_writer_warnings(data) if data.get('enhance') else {}), **out})


def enqueue_video_clip(data, prompt, *, mode, image, end_image=None, references=None):
    """Shared queue seam: Auto uses the same name fence, graph and preflight."""
    if 'cloud_session_id' in data:
        raise ValueError('Open Creature Battle to render with its cloud GPU session.')
    # ⏭ A reference continuation renders at the shape of the picture it starts
    # on, and the panel says so in words — the shape control reads "From clip
    # #N" and is locked. If that picture cannot be measured, falling back to
    # the dial would render one thing while the screen promises another; the
    # launch says so instead (raised in verification, 2026-09-07).
    if mode == 'ref2va' and data.get('continues') and image and _staged_image_ratio(image) is None:
        raise ValueError('The shape of the frame this continues could not be read. '
                         'Stage its last frame again, or drop the continuation.')
    lora = data.get('lora') or None
    if lora and lts.is_unsafe_external_lora_name(lora):
        raise ValueError('invalid LoRA name')
    return vts.enqueue_clip(
        LOCAL_USER, prompt=prompt, mode=mode, image=image, end_image=end_image,
        lora=lora, lora_strength=data.get('lora_strength', 1.0),
        run_id=data.get('run_id'), dataset_id=data.get('dataset_id'),
        seed=data.get('seed'), steps=data.get('steps'), frames=data.get('frames'),
        megapixels=data.get('megapixels', vts.MP_DEFAULT),
        aspect=data.get('aspect', 'auto'), turbo=bool(data.get('turbo')),
        accel=data.get('accel'), continues=data.get('continues'),
        eros=bool(data.get('eros')), light=bool(data.get('light')),
        sparse=data.get('sparse', ''), latent_upscale=bool(data.get('latent_upscale')),
        references=references if references is not None else data.get('references'),
        ref_base=data.get('ref_base', 'official'), ref_image_size=data.get('ref_image_size', 'match'),
        refmods=data.get('refmods', False),
        fused=data.get('fused', False), h3_attention=data.get('h3_attention', 'auto'),
        h3_spectrum=data.get('h3_spectrum', False), h3_video_vae=data.get('h3_video_vae', 'fp16'),
        h3_video_writer=data.get('h3_video_writer', 'native'),
        # ⏭ …and for a reference CONTINUATION, whose canvas must be its
        # parent's: the seam picture is that parent's last frame, so its own
        # shape is the measurement. Read here, where the staged file is, and
        # only for a continuation — a plain reference launch keeps taking its
        # shape from the dial, guide or no guide.
        # In reference mode the ratio is MEASURED, never taken from the body:
        # the shipped panel sends none there, and a hand-built one would
        # otherwise steer a canvas the rule above says belongs to the parent
        # (raised in verification, 2026-09-07). i2v keeps trusting the strip's,
        # which is the shape of the picture it just staged.
        source_ratio=(_staged_image_ratio(image) if (data.get('continues') and image) else None)
        if mode == 'ref2va'
        else (data.get('ratio') or (_staged_image_ratio(image) if mode == 'i2v' else None)))


@bp.route('/auto-continue', methods=['GET', 'POST', 'PATCH'])
def video_studio_auto_continue():
    from lds_video import video_auto_continue as auto
    try:
        runner = auto.manager(current_app._get_current_object())
        data = request.get_json(silent=True) or {}
        if request.method == 'POST':
            state = runner.start(data)
        elif request.method == 'PATCH':
            state = runner.update(data)
        else:
            state = runner.status()
        return jsonify({'ok': True, 'session': state})
    except (ValueError, RuntimeError) as exc:
        return _map_error(exc)


@bp.post('/auto-continue/<action>')
def video_studio_auto_continue_action(action):
    from lds_video import video_auto_continue as auto
    if action not in ('stop', 'resume'):
        return jsonify({'error': 'Unknown continuation action.'}), 404
    try:
        runner = auto.manager(current_app._get_current_object())
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            raise ValueError('Expected an Auto session identity.')
        state = getattr(runner, action)(data.get('session_id'))
        return jsonify({'ok': True, 'session': state})
    except (ValueError, RuntimeError) as exc:
        return _map_error(exc)


@bp.get('/clips')
def video_studio_clips():
    """The history, newest first. `limit` caps a page (default 24, hard max
    200); `before=<id>` pages further back.

    THE SOURCE OF A RENDER RIDES ALONG. A smoothed or neural-rendered clip
    points at the clip it was made from (`vfi_of`, `nr_of`), and that clip is
    older by construction — after a few renders it falls off the newest page,
    and the pair the studio exists to compare reads as "the original was
    deleted" (reported on the first evening). So every source of a listed
    render is appended to the page it belongs with, whatever its age, and the
    list stays newest first. `has_more` says whether a further page exists —
    judged on the page proper, not on the sources it carried along.
    """
    from lds_video.models import VideoTestClip
    try:
        limit = max(1, min(200, int(request.args.get('limit', 24))))
    except (TypeError, ValueError):
        limit = 24
    query = _owned_clips().order_by(VideoTestClip.id.desc())
    try:
        before = int(request.args.get('before', 0))
    except (TypeError, ValueError):
        before = 0
    if before > 0:
        query = query.filter(VideoTestClip.id < before)
    page = query.limit(limit).all()
    listed = {c.id for c in page}
    wanted = ({getattr(c, 'nr_of', None) for c in page} | {getattr(c, 'vfi_of', None) for c in page}
              | {getattr(c, 'continues_of', None) for c in page})
    wanted = {i for i in wanted if i and i not in listed}
    sources = (_owned_clips().filter(VideoTestClip.id.in_(wanted)).all()
               if wanted else [])
    rows = sorted(page + sources, key=lambda c: c.id, reverse=True)
    # Where the clip on the card actually is — ComfyUI's own progress bar, read
    # from its console — so the "Rendering…" tile can say "step 3/4, about an
    # hour left" instead of spinning the same way for a minute and for a night.
    # Only paid for while a clip is pending; the read is cached and shared.
    render = None
    if any(c.status == 'pending' for c in rows):
        from lds_sdk import comfy
        render = comfy.render_progress()
    # `oldest_id` is the boundary of the page PROPER. The panel keeps what it
    # loaded below that boundary and pages further back from it; a source
    # that rode along is older than the page by construction and must not
    # move the boundary — it did, and every clip loaded between the two
    # vanished at the next poll (read as "Smooth deleted my clips").
    return jsonify({'clips': [_clip_dict(c) for c in rows],
                    'has_more': len(page) == limit, 'page_size': limit,
                    'oldest_id': page[-1].id if page else 0,
                    'render': render})


@bp.get('/clip/<int:clip_id>')
def video_studio_clip(clip_id):
    """One clip — what the panel polls while a job is in flight."""
    clip = _owned_clips().filter_by(id=clip_id).first()
    if clip is None:
        return jsonify({'error': 'clip not found'}), 404
    return jsonify(_clip_dict(clip))


@bp.get('/clip/<int:clip_id>/video')
def video_studio_clip_media(clip_id):
    """The mp4 itself.

    `conditional=True` for the same reason as the bank's rushes: without a
    206-capable response the player downloads the whole clip before it can seek
    a single second of it.
    """
    clip = _owned_clips().filter_by(id=clip_id).first()
    if clip is None or not clip.filename:
        return jsonify({'error': 'clip not available'}), 404
    from lds_video.video_result_recovery import recover
    recover(clip)
    path = os.path.join(str(vts.clips_dir()), os.path.basename(clip.filename))
    if not os.path.isfile(path):
        return jsonify({'error': 'clip file not found'}), 404
    return send_file(path, mimetype='video/mp4', conditional=True, max_age=0)


@bp.post('/clip/<int:clip_id>/rate')
def video_studio_rate(clip_id):
    """👍 / 👎 / clear — the image studio's scale, so one habit covers both."""
    from lds_video.models import db
    clip = _owned_clips().filter_by(id=clip_id).first()
    if clip is None:
        return jsonify({'error': 'clip not found'}), 404
    data = request.get_json(silent=True) or {}
    try:
        rating = int(data.get('rating', 0))
    except (TypeError, ValueError):
        rating = 0
    clip.rating = 1 if rating > 0 else (-1 if rating < 0 else 0)
    db.session.commit()
    return jsonify({'ok': True, 'rating': clip.rating})


@bp.delete('/clip/<int:clip_id>')
def video_studio_delete(clip_id):
    """Drop a clip and its file.

    The row goes even when the file cannot: a history entry pointing at nothing
    is worse than a stray mp4, and the file was in the app's own folder.
    """
    from lds_video.models import db
    clip = _owned_clips().filter_by(id=clip_id).first()
    if clip is None:
        return jsonify({'error': 'clip not found'}), 404
    if clip.status == 'pending' and '"execution": "battle_cloud"' in (clip.generation_settings or ''):
        return jsonify({'error': 'Stop the battle GPU before deleting its unfinished clip.'}), 409
    if clip.filename:
        try:
            os.unlink(os.path.join(str(vts.clips_dir()),
                                   os.path.basename(clip.filename)))
        except OSError:
            pass
    # ⏭ The last-frame cache the clip may have grown, and 🎬 the copies of the
    # frames it started from / ended on: derived from or staged for this
    # clip, written by the app, and SQLite reuses a deleted id — a stale
    # sidecar under the next clip's id is one mtime check away from being
    # served, or restaged as the next clip's picture.
    for which in ('last', 'first', 'end'):
        try:
            os.unlink(os.path.join(str(vts.clips_dir()), f'clip_{int(clip_id)}_{which}.png'))
        except OSError:
            pass
    vrefs.delete_clip_references(clip)
    db.session.delete(clip)
    db.session.commit()
    return jsonify({'ok': True})


def _owned_clips():
    from lds_video.models import VideoTestClip
    return VideoTestClip.query.filter(sa.or_(VideoTestClip.user_id == str(LOCAL_USER),
                                              VideoTestClip.user_id.is_(None)))
