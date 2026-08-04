"""Turning a built video dataset into an ai-toolkit job config — and reading back
what a two-expert model writes when it saves.

This is the video sibling of `lora_training._build_job_config_*`, kept in its own
module because it shares none of their inputs. Those builders read a `FaceDataset`
and its `train_settings` column; there is no such column on `video_dataset`, and
routing a video run through helpers that all `getattr(ds, ..., None)` would mean a
config assembled entirely from defaults that nobody could see. The entities are
different, so the builder is separate.

Like `video_targets`, this module is pure: a catalogue lookup, some arithmetic and
string work. No ffmpeg, no PyAV, no torch, no database. A cloud launcher can build
a config from a snapshot on a machine that has no trainer installed at all.

WHERE THE VALUES COME FROM
--------------------------
An end-to-end smoke run has been through this path: a dataset built by the video
Bank, handed to the local ai-toolkit, trained to decreasing loss (0.28 -> 0.23) at
81 frames and 384 px. The non-obvious settings below are that run's, and the two
shipped ai-toolkit example configs it derives from. Where no such source exists —
a base repository for LTX or MiniMax — this module RAISES rather than invents one.
A guessed repo id does not fail at build time; it fails after the GPU is rented.

WHAT IT COSTS, MEASURED
-----------------------
That run filled 24 GB and took 170-185 s per step. `low_vram` is why: it keeps one
expert on the CPU and shuttles it over PCIe every boundary switch. It is the
default here because a 24 GB card cannot do without it, and it is a PARAMETER
because the whole reason to move a video run to a rented 80 GB pod is to turn it
off.
"""
import math
import os
import re

from . import video_targets


class VideoTrainingUnsupported(ValueError):
    """This video dataset cannot be turned into a training config, and the reason
    is stated. Raised at BUILD time, on purpose: every one of these conditions
    would otherwise surface as a trainer crash or — worse — a silent misread, on a
    pod that is already being paid for."""


# Bases stated by an ai-toolkit example config shipped on this machine, keyed by
# the arch. Deliberately short. The two Wan entries are the only video bases any
# local source names; every other arch demands an explicit `base_model` from the
# caller. `wan21` covers both the 1.3B and the 14B in one catalogue profile, so
# the flagship is the default and a caller wanting the 1.3B names it.
_VERIFIED_BASES = {
    'wan21': 'Wan-AI/Wan2.1-T2V-14B-Diffusers',
    'wan22_14b': 'ai-toolkit/Wan2.2-T2V-A14B-Diffusers-bf16',
}

# Accuracy-recovery adapters, keyed by arch. The 4-bit path is only usable WITH
# one: `quantize: true` + `qtype: uint4` alone is a measurably worse run, so the
# adapter travels with the qtype string rather than being a separate opt-in.
_RECOVERY_ADAPTERS = {
    'wan22_14b': ('uint4|ostris/accuracy_recovery_adapters/'
                  'wan22_14b_t2i_torchao_uint4.safetensors'),
}

# The two-expert (MoE) arches. Two consequences, and they are unrelated to each
# other: training needs `switch_boundary_every` to alternate between the experts,
# and SAVING writes two files per checkpoint instead of one.
_MOE_ARCHES = ('wan22_14b', 'wan22_14b_i2v')

# From ai-toolkit's own 24 GB example and from the run that trained. Not a tuning
# knob we picked: a boundary this tight is what keeps both experts learning
# together instead of the run becoming two half-trainings in sequence.
_SWITCH_BOUNDARY_EVERY = 10

# The suffixes `wan22_14b_model.save_lora` appends when it splits a state dict on
# `.transformer_1.` / `.transformer_2.`. Order matters only for readability; the
# parser matches whichever is present.
_STAGE_SUFFIXES = ('high_noise', 'low_noise')

# ai-toolkit zero-pads the step to 9 digits. 6 is the floor every consumer in this
# app already used, and it is what keeps a trailing '_v3' or '_rc74' from reading
# as a step.
_STEP_RE = re.compile(r'_(\d{6,})$')


def is_multistage_arch(arch) -> bool:
    """Does this architecture save its LoRA as a high-noise / low-noise PAIR?

    True for the Wan 2.2 14B MoE arches. `split_multistage_loras` defaults to True
    in `toolkit/config_modules.py`, so this is the shape a caller gets unless it
    goes out of its way to ask for a combined file — and the combined file is not
    what any downstream loader here expects."""
    return str(arch or '') in _MOE_ARCHES


