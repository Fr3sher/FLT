"""The Video Test Studio — playing a trained video LoRA back as a clip.

The video lane could train a LoRA and hand back a `.safetensors`, and that was
where it stopped. Judging the result meant leaving the app: copy the file into
ComfyUI by hand, open a graph someone else wrote, guess which knobs the training
recipe implied. This module closes that loop the way the image Test Studio
already does for image LoRAs — same idea, different medium.

WHAT THIS IS A PORT OF, AND WHY THAT MATTERS
--------------------------------------------
Nothing here was invented. The MiniMax H3 image-to-video graph, the turbo
distillation LoRA, the third-party 10Eros base, the sparse-attention grafts and
the latent upscale all come from a video pipeline that has been generating real
clips for months, and every constant below was measured there — several of them
the hard way, on runs that had to be interrupted. The comments carry those
measurements because a value without its measurement is a value the next person
will "clean up".

THE ONE DESIGN DECISION WORTH STATING: GRAFTS, NOT WORKFLOW VARIANTS
--------------------------------------------------------------------
`workflows/minimax_h3_i2v.json` holds eighteen nodes and no options. Turbo,
LoRA, sparse attention and upscale are grafted onto that graph at build time
(ids 600-810), never shipped as separate JSON files. Four options that combine
freely would otherwise be sixteen workflow files, fifteen of which nobody would
ever open again, and a bug fixed in one would live on in the other fifteen.

The build is a PURE function. It takes what it needs — including whether the
10Eros weight is on disk — and returns a graph. No Flask, no filesystem, no
database: the whole option matrix is testable without a GPU, which is the only
reason the pitfalls below can be pinned by tests at all.
"""

from lds_sdk.h3_render import (  # noqa: F401 - public compatibility aliases
    sage_available as sage_available,
    ACCELERATIONS as ACCELERATIONS,
    ACCEL_IDS as ACCEL_IDS,
    BASE_EROS as BASE_EROS,
    BASE_OFFICIAL as BASE_OFFICIAL,
    DARETIES_LORA as DARETIES_LORA,
    DEFAULT_STEPS as DEFAULT_STEPS,
    FAST_DISK_MIN_COMFYUI as FAST_DISK_MIN_COMFYUI,
    FAST_DISK_RAM_FLOOR_GB as FAST_DISK_RAM_FLOOR_GB,
    FRAMES_DEFAULT as FRAMES_DEFAULT,
    H3_HOST_RAM_GB as H3_HOST_RAM_GB,
    LORA_EXT as LORA_EXT,
    LORA_SUBDIR as LORA_SUBDIR,
    N_ACCEL_LORA as N_ACCEL_LORA,
    N_COND as N_COND,
    N_CREATE_VIDEO as N_CREATE_VIDEO,
    N_DECODE_AUDIO as N_DECODE_AUDIO,
    N_DECODE_VIDEO as N_DECODE_VIDEO,
    N_GUIDER as N_GUIDER,
    N_LOAD_IMAGE as N_LOAD_IMAGE,
    N_NOISE as N_NOISE,
    N_SAGE as N_SAGE,
    N_SAMPLER as N_SAMPLER,
    N_SAMPLER_SELECT as N_SAMPLER_SELECT,
    N_SAVE as N_SAVE,
    N_SCALE as N_SCALE,
    N_SCHEDULER as N_SCHEDULER,
    N_SHIFT as N_SHIFT,
    N_SIZE as N_SIZE,
    N_SPARSE as N_SPARSE,
    N_TEST_LORA as N_TEST_LORA,
    N_TURBO_LORA as N_TURBO_LORA,
    N_TURBO_SAMPLER as N_TURBO_SAMPLER,
    N_UNET as N_UNET,
    N_UPSCALE as N_UPSCALE,
    N_UPSCALE_PARAMS as N_UPSCALE_PARAMS,
    N_UPSCALE_SPLIT as N_UPSCALE_SPLIT,
    N_VAE_VIDEO as N_VAE_VIDEO,
    OPTIONAL_WEIGHTS as OPTIONAL_WEIGHTS,
    OPTION_NODE_PACKS as OPTION_NODE_PACKS,
    PARASYTE_LORA as PARASYTE_LORA,
    REQUIRED_WEIGHTS as REQUIRED_WEIGHTS,
    SAGE_CLASS as SAGE_CLASS,
    SAGE_PACK as SAGE_PACK,
    SPARSE_BACKEND as SPARSE_BACKEND,
    SPARSE_MODES as SPARSE_MODES,
    SPARSE_PRESETS as SPARSE_PRESETS,
    TARGET_KEY as TARGET_KEY,
    TURBO_LORA as TURBO_LORA,
    TURBO_STEPS as TURBO_STEPS,
    UNFETCHABLE as UNFETCHABLE,
    UPSCALE_MODEL as UPSCALE_MODEL,
    WORKFLOW_FILENAME as WORKFLOW_FILENAME,
    DYNAMIC_VRAM_FORCE as _DYNAMIC_VRAM_FORCE,
    DYNAMIC_VRAM_OFF_MODES as _DYNAMIC_VRAM_OFF_MODES,
    DYNAMIC_VRAM_SWITCH as _DYNAMIC_VRAM_SWITCH,
    FAST_DISK_FLAG as _FAST_DISK_FLAG,
    HIGH_RAM_FLAG as _HIGH_RAM_FLAG,
    VERSION_RE as _VERSION_RE,
    drop_sage as _drop_sage,
    graft_latent_upscale as _graft_latent_upscale,
    graft_sparse as _graft_sparse,
    graft_stock_accel as _graft_stock_accel,
    graft_test_lora as _graft_test_lora,
    graft_turbo as _graft_turbo,
    insert_into_chain as _insert_into_chain,
    loras_write_dir as _loras_write_dir,
    make_t2v as _make_t2v,
    model_readers as _model_readers,
    profile as _profile,
    video_runs as _video_runs,
    weight_present as _weight_present,
    accel_spec as accel_spec,
    accelerations_status as accelerations_status,
    build_workflow as build_workflow,
    clamp_megapixels as clamp_megapixels,
    comfyui_launch_facts as comfyui_launch_facts,
    deploy_checkpoint as deploy_checkpoint,
    deploy_file as deploy_file,
    deployed_loras as deployed_loras,
    eros_on_disk as eros_on_disk,
    import_external_lora as import_external_lora,
    knows_fast_disk as knows_fast_disk,
    last_frame_command as last_frame_command,
    launch_advice as launch_advice,
    load_base_workflow as load_base_workflow,
    missing_weights as missing_weights,
    new_prefix as new_prefix,
    normalise_accel as normalise_accel,
    normalise_sparse as normalise_sparse,
    option_availability as option_availability,
    preflight as preflight,
    registered_classes as registered_classes,
    snap_frames as snap_frames,
    studio_ready as studio_ready,
    trained_loras as trained_loras,
    undeploy_lora as undeploy_lora,
    workflow_path as workflow_path,
)

