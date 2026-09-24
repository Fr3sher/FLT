"""The checkpoint-name parser — the one place that knows a save may carry a
multistage suffix, and every family's step is read through it so the single-file
and the paired case cannot drift.

Core on purpose, and pure (no torch, no ffmpeg, no database): the run graph
(`run_graph.py`) reads every save of every lane through it, the video lane
(`video_training.py`, which re-exports it) writes its pairs with it, and the
cloud lane restages its mirrors with it. An install without the video lane
still has run graphs to draw.
"""
import os
import re

# The suffixes `wan22_14b_model.save_lora` appends when it splits a state dict on
# `.transformer_1.` / `.transformer_2.`. Order matters only for readability; the
# parser matches whichever is present.
_STAGE_SUFFIXES = ('high_noise', 'low_noise')

# ai-toolkit zero-pads the step to 9 digits. 6 is the floor every consumer in this
# app already used, and it is what keeps a trailing '_v3' or '_rc74' from reading
# as a step.
_STEP_RE = re.compile(r'_(\d{6,})$')


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


def group_saves_by_step(saves, target=None) -> list:
    """The grouping behind `harvested_steps`, over any ``{filename: path}`` —
    the local run folder uses it too (`video_checkpoints.local_group`), so
    both lanes cut a Wan pair at the same seam.

    `target` numbers the FINAL save (a cloud run stamps its step count; the
    local lane passes None and the final is reported with `step: None`)."""
    by_step = {}
    for name, path in saves.items():
        step, _stage = split_checkpoint_name(name)
        final = step is None
        key = (target if final else step, final)
        by_step.setdefault(key, []).append((name, path))
    out = []
    for (step, final), items in sorted(by_step.items(),
                                       key=lambda kv: (kv[0][1], kv[0][0] or 0)):
        items.sort()
        out.append({'step': None if step is None else int(step), 'final': final,
                    'files': [n for n, _ in items],
                    'paths': [p for _, p in items]})
    return out