def split_checkpoint_name(filename):
    """``(step, stage)`` for one saved checkpoint filename.

    `step` is None for the run's FINAL save, which carries no number in either
    world — that is how a caller flags it final. `stage` is `'high_noise'`,
    `'low_noise'`, or None for a single-file arch.

    THIS EXISTS BECAUSE OF THE ANCHOR. Every step read in this app was
    ``_(\\d{6,})\\.safetensors$``, and `save_lora` builds its pair by rewriting
    `.safetensors` into `_high_noise.safetensors`. The step is therefore no longer
    at the end of the stem, the regex misses, and each consumer's `or target`
    fallback labels EVERY intermediate save with the run's total step count — six
    identical pills, and a "continue from step 50" that resumes from step 100.
    Nothing raises; the numbers are just wrong.

    The stage is only recognised at the very end of the stem, so a dataset called
    "low noise study" does not turn all of its saves into low-noise halves."""
    stem = os.path.basename(str(filename or ''))
    if stem.lower().endswith('.safetensors'):
        stem = stem[:-len('.safetensors')]
    stage = None
    for suffix in _STAGE_SUFFIXES:
        if stem.endswith('_' + suffix):
            stage = suffix
            stem = stem[:-(len(suffix) + 1)]
            break
    m = _STEP_RE.search(stem)
    return (int(m.group(1)) if m else None), stage


def restage_checkpoint_name(base: str, step, stage) -> str:
    """Rebuild a checkpoint filename from a new stem plus the step and stage read
    off the original — the inverse of `split_checkpoint_name`.

    The mirror into the local run folder needs this. Rebuilding from the step
    alone gives BOTH halves of a pair the same name, and the second copy is then
    refused as a collision with the first — one expert of every checkpoint lost,
    with a log line that says the local file was protected."""
    parts = [base]
    if step is not None:
        parts.append(f'{int(step):09d}')
    if stage:
        parts.append(stage)
    return '_'.join(parts) + '.safetensors'