import os
import subprocess
import re
import uuid


# ── The base graph ───────────────────────────────────────────────────────────
# 18 nodes: loaders (6/13/11/24), the image branch (114 → 119 → 120), the H3
# conditioner (104), sampling (15/16/17/9/14), decode (10/23) and mux (91/92),
# plus SageAttention (600) sitting between the UNET and everything that reads
# the model.

# Node ids of the base graph that the grafts read or rewrite. Named because
# `workflow["9"]` five hundred lines from here says nothing about which node
# just had its step count changed.
N_CLIP = '13'           # CLIPLoader — Qwen3-VL text encoder
N_VAE_AUDIO = '24'

# Grafted ids. The ranges are deliberately spread out: a collision would
# overwrite a node with no message at all, in a dict where every key is a
# string that looks like every other key.

# ── The weights this graph names ─────────────────────────────────────────────
# The OFFICIAL base. Kept as a constant rather than read off the JSON because
# the 10Eros swap has to be able to say which base a run actually used.

# 🔥 10Eros-Max — a THIRD-PARTY finetune of H3 (cicalooo), int8 convrot, in the
# `skip_edges` variant (blocks 0/1/48/49 kept in BF16, which its own SKIP_EDGES
# note calls "the safer starting point when comparing quality").
#
# Never elected in silence: the option is off by default and the official base
# stays the graph's. It also imposes its own faces, which is exactly wrong when
# the thing being tested is whether YOUR LoRA reproduces an identity — the UI
# says so, and the identity recipe measured on this pipeline uses the official
# base for that reason.

# ⚡ The 6-step distillation LoRA (larryvrh v4, step 600 EMA — the top row of the
# multimodalart H3 acceleration arena at 6 steps), applied through its OWN node, not
# a standard loader. Both halves of that sentence were paid for:
#
#   * the file uses H3's bare key naming (`blocks.0.attn…`) plus 102 adaln keys.
#     `MiniMaxH3TurboLoRA` re-prefixes the keys AND re-injects the adaln that the
#     pruned base collapsed into a curve. Hand the same file to a standard
#     loader and the adaln half is simply missing.
#   * a standard loader MERGES into the weights (`add_patches`). On an int8
#     base that pushes modules into lowvram patches and re-quantises on every
#     forward pass — measured elsewhere at step 1 unfinished after 6 min 37,
#     against ~9 s/step without. The dedicated node runs the LoRA alongside the
#     base instead (bypass), immune to where the weights happen to sit.

# Six, not four. The model card is explicit — "4 steps is the recommended
# MINIMUM; 4-8 is the useful range. 6-8 steps look noticeably better than 4" —
# and at 4 steps with fast motion this checkpoint trails ghosting.

# ⚡ The accelerations the Render panel offers: the top three rows of the
# multimodalart MiniMax-H3 acceleration arena (human preference Elo, ~7 400
# votes per task, 95 % intervals about ±26 — so the three are statistical
# ties), every one of them at 6 steps and about 4× the 28-step reference.
# `turbo` is larryvrh's LoRA through its OWN nodes (a LoRA node and the
# double-clock sampler, see _graft_turbo). The other two are ordinary LoRAs
# for the stock loader, run on the stock euler sampler at the sigma shift
# their cards and the arena ran them at (video 8, audio 3; the base's own
# grid is 12/3). Strengths are the arena's verified settings, not 1.0: the
# Parasyte file's alpha convention wants 4-5, the merge's card says 0.6-0.8.





# Without turbo the base is not distilled and needs a real schedule.

# ⚡ Sparse attention (H3-Optimizations, Zironic). Both levels are the AUTHOR's,
# not ours: `default` is the node's own defaults, `conservative` raises the
# budget and holds the schedule's edges denser — the exact shape of the node's
# "Denser Early/Late" toggle applied to a higher budget.
#
# `max` carries the same numbers as `default` and differs only in WHERE it is
# applied (see `_graft_sparse`): it is the one level that lets the sparse graph
# touch the base sampling pass as well.

# Backend left at the node's embedded default. FROST BF16 exists on SM89 but an
# explicitly named backend FAILS when it is unavailable, and this graph is also
# meant to run on a rented GPU nobody inspected.

# 🔬 The latent upscaler. H3 emits an INTERLEAVED latent — 24 video channels and
# 32 audio channels in one tensor — which image upscalers cannot read; they have
# to decode to pixels, enlarge, and re-encode, which is where the re-muxed audio
# and the tile seams come from. This one enlarges inside the model's own domain
# and the audio passes through untouched.

# The profile key in the shared target catalogue. The studio takes fps and the
# legal clip lengths from there rather than restating them, so a clip generated
# here and a clip cut for training cannot drift apart.



# H3's VAE packs 17 pixel frames per chunk, so a legal length is ≡ 5 (mod 17).
_FRAME_MOD, _FRAME_OFFSET = 17, 5
# Generation reaches further than training does. The catalogue stops at 209
# because that is where TRAINING clip lengths stop being useful; the model
# itself renders to ~15 s at 24 fps, and refusing that here would cap the studio
# at 8.7 s for a reason that has nothing to do with the studio.
FRAMES_MIN, FRAMES_MAX = 22, 362

# And the default is the STUDIO's, not the catalogue's. The catalogue's
# `frame_default` is 39 because that is how long a TRAINING clip should be; the
# same preset carries 107 on its preview line, and reading the wrong one of those
# two numbers has already cost this project a wrong default once. A test clip
# wants enough motion to judge (39 frames is 1.6 s — barely a gesture) without
# paying the ~2.7x per-step cost of 107, so it sits between them.

# Resolution, in megapixels at node 119. The ceiling is the MODEL's, not a
# card's: the sweet spot for faces sits near 1.0 MP and the machine that runs
# the job decides what it can hold.
MP_MIN, MP_MAX, MP_DEFAULT = 0.1, 2.0, 0.3

# Where the studio deploys a trained video LoRA so ComfyUI can list it. `h3` is
# the subfolder the H3 LoRAs of this ecosystem already live in; `lds` keeps the
# app's own deployments distinct from files the user put there by hand.


class VideoStudioAssetsMissing(Exception):
    """Raised by the preflight when the graph cannot run on this install.

    Carries what is missing so the caller can name each file and node instead of
    letting ComfyUI answer "Value not in list: unet_name" three screens later.
    """

    def __init__(self, missing_files, missing_nodes):
        self.missing_files = list(missing_files)
        self.missing_nodes = list(missing_nodes)
        super().__init__('video studio assets missing: '
                         f'{len(self.missing_files)} file(s), '
                         f'{len(self.missing_nodes)} node(s)')












# ── The build ────────────────────────────────────────────────────────────────























# ═══════════════════════════════════════════════════════════════════════════
# The runtime half: what is on disk, what ComfyUI can see, and the queue.
# Everything above this line is pure; everything below touches the world.
# ═══════════════════════════════════════════════════════════════════════════

import logging

logger = logging.getLogger(__name__)
















# A LoRA is one safetensors file. The extension is not decoration here: it is
# what ComfyUI's LoraLoader reads, and copying a .ckpt or a .pt into the folder
# would put an entry in the picker that fails at generation time.








def clips_dir(create=True):
    """Where finished test clips live, away from ComfyUI's output directory.

    Same reasoning as the image studio's per-dataset folder: the clip has to
    survive whatever ComfyUI does with its own outputs, and be served by the app
    under a path it controls.
    """
    from lds_sdk.video_host import config as cfg
    root = cfg.data_dir() / 'video_tests'
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root


def enqueue_clip(user_id, *, prompt, mode='i2v', image=None, lora=None,
                 lora_strength=1.0, run_id=None, dataset_id=None, seed=None,
                 steps=None, frames=None, megapixels=MP_DEFAULT, aspect='auto',
                 turbo=False, accel=None, eros=False, sparse='', latent_upscale=False,
                 source_ratio=None, skip_preflight=False, continues=None) -> dict:
    """Build the graph, record the clip, queue the job — in that order.

    The row is written BEFORE the queue insert and in the SAME transaction, so a
    job can never exist without the row that explains what it was: the queue
    monitor's completion callback resolves by `job_id`, and a missing row means
    a finished clip nobody can attribute.
    """
    from lds_video.models import db
    from lds_sdk.video_runtime import queue as queue_manager
    from lds_video.models import VideoTestClip

    # Keep the T2V canvas choice with the clip so Reuse cannot inherit a later
    # render's format. I2V follows its source image instead of a canvas preset.
    mode = 't2v' if str(mode or 'i2v').lower() == 't2v' else 'i2v'
    aspect = str(aspect or 'auto').strip().lower()
    if mode == 'i2v' or aspect not in ('auto', 'portrait', 'landscape', 'square'):
        aspect = 'auto'

    # ONE /object_info read for the whole launch, and it decides two things:
    # whether SageAttention goes into the graph at all, and (through the
    # preflight below) whether an armed option's nodes are there. Reading it
    # twice would let a ComfyUI that restarts between the two answer differently
    # for the same clip.
    # ⏭ A continuation: the clip this one will be joined behind. Checked
    # before anything is queued — a parent that is not done has no last frame.
    parent = None
    if continues:
        parent = VideoTestClip.query.filter_by(id=int(continues)).first()
        if parent is None or parent.status != 'done' or not parent.filename:
            raise ValueError('the clip to continue has not finished rendering')
    classes = registered_classes()
    built = build_workflow(
        prompt=prompt, mode=mode, image=image, seed=seed, steps=steps,
        frames=frames, megapixels=megapixels, aspect=aspect, lora=lora,
        lora_strength=lora_strength, turbo=turbo, accel=accel, eros=eros,
        eros_on_disk=eros_on_disk() if eros else False, sparse=sparse,
        latent_upscale=latent_upscale, source_ratio=source_ratio,
        sage=sage_available(classes), filename_prefix=new_prefix(user_id))
    if not skip_preflight:
        preflight(built['workflow'])

    job_id = str(uuid.uuid4())
    clip = VideoTestClip(
        run_id=run_id, dataset_id=dataset_id, job_id=job_id, status='pending',
        prompt=prompt, mode=mode, aspect=aspect,
        source_image=image, seed=built['seed'], steps=built['steps'],
        frames=built['frames'], megapixels=built['megapixels'],
        fps=float(_profile().get('fps') or 24.0), base_model=built['base'],
        lora=lora, lora_strength=float(lora_strength) if lora else None,
        turbo=(built['accel'] == 'turbo'), accel=(built['accel'] or None),
        sparse=normalise_sparse(sparse), latent_upscale=bool(latent_upscale),
        continues_of=(parent.id if parent else None))
    db.session.add(clip)
    db.session.flush()          # mint the id inside the same transaction
    queue_manager.add_job(job_type='image', user_id=str(user_id),
                          workflow_data=built['workflow'], prompt=prompt or '',
                          job_id=job_id,
                          metadata={'model_name': 'video_lora_test',
                                    'is_video_test': True,
                                    'clip_id': clip.id},
                          commit=False)
    db.session.commit()
    logger.info('video studio: queued clip %s (%s)', clip.id,
                ', '.join(built['notes']) or 'no options')
    return {'clip_id': clip.id, 'job_id': job_id, 'seed': built['seed'],
            'frames': built['frames'], 'steps': built['steps'],
            'notes': built['notes']}