def _resolution_for(width, height, size_multiple):
    """The single scalar that asks ai-toolkit for exactly this clip's pixels.

    `resolution` is not a width. `toolkit/buckets.get_bucket_for_image_size` reads
    it as a pixel CAP — `max_pixels = resolution ** 2`, then
    `target = min(total_pixels, max_pixels)` — and rescales the clip's own aspect
    ratio under it. So the faithful scalar for a w x h clip is the geometric mean
    sqrt(w*h): the cap equals the clip's own pixel count, the scaler is exactly
    1.0, and nothing is resized in either direction.

    Floored to the target's size multiple, never rounded up: the multiple is the
    VAE's spatial stride, and rounding up would ask for more pixels than the clips
    contain and upscale data that does not exist."""
    side = math.sqrt(width * height)
    step = size_multiple or 1
    return max(step, int(side // step) * step)


def build_job_config(video_ds, dataset_folder: str, steps: int,
                     training_folder=None, base_model=None, low_vram=True,
                     sample_prompts=None, save_every=None,
                     max_step_saves_to_keep=2, rank=16) -> dict:
    """The ai-toolkit job config for training on a built video dataset.

    `video_ds` needs the `video_dataset` columns and nothing else: `name`,
    `target_profile`, `frames`, `fps`, `width`, `height`. It is duck-typed rather
    than a model import so a cloud launcher can pass a frozen snapshot of a row
    whose dataset may since have been rebuilt.

    `dataset_folder` is used VERBATIM. A video dataset is already the shape
    ai-toolkit wants — a flat folder of .mp4 files with homonym .txt captions — so
    unlike the image families there is no export to re-run; the caller passes the
    local folder, and `_cloudify_job_config` rewrites it to the pod path with the
    same string swap it does for every other family.

    `training_folder` is the same cloud seam as the image families: supplied, it is
    used as-is so a launch needs no local ai-toolkit; omitted, the caller is
    expected to have resolved it (this module has no run-root of its own).

    `low_vram` defaults True because 24 GB cannot do without it, and exists as a
    parameter because turning it off is the measured reason to rent a bigger GPU:
    the smoke run spent 170-185 s per step shuttling the idle expert over PCIe.

    `sample_prompts` defaults to none, and with none `disable_sampling` is True. A
    video preview is minutes of paid GPU per prompt and proves nothing about the
    dataset. Asked for, previews are rendered at the DATASET's own frame count and
    fps — a preview at another rate is not a preview of this LoRA.
    """
    key = getattr(video_ds, 'target_profile', None)
    profile = video_targets.get(key)
    if profile is None:
        raise VideoTrainingUnsupported(
            f'unknown video target profile {key!r} — this build has no rules for '
            'it, and Wan\'s would be a guess')
    arch = profile['aitk_arch']
    if not arch:
        raise VideoTrainingUnsupported(
            f'the {key!r} video target declares no ai-toolkit architecture, so no '
            'training config can be written for it — pick a catalogued target')

    frames = getattr(video_ds, 'frames', None)
    if not frames or not video_targets.is_legal_frames(key, frames):
        raise VideoTrainingUnsupported(
            f'{frames} frames is not a length {profile["label"]} can ingest — its '
            'VAE would silently drop the trailing frames of every clip')

    width = getattr(video_ds, 'width', None)
    height = getattr(video_ds, 'height', None)
    if not width or not height:
        raise VideoTrainingUnsupported(
            'this video dataset recorded no clip size, so the training resolution '
            'cannot be derived — rebuild it, or pass the size explicitly')

    name_or_path = base_model or _VERIFIED_BASES.get(arch)
    if not name_or_path:
        raise VideoTrainingUnsupported(
            f'no verified base model is known for {profile["label"]} — name the '
            'base repository to train it (nothing installed here states one, and '
            'a guessed repository id only fails once the pod is paid for)')

    model = {
        'arch': arch,
        'name_or_path': name_or_path,
        'quantize': True,
        'quantize_te': True,
        'qtype_te': 'qfloat8',
        'low_vram': bool(low_vram),
    }
    qtype = _RECOVERY_ADAPTERS.get(arch)
    if qtype:
        model['qtype'] = qtype
    if is_multistage_arch(arch):
        # Both experts, explicitly. Under low_vram ai-toolkit unloads whichever
        # one is idle; training only one of them yields half a LoRA that no
        # downstream loader here knows how to complete.
        model['model_kwargs'] = {'train_high_noise': True, 'train_low_noise': True}

    train = {
        'batch_size': 1,
        'steps': int(steps),
        'gradient_accumulation': 1,
        'train_unet': True,
        'train_text_encoder': False,
        'gradient_checkpointing': True,
        'noise_scheduler': 'flowmatch',
        'timestep_type': 'linear',
        'optimizer': 'adamw8bit',
        'lr': 1e-4,
        'optimizer_params': {'weight_decay': 1e-4},
        'dtype': 'bf16',
        'disable_sampling': not sample_prompts,
        # NOT `unload_text_encoder`. ai-toolkit offers exactly two routes to 24 GB
        # and they are not interchangeable: unloading encodes the TRIGGER WORD
        # ONLY and reuses that one embedding for every clip, discarding every
        # caption in the dataset without a word. Caching pre-encodes the real
        # captions. A captioned-clip lane can only ever use the second.
        'cache_text_embeddings': True,
    }
    if is_multistage_arch(arch):
        train['switch_boundary_every'] = _SWITCH_BOUNDARY_EVERY

    fps = getattr(video_ds, 'fps', None) or profile['fps'] or 16
    proc = {
        'type': 'sd_trainer',
        # 'output' is ai-toolkit's own default, relative to its root, and is what
        # the run that trained carried. Emitting the caller's None instead would
        # put a literal null in the config and fail inside the trainer.
        'training_folder': training_folder or 'output',
        'device': 'cuda:0',
        'network': {'type': 'lora', 'linear': int(rank), 'linear_alpha': int(rank)},
        'save': {
            'dtype': 'float16',
            'save_every': int(save_every or max(1, int(steps) // 2)),
            'max_step_saves_to_keep': int(max_step_saves_to_keep),
        },
        'datasets': [{
            'folder_path': dataset_folder,
            'caption_ext': 'txt',
            'caption_dropout_rate': 0.05,
            'num_frames': int(frames),
            'resolution': [_resolution_for(width, height,
                                           profile['size_multiple'])],
        }],
        'train': train,
        'model': model,
    }
    if sample_prompts:
        proc['sample'] = {
            'sampler': 'flowmatch',
            'sample_every': proc['save']['save_every'],
            'width': int(width),
            'height': int(height),
            'num_frames': int(frames),
            'fps': int(fps),
            'prompts': list(sample_prompts),
            'neg': '',
            'seed': 42,
            'guidance_scale': 3.5,
            'sample_steps': 4,
        }
    return {
        'job': 'extension',
        'config': {
            'name': job_name_for(video_ds),
            'process': [proc],
        },
    }


def job_name_for(video_ds) -> str:
    """A filesystem- and route-safe job name for this dataset. It becomes the save
    root on the pod and the stem of every checkpoint file, so it may only contain
    what ai-toolkit's own upload route preserves ([A-Za-z0-9._-])."""
    raw = (getattr(video_ds, 'name', None) or '').strip()
    safe = ''.join(c if (c.isalnum() or c in '_-') else '_' for c in raw).strip('_')
    return f'video_{safe}' if safe else f'video_dataset{getattr(video_ds, "id", 0)}'


# Kept as the name the image families use, so a reader grepping for the family of
# builders finds this one too.
_build_job_config_video = build_job_config