# ↗ VFI. The checkpoint, the multiplier and every dial below are read from the
# maintainer's image generator (workflows/video-generation/vfi.json) rather than
# chosen here: the two apps drive the same ComfyUI, and a clip smoothed in one
# should be the clip smoothed in the other. rife49 is what that graph loads;
# `fast_mode` and `ensemble` are its settings; the cache is cleared every 16
# frames, which is what keeps a 200-frame clip inside VRAM.
VFI_CKPT = 'rife49.pth'
VFI_MULTIPLIER = 2
VFI_CLEAR_CACHE_EVERY = 16
# h264 at crf 19, yuv420p — the same container the generator writes, so the
# smoothed clip plays anywhere the original did.
VFI_CRF = 19

N_VFI_LOAD, N_VFI_RIFE, N_VFI_SAVE = 'v1', 'v2', 'v3'


def build_vfi_workflow(*, video_path, fps, multiplier=VFI_MULTIPLIER,
                       filename_prefix=None) -> dict:
    """The interpolation graph for ONE finished clip. Pure — no disk, no queue.

    The source is given as an ABSOLUTE path: the clip lives in this app's own
    folder (clips_dir), never in ComfyUI's output, and VHS_LoadVideoPath takes a
    path rather than a name precisely so a file outside that tree can be read.
    The output rate is the source's times the multiplier, which is what makes
    this a SMOOTHING rather than a slow motion — the clip keeps its duration and
    gains frames.
    """
    rate = round(float(fps or 24) * int(multiplier), 3)
    return {
        N_VFI_LOAD: {
            'class_type': 'VHS_LoadVideoPath',
            'inputs': {'video': str(video_path), 'force_rate': 0,
                       'custom_width': 0, 'custom_height': 0,
                       'frame_load_cap': 0, 'skip_first_frames': 0,
                       'select_every_nth': 1, 'format': 'AnimateDiff'},
        },
        N_VFI_RIFE: {
            'class_type': 'RIFE VFI',
            'inputs': {'ckpt_name': VFI_CKPT,
                       'frames': [N_VFI_LOAD, 0],
                       'clear_cache_after_n_frames': VFI_CLEAR_CACHE_EVERY,
                       'multiplier': int(multiplier), 'fast_mode': True,
                       'ensemble': True, 'scale_factor': 2},
        },
        N_VFI_SAVE: {
            'class_type': 'VHS_VideoCombine',
            'inputs': {'images': [N_VFI_RIFE, 0], 'frame_rate': rate,
                       'loop_count': 0,
                       'filename_prefix': filename_prefix or 'lds_vfi',
                       'format': 'video/h264-mp4', 'pix_fmt': 'yuv420p',
                       'crf': VFI_CRF, 'save_metadata': True,
                       'trim_to_audio': False, 'pingpong': False,
                       'save_output': True},
        },
    }


def interpolate_clip(user_id, clip_id, multiplier=VFI_MULTIPLIER) -> dict:
    """↗ Smooth a finished clip: queue a RIFE pass over its own file.

    A NEW row, never an edit of the old one: the smoothed clip is a different
    artefact with a different frame rate, and overwriting the original would
    destroy the comparison the studio exists for. It carries the source's
    settings so the card still says what made it, plus `vfi_of` so the pair
    stays readable.

    Refused rather than queued when the interpolation nodes are absent — the
    job would otherwise die inside ComfyUI with a message nobody sees.
    """
    from lds_video.models import db
    from lds_sdk.video_runtime import queue as queue_manager
    from lds_video.models import VideoTestClip

    src = VideoTestClip.query.filter_by(id=int(clip_id)).first()
    if src is None:
        raise ValueError('clip not found')
    if src.status != 'done' or not src.filename:
        raise ValueError('that clip has not finished rendering yet')
    path = os.path.join(str(clips_dir()), os.path.basename(src.filename))
    if not os.path.isfile(path):
        raise ValueError('that clip is no longer on disk')

    classes = registered_classes()
    spec = OPTION_NODE_PACKS['vfi']
    if classes is not None:
        gone = [c for c in spec['classes'] if c not in classes]
        if gone:
            raise ValueError(
                f"this ComfyUI has no {', '.join(gone)} — install "
                f"{spec['pack']} ({spec['search']} in ComfyUI-Manager) and "
                f"try again")

    mult = max(2, min(8, int(multiplier or VFI_MULTIPLIER)))
    job_id = str(uuid.uuid4())
    workflow = build_vfi_workflow(video_path=path, fps=src.fps or 24,
                                  multiplier=mult,
                                  filename_prefix=new_prefix(user_id))
    clip = VideoTestClip(
        run_id=src.run_id, dataset_id=src.dataset_id, job_id=job_id,
        status='pending', prompt=src.prompt, mode=src.mode,
        aspect=src.aspect or 'auto', accel=src.accel,
        source_image=src.source_image, seed=src.seed, steps=src.steps,
        # The frame COUNT grows with the rate, so the clip lasts exactly as
        # long — RIFE inserts between frames, it does not slow anything down.
        frames=(src.frames or 0) * mult if src.frames else None,
        megapixels=src.megapixels, fps=float(src.fps or 24) * mult,
        base_model=src.base_model, lora=src.lora,
        lora_strength=src.lora_strength, turbo=bool(src.turbo),
        sparse=src.sparse, latent_upscale=bool(src.latent_upscale),
        vfi_of=src.id)
    db.session.add(clip)
    db.session.flush()
    queue_manager.add_job(job_type='image', user_id=str(user_id),
                          workflow_data=workflow, prompt=src.prompt or '',
                          job_id=job_id,
                          metadata={'model_name': 'video_lora_test',
                                    'is_video_test': True,
                                    'clip_id': clip.id},
                          commit=False)
    db.session.commit()
    logger.info('video studio: queued VFI x%s of clip %s as %s',
                mult, src.id, clip.id)
    return {'clip_id': clip.id, 'job_id': job_id, 'multiplier': mult,
            'fps': clip.fps}


def link_completed_clip(job_id, filename, failed=False, reason=None):
    """Attach a finished ComfyUI job to its clip row.

    Runs in the queue monitor thread, whose session may hold a stale read
    snapshot — hence the rollback-and-re-read before concluding the row is
    absent, exactly as the image studio's callback does.

    The mp4 comes back under the history's `images` key like any other output
    (that is how `SaveVideo` reports), so nothing in the polling path had to
    change for video.
    """
    from lds_video.models import db
    from lds_video.models import VideoTestClip
    clip = VideoTestClip.query.filter_by(job_id=job_id).first()
    if clip is None:
        db.session.rollback()
        clip = VideoTestClip.query.filter_by(job_id=job_id).first()
    if clip is None:
        logger.warning('video studio: no clip row for job %s', job_id)
        return
    if clip.status != 'pending':
        logger.info('video studio: clip %s already %s — late completion ignored',
                    clip.id, clip.status)
        return
    # Read before the row settles, on the failure path too: a clip that died
    # after four minutes of rendering says something a bare "failed" does not.
    clip.render_seconds = _render_seconds(job_id)
    if failed:
        clip.status = 'failed'
        clip.error = (reason or 'Generation failed (see the server log in '
                                'Settings for the ComfyUI error).')
        db.session.commit()
        return
    clip.filename = filename
    clip.status = 'done'
    _bring_clip_home(filename)
    continues = getattr(clip, 'continues_of', None)
    clip_id = clip.id
    # Committed BEFORE any join: from here the row is a valid render (the
    # part), and the encode below runs with no write transaction open. It ran
    # inside this one once — measured: every other writer got "database is
    # locked" for the length of ffmpeg (up to its 600 s timeout).
    db.session.commit()
    if continues:
        # ⏭ The part becomes the whole: parent, then this render.
        _join_continuation(clip_id)


# ── ⏭ Continue: the last frame as the next start frame, the clips joined ──

def _run_ffmpeg(cmd, timeout=600):
    """The app's subprocess convention for ffmpeg (video_bank_service has the
    same): no console window in the frozen Windows build, utf-8 stderr with
    replacement, and a timeout."""
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=timeout,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))




def last_frame_png(clip_id) -> str:
    """The clip's last frame as a PNG next to its mp4 (`clip_<id>_last.png`),
    extracted once and kept; the picture the next clip starts from."""
    from lds_video.models import VideoTestClip
    from lds_sdk.video_host import ffmpeg_tools
    clip = VideoTestClip.query.filter_by(id=int(clip_id)).first()
    if clip is None:
        raise LookupError('clip not found')
    if clip.status != 'done' or not clip.filename:
        raise ValueError('that clip has not finished rendering yet')
    root = str(clips_dir())
    src = os.path.join(root, os.path.basename(clip.filename))
    if not os.path.isfile(src):
        raise ValueError('that clip is no longer on disk')
    dst = os.path.join(root, f'clip_{int(clip_id)}_last.png')
    if os.path.isfile(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst
    ffmpeg = ffmpeg_tools.ffmpeg_path()
    if not ffmpeg:
        raise ValueError('ffmpeg is needed to read the last frame — install the video extra from Setup')
    # Concurrent previews and continuations must never see a partial PNG. Keep
    # the previous complete image until ffmpeg succeeds, then publish in place.
    tmp = os.path.join(root, f'.clip_{int(clip_id)}_last.{uuid.uuid4().hex[:8]}.png')
    try:
        r = _run_ffmpeg(last_frame_command(ffmpeg, src, tmp), timeout=120)
        if r.returncode != 0 or not os.path.isfile(tmp):
            raise ValueError(f'the last frame could not be read: {(r.stderr or "")[-300:]}')
        os.replace(tmp, dst)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return dst


def _probe_media(ffmpeg, path) -> dict:
    """What ffmpeg sees in a file, read off its own `-i` banner: whether it
    has a sound track, and how long it plays. The join needs both — a smoothed
    clip has no sound (its VHS_VideoCombine is given pictures only), and a
    silent side joined to a sounding one must be padded with silence of ITS
    length, not muted along with the other side (found in verification,
    2026-09-03: the blind `-an` fallback threw the new part's sound away)."""
    r = _run_ffmpeg([ffmpeg, '-hide_banner', '-i', path], timeout=60)
    text = (r.stderr or '') + (getattr(r, 'stdout', '') or '')
    audio = re.search(r'Stream #\d+:\d+.*?: Audio', text) is not None
    m = re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)', text)
    duration = None
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return {'audio': audio, 'duration': duration}


def continuation_command(ffmpeg, parent, part, dst, width, height, fps, *, part_fps=None,
                         parent_audio=True, part_audio=True, parent_seconds=None,
                         part_seconds=None):
    """Parent, then the new part: one video, at the parent's cadence.

    The part's FIRST frame is dropped — it is the parent's last frame, the
    picture the part was conditioned on, and kept it freezes the join for one
    frame — and its audio is trimmed by the same 1/fps (the PART's fps: a
    smoothed parent plays at 48 while its part rendered at 24) so the two stay
    in step. Both sides are forced to one constant cadence (`fps=`): concat
    accepts mixed rates and writes a variable-rate file whose stated fps then
    lies to Smooth and to the card. The part is scaled to the parent's size in
    case the dials changed between the two.

    Sound: each side that has a track keeps it (resampled to one format, or
    concat refuses the pair); a side without one is padded with silence of
    its own length, so the other side's sound survives. Neither side sounding
    → no track. Metadata is dropped: a studio clip carries its whole
    generation graph in a tag, and the join is not that graph."""
    fps = float(fps or 24)
    part_fps = float(part_fps or fps)
    trim = 1.0 / part_fps
    rate = f'{fps:g}'
    graph = (f'[1:v]trim=start_frame=1,setpts=PTS-STARTPTS,'
             f'scale={int(width)}:{int(height)}:flags=lanczos,setsar=1,fps={rate}[v1];'
             f'[0:v]setsar=1,fps={rate}[v0];[v0][v1]concat=n=2:v=1:a=0[v]')
    cmd = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', parent, '-i', part]
    fmt = 'aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo'
    if parent_audio or part_audio:
        if parent_audio:
            a0 = f'[0:a]{fmt}[a0]'
        else:
            if parent_seconds is None:
                raise ValueError('a silent parent needs its length to be padded with silence')
            a0 = f'anullsrc=r=48000:cl=stereo:d={max(float(parent_seconds), 0.01):.3f}[a0]'
        if part_audio:
            a1 = f'[1:a]atrim=start={trim:.6f},asetpts=PTS-STARTPTS,{fmt}[a1]'
        else:
            if part_seconds is None:
                raise ValueError('a silent part needs its length to be padded with silence')
            a1 = f'anullsrc=r=48000:cl=stereo:d={max(float(part_seconds) - trim, 0.01):.3f}[a1]'
        graph += f';{a0};{a1};[a0][a1]concat=n=2:v=0:a=1[a]'
        cmd += ['-filter_complex', graph, '-map', '[v]', '-map', '[a]', '-c:a', 'aac', '-b:a', '128k']
    else:
        cmd += ['-filter_complex', graph, '-map', '[v]', '-an']
    cmd += ['-c:v', 'libx264', '-crf', '19', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', '-map_metadata', '-1', dst]
    return cmd


def _join_continuation(clip_id) -> bool:
    """⏭ The finished part joined behind the clip it continues, as THIS clip's
    file: what the card plays is the whole, the parent followed by the new
    motion. The parent stays as it is; the part is not kept apart.

    Called AFTER the completion is committed, and committing on its own: the
    row is already 'done' with the part as its file — a valid render — while
    ffmpeg runs, so no write lock is held for the length of an encode (the
    Bank's passes keep the same rule, `_release_db_before_inference`). A join
    that fails, or raises, leaves the part as the clip and says so in
    `error`, which the card shows under its lineage line."""
    from lds_video.models import db
    from lds_video.models import VideoTestClip
    from lds_sdk.video_host import ffmpeg_tools

    def _fail(msg):
        row = VideoTestClip.query.filter_by(id=int(clip_id)).first()
        if row is not None:
            row.error = f'continuation not joined: {msg}'[:300]
            db.session.commit()
        return False

    # 1. What the join needs, read in one short transaction.
    clip = VideoTestClip.query.filter_by(id=int(clip_id)).first()
    if clip is None or not clip.continues_of or not clip.filename:
        return False
    parent = VideoTestClip.query.filter_by(id=int(clip.continues_of)).first()
    root = str(clips_dir())
    part = os.path.join(root, os.path.basename(clip.filename))
    if parent is None or not parent.filename:
        return _fail('the clip it continues is gone')
    src = os.path.join(root, os.path.basename(parent.filename))
    if not os.path.isfile(src) or not os.path.isfile(part):
        return _fail('a file is missing')
    ffmpeg = ffmpeg_tools.ffmpeg_path()
    if not ffmpeg:
        return _fail('ffmpeg is not available')
    parent_id, parent_frames, part_frames = parent.id, parent.frames, clip.frames
    fps = float(parent.fps or clip.fps or 24)
    part_fps = float(clip.fps or fps)
    try:
        from PIL import Image
        with Image.open(last_frame_png(parent_id)) as im:
            width, height = im.size
    except Exception as exc:  # noqa: BLE001 — no size, no scaling target
        return _fail(str(exc))
    db.session.commit()   # nothing dirty — this only ends the read before the encode

    # 2. The encode, with no transaction open.
    stem, _ = os.path.splitext(os.path.basename(part))
    out_name = f'{stem}_joined.mp4'
    dst = os.path.join(root, out_name)
    try:
        p_src, p_part = _probe_media(ffmpeg, src), _probe_media(ffmpeg, part)
        parent_audio, part_audio = p_src['audio'], p_part['audio']
        # A silent side is padded with silence of its own length; when that
        # length cannot be read the pair goes without sound rather than out of step.
        if ((not parent_audio and part_audio and p_src['duration'] is None)
                or (parent_audio and not part_audio and p_part['duration'] is None)):
            parent_audio = part_audio = False
        r = _run_ffmpeg(continuation_command(
            ffmpeg, src, part, dst, width, height, fps, part_fps=part_fps,
            parent_audio=parent_audio, part_audio=part_audio,
            parent_seconds=p_src['duration'], part_seconds=p_part['duration']))
        if r.returncode != 0 or not os.path.isfile(dst):
            raise RuntimeError((r.stderr or '')[-300:] or 'ffmpeg wrote nothing')
    except Exception as exc:  # noqa: BLE001 — a timeout, a vanished binary, a refused graph: the part stays
        try:
            os.remove(dst)
        except OSError:
            pass
        # A timeout's own text is the whole command line — the two paths alone
        # outrun the 300 characters the card can show; say the one fact.
        msg = (f'ffmpeg timed out after {exc.timeout:.0f} s'
               if isinstance(exc, subprocess.TimeoutExpired) else str(exc))
        logger.warning('video studio: clip %s could not be joined behind clip %s: %s',
                       clip_id, parent_id, msg)
        return _fail(msg)

    # 3. Name the joint on the row and commit — then, and only then, let the part go.
    row = VideoTestClip.query.filter_by(id=int(clip_id)).first()
    if row is None:
        try:
            os.remove(dst)
        except OSError:
            pass
        return False
    row.filename = out_name
    if parent_frames and part_frames:
        # The part's frames, minus the dropped one, at the parent's cadence.
        row.frames = int(parent_frames) + int(round((int(part_frames) - 1) * fps / part_fps))
    row.fps = fps
    row.error = None
    db.session.commit()
    try:
        os.remove(part)
    except OSError:
        pass
    logger.info('video studio: clip %s joined behind clip %s -> %s', clip_id, parent_id, out_name)
    return True


def _render_seconds(job_id):
    """Seconds the queue spent on a job: from the worker's claim (`started_at`,
    stamped when the job is taken, so the wait in the queue is excluded) to the
    moment it settled (`completed_at`). ComfyUI's model loading is inside that
    window on purpose — it is what the user waited for, and on a machine whose
    RAM cannot hold the weights it is most of the number.

    None whenever the queue cannot say: no job row (a clip settled by hand), a
    stamp missing, a clock that went backwards — and a job the queue CANCELLED.
    That last one is the ComfyUI-restart path: the job stalls with its
    `started_at` kept, the barrier waits for the user, and `completed_at` is
    stamped when the barrier is reconciled, hours later if need be. The
    difference then measures the outage, not the render, and a card saying
    "failed after 6 h" would be a lie. A number here is a measurement, never a
    guess.
    """
    from lds_sdk.video_host.models import ImageGenerationQueue
    job = ImageGenerationQueue.query.filter_by(job_id=job_id).first()
    if job is None or job.status not in ('completed', 'failed'):
        return None
    if not job.started_at or not job.completed_at:
        return None
    secs = (job.completed_at - job.started_at).total_seconds()
    return round(secs, 1) if secs >= 0 else None


def _bring_clip_home(filename):
    """Bring the finished mp4 out of ComfyUI's output dir into the app's own.

    Disk claim first, HTTP `/view` fetch as the fallback: a ComfyUI pointed at a
    custom output directory (`--output-directory`, the desktop app's setting)
    has a path this app cannot know, but its API serves the file regardless.
    A failure here is not fatal — the row keeps the filename and the clip is
    still readable from ComfyUI.
    """
    from lds_sdk.video_host import studio as lts
    from lds_sdk.video_host import comfy_fs
    dst = os.path.join(str(clips_dir()), filename)
    if os.path.exists(dst):
        return
    out_dir = lts.comfy_output_dir()
    src = os.path.join(out_dir, filename) if out_dir else None
    try:
        # Same claim as the two image lanes: copy into place, treat dest-present
        # as success, unlink the source only if it lets us. A mp4 ComfyUI has
        # just flushed is the likeliest of our outputs to still be held open,
        # and `shutil.move`'s copy+unlink fallback raised AFTER the bytes had
        # landed — the half-claimed clip then satisfied the `dst` guard above
        # for good, and the /view fallback below was skipped by the raise.
        if src and comfy_fs.claim_output_file(src, dst):
            return
        from lds_sdk.video_host.comfyui import fetch_output_image_bytes
        data = fetch_output_image_bytes(filename)
        if data:
            with open(dst, 'wb') as fh:
                fh.write(data)
        else:
            logger.warning('video studio: %s is not on disk and /view returned '
                           'nothing — the clip stays with ComfyUI', filename)
    except OSError:
        logger.exception('video studio: could not bring %s home', filename)


# ═══════════════════════════════════════════════════════════════════════════
# What a machine needs before this lane can render anything — and what it is
# still missing right now.
#
# The Setup screen turns each key below into a button, so these names are not
# labels: they are `setup_installer.INSTALL_ACTIONS` entries. A name that does
# not exist there is a dead end by construction, which a contract test catches.
# ═══════════════════════════════════════════════════════════════════════════

# (setup action, ComfyUI subfolders it may live in, filename, why it is needed).
# REQUIRED first: a message built from this list reads worst-first.

# Optional weights: each one belongs to ONE checkbox, and its absence disables
# that checkbox rather than the lane.

# The weights the app will NOT fetch for you, and why — stated here rather than
# discovered as a silent gap:
#   * the latent upscaler has no authoritative home. The node's own README names
#     the FOLDER it reads and no download; the copies on the model hub are
#     community re-uploads whose provenance cannot be checked. Shipping an
#     installer button that pulls an unverifiable 0.6 GB file into somebody
#     else's ComfyUI is not a thing this app should do, so the preflight names
#     the folder instead and the checkbox says the file is missing.
#   * the 10Eros base is a third-party finetune, opt-in by design.

# Custom-node packs, per option. The BASE graph is deliberately absent from this
# table: it runs on a stock ComfyUI, which is what lets a new user render their
# first clip with nothing but the weights.
#
# SageAttention is absent too, and that is the same decision seen from the other
# side: it is a speed patch, its pack declares pip dependencies, and this app
# never pip-installs a third-party requirements file — so it is used when the
# target ComfyUI already has it and skipped when it does not.
# WHY THESE ARE LINKS AND NOT BUTTONS (maintainer's call, 2026-08-31)
# "Downloading models is fine, but we do not take responsibility for breaking a
# ComfyUI install." A weight is an inert file; a custom node is code ComfyUI
# imports at startup, and one bad import takes the server down for every other
# lane. So the app names the pack, links it, and lets the user install it on the
# ComfyUI side — where they can see what they are adding.

# SageAttention. Not an option and not a checkbox: a speed patch the graph keeps
# when the target ComfyUI has it and drops when it does not. Linked for the same
# reason as the three above, and installed the same way — by the user.
















# ⏱ How ComfyUI was STARTED decides more than any dial on this screen.
#
# The H3 set the graph loads weighs about 43 GB (DiT int8 21 + text encoder
# nvfp4 16 + the two VAEs 6), and ComfyUI's default loader keeps a copy of every
# weight it offloads in system RAM. On a machine whose RAM cannot hold that set
# beside the OS and the desktop, the models page through the swap file at every
# node change — measured per node on a 48 GB machine: a 56-frame clip took
# 348 s (319 s of them decoding the VAE), the next one 302-315 s. Started with
# `--fast-disk`, ComfyUI reads the weights back from the safetensors files
# instead: the same clip took 30 s cold and 21-24 s warm, RAM left alone.
#
# LDS's own launcher passes the flag (`comfyui_control._spawn`). A ComfyUI the
# user starts some other way — a .bat, a Desktop install, another machine —
# is not ours to configure, so the Studio asks the running instance what it
# was started with (`/system_stats` echoes its argv, its RAM and its version)
# and SAYS so when the flag is missing on a machine that needs it. Every
# "cannot tell" case stays silent: advice built on a guess would name a flag
# the user may already be passing, or one their ComfyUI does not know.
# psutil reports the RAM the OS can use, a little under the nominal size: the
# 48 GB machine above reads 47.7, a 64 GB one about 63.7. The floor sits under
# the nominal 64 GB it means, or that class of machine would get the card the
# comment above says it should not. Calibrated on one point (48 GB of RAM,
# 43 GB of weights); nothing in between has been measured.
# `--fast-disk` was declared in ComfyUI v0.23.0 (2026-06-01). argparse answers
# an unknown flag with an exit before the server exists, so advising it to an
# older instance would stop that ComfyUI from starting — the exact failure the
# launcher guards against by reading cli_args.py. Below this version, or
# without one, the advice stays silent.
# `--high-ram` is the user saying "I prefer the page file to model loading" —
# the opposite choice, made on purpose, whatever the loader. Never argued with.
# `--fast-disk` only steers ComfyUI's DYNAMIC loader (its whole effect runs
# through the vbar path). With that loader off the flag is inert, so advising
# it alone would send the user to a change that changes nothing. ComfyUI's own
# rule (`enables_dynamic_vram`): `--enable-dynamic-vram` forces the loader on;
# otherwise `--disable-dynamic-vram` or any of the memory modes below turns it
# off. The switch is what a launcher tuned for an older ComfyUI still carries
# (the maintainer's own did, calibrated on a 20 GB image model, and ComfyUI now
# announces it as "will be removed soon") — that one is named, to be removed.
# The modes are a choice, and the advice stays silent rather than argue.
