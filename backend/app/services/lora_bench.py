"""⚖ LoRA bench — judge a LoRA you did NOT train here.

You download a LoRA from a model site, drop the .safetensors into ComfyUI's
``models/loras`` folder, and you want two answers: is it any good, and at what
strength should you load it? Until now the app made you build a whole dataset
first — which makes no sense, because you are not training anything.

The bench is a strength sweep of ONE file on a fixed prompt and a fixed seed.

WHY A SCRATCH DATASET
---------------------
``LoraTestImage.dataset_id`` is NOT NULL with an ``ON DELETE CASCADE`` FK, and
``dataset_id`` appears about a hundred times in ``lora_test_studio``. Making it
nullable would have meant auditing every one of those call sites, each of which
becomes a crash on a null id if missed — for no benefit in a single-user app.
So the bench owns ONE hidden ``FaceDataset`` row (``internal='bench'``) and
every downstream mechanism — cells, votes, the Wilson ranking, the low-confidence
flag, the GPU guard, resume, the grid export, the results gallery — keeps working
untouched.

The price of that choice is that the row must stay invisible EVERYWHERE a
dataset is listed, counted, exported or backed up. That gate is not spread
around: it lives in ``face_dataset_service.list_datasets`` (which the library,
the full backup, the canvas index and the HF index all read) plus
``dataset_list_stats``, and the two Test Studio surfaces that enumerate datasets
directly. ``tests/test_lora_bench_hidden.py`` pins each of them, and
``test_internal_dataset_filter_guard`` watches for the pattern coming back.

WHAT THIS MODULE DOES **NOT** DO
--------------------------------
It does not generate. It calls ``lora_test_studio.create_run`` — the Test
Studio's own engine — with a strict SUBSET of its parameters. A strict subset
cannot drift from the Test Studio or the Canvas the way a second pipeline would,
which is exactly why the bench is a new entry point and not a second lane. If a
"bench this LoRA" shortcut is ever wanted from the Canvas, it must be a
navigation link to the bench page — never a duplicated engine.
"""
from __future__ import annotations

import json
import logging
import os

from ..extensions import db
from ..models import FaceDataset, LoraTestImage
from ..utils.comfyui import FAMILY_LABELS, family_of_lora
from . import face_dataset_service as fds
from . import lora_test_studio as lts
from . import lora_training as lt

logger = logging.getLogger(__name__)

# The name the scratch row carries. Never shown in the library (it is filtered
# out of every listing) — it exists so that a developer opening the database, or
# a diagnostic dump, reads something that explains itself.
BENCH_DATASET_NAME = 'LoRA bench (scratch)'

# The families the Test Studio can actually render. `family_of_lora` knows more
# folders (flux, flux2klein, anima) but those have no test pipeline, so a file
# sitting in one of them cannot be benched — and the empty state says so by name
# rather than letting the picker look broken.
BENCH_FAMILIES = lts.FAMILIES

# The ComfyUI loras subfolder each family is scanned from, in the spelling a
# user has to type. `get_zimage_loras` also accepts 'zimage' / 'z-image'; the
# canonical one is what the training deploy writes, so it is what we advertise.
BENCH_FOLDERS = {'zimage': 'z image', 'sdxl': 'sdxl', 'krea': 'krea'}

# Default sweep: four points that answer "too weak / right / too strong" without
# spending eight generations on it. Editable in the UI.
DEFAULT_STRENGTHS = (0.4, 0.6, 0.8, 1.0)
MAX_BENCH_STRENGTHS = 8

# `ss_output_name` values that carry no information — kohya and ai-toolkit both
# write a run name here, and these are the ones that name the run instead of the
# subject. Prefilling the trigger field with "last" would be worse than leaving
# it empty: it looks like an answer.
_GENERIC_OUTPUT_NAMES = {
    'last', 'lora', 'loras', 'model', 'output', 'checkpoint', 'ckpt',
    'result', 'final', 'test', 'train', 'training', 'epoch', 'step', 'untitled',
}

# How many training tags to offer as SUGGESTIONS. They are not the trigger and
# are never prefilled — the most frequent tag of a character LoRA is very often
# a generic booru tag, and silently prefilling it is precisely the false verdict
# this feature exists to prevent.
_MAX_TAG_CANDIDATES = 6


def bench_folder_hint() -> str:
    """The sentence the empty state shows: WHERE to put a downloaded file.

    Someone arriving here has a .safetensors and no idea where the app looks.
    "Nothing to show" would be a dead end, so the empty state names the folders.
    """
    folders = ', '.join(f'models/loras/{BENCH_FOLDERS[f]}' for f in BENCH_FAMILIES)
    return (f'LoRA bench lists every .safetensors in {folders}. '
            'Drop the file you downloaded into the folder of the model family '
            'it was trained for, then reload this page.')


# --- Discovery ---------------------------------------------------------------
def list_bench_loras() -> list[dict]:
    """Every LoRA file the bench can test, across the three testable families.

    Deliberately UNFILTERED, unlike `permanent_lora_candidates` (which skips
    `lora_*` because a trained character LoRA is an axis, not an always-on): here
    a character LoRA is exactly what you came to judge, and a downloaded file can
    be named anything at all.

    Returns [{filename, label, family, family_label, folder}] — `filename` in
    LoraLoader form, which is also the identity the run is launched with.
    """
    out = []
    for fam in BENCH_FAMILIES:
        label = FAMILY_LABELS.get(fam, fam)
        for lora in lts._pool_for_family(fam):
            base = lts._basename(lora['filename'])
            out.append({
                'filename': lora['filename'],
                'label': lora.get('displayName') or base.rsplit('.', 1)[0],
                'name': base,
                'family': fam,
                'family_label': label,
                'folder': BENCH_FOLDERS[fam],
            })
    out.sort(key=lambda e: (e['family'], e['name'].lower()))
    return out


def resolve_bench_lora(filename) -> dict:
    """The pool entry for `filename`, or ValueError naming the eligible folders.

    Membership in the family pool IS the validation — the same list the picker
    renders, built by walking the loras roots. Nothing here joins user text onto
    a filesystem path, so the bench adds no path-injection surface: a name that
    is not already a file we listed simply does not resolve.
    """
    want = str(filename or '').strip()
    if not want:
        raise ValueError('pick a LoRA file first')
    for entry in list_bench_loras():
        if entry['filename'] == want:
            return entry
    fam = family_of_lora(want)
    if fam and fam not in BENCH_FAMILIES:
        raise ValueError(
            f'{FAMILY_LABELS.get(fam, fam)} LoRAs cannot be benched yet — the test '
            'engine only renders Z-Image, SDXL and Krea 2. '
            + bench_folder_hint())
    raise ValueError('that LoRA is not in a folder the bench reads. ' + bench_folder_hint())


# --- Trigger word ------------------------------------------------------------
def _tag_candidates(md) -> list[dict]:
    """Training tags by decreasing frequency, from kohya's `ss_tag_frequency`.

    The header stores {folder: {tag: count}}; counts are summed across folders.
    These are SUGGESTIONS shown as what they are — frequent tags — never an
    answer. A character LoRA's top tag is routinely `1girl`.
    """
    raw = md.get('ss_tag_frequency')
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return []
    if not isinstance(raw, dict):
        return []
    totals = {}
    for per_folder in raw.values():
        if not isinstance(per_folder, dict):
            continue
        for tag, count in per_folder.items():
            tag = str(tag).strip()
            if not tag:
                continue
            try:
                totals[tag] = totals.get(tag, 0) + int(count)
            except (TypeError, ValueError):
                continue
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{'tag': t, 'count': n} for t, n in ranked[:_MAX_TAG_CANDIDATES]]


def read_lora_trigger(filename) -> dict:
    """What the file itself says about its activation word.

    This is the pivot of the whole feature. The Studio builds its prompt from the
    trigger; test a subject LoRA without its activation token and every cell
    comes back looking unaffected — and the user concludes the LoRA is bad when
    it was simply never summoned. So:

      * `ss_output_name` (the name the file was trained under) prefills the field
        when it says something. It is usually, NOT always, the activation word —
        the UI says that, and the field stays editable;
      * when it does not, the field is left EMPTY and the caller is told so. Tags
        are offered as labelled suggestions, never as a prefill.

    Returns {trigger, source, candidates, arch, arch_label, readable}. `source` is
    'metadata' | None. Never raises for an unreadable file: an unreadable header
    is a "we don't know", which is exactly the empty case.
    """
    entry = resolve_bench_lora(filename)
    path = lts._resolve_lora_abs_path(entry['filename'])
    out = {'filename': entry['filename'], 'family': entry['family'],
           'family_label': entry['family_label'], 'label': entry['label'],
           'trigger': '', 'source': None, 'candidates': [], 'readable': False,
           'arch': None, 'arch_label': None}
    if not path or not os.path.isfile(path):
        return out
    try:
        md, _keys = lt._read_safetensors_header(path)
    except ValueError:
        return out
    out['readable'] = True
    name = str(md.get('ss_output_name') or '').strip()
    if name and name.lower() not in _GENERIC_OUTPUT_NAMES and not name.isdigit():
        out['trigger'] = name
        out['source'] = 'metadata'
    out['candidates'] = _tag_candidates(md)
    detected = lt.detect_lora_arch(path)
    if detected:
        out['arch'] = detected
        out['arch_label'] = lt._LORA_ARCH_LABEL.get(detected, detected)
    return out


# --- The scratch dataset -----------------------------------------------------
def get_bench_dataset(user_id):
    """The scratch row, or None. Never creates — read paths must stay read-only."""
    # lds-allow-internal-datasets: this IS the internal-row lookup.
    return (FaceDataset.query
            .filter_by(user_id=str(user_id), internal=fds.INTERNAL_BENCH)
            .order_by(FaceDataset.id.asc()).first())


def ensure_bench_dataset(user_id, trigger_word=''):
    """The scratch row, created on first use, with `trigger_word` applied.

    Created LAZILY and re-created if it is missing, because it legitimately can
    be: it is excluded from the full backup (bench history is test data, and
    shipping it would bloat every archive), so a restored install has no scratch
    row at all. The bench must come back on its own there — the alternative is a
    page that breaks weeks after a restore nobody remembers doing.

    Built row-by-hand rather than through `create_dataset`, which normalises kind
    / fidelity / suffixes and commits a *user's* dataset. This one is bookkeeping.
    """
    ds = get_bench_dataset(user_id)
    trigger = (trigger_word or '').strip()[:60]
    if ds is None:
        ds = FaceDataset(user_id=str(user_id), name=BENCH_DATASET_NAME,
                         trigger_word=trigger, internal=fds.INTERNAL_BENCH)
        db.session.add(ds)
        db.session.commit()
        logger.info('lora-bench: created the scratch dataset (id=%s)', ds.id)
        return ds
    if (ds.trigger_word or '') != trigger:
        # The scratch row carries the trigger of whichever LoRA is under test.
        ds.trigger_word = trigger
        db.session.commit()
    return ds


# --- Running -----------------------------------------------------------------
def _sweep(strengths) -> list[float]:
    """The strength axis: 1..8 distinct values, order preserved, validated by
    `build_matrix` afterwards (which owns the range rule for the whole engine)."""
    out = []
    for s in (strengths or []):
        try:
            v = round(float(s), 2)
        except (TypeError, ValueError):
            raise ValueError(f'invalid strength: {s!r}')
        if v not in out:
            out.append(v)
    if not out:
        out = list(DEFAULT_STRENGTHS)
    if len(out) > MAX_BENCH_STRENGTHS:
        raise ValueError(f'a bench sweep takes at most {MAX_BENCH_STRENGTHS} strengths')
    return out


def create_bench_run(user_id, filename, strengths=None, trigger=None, prompt=None,
                     seed=None, no_trigger=False) -> dict:
    """Launch the sweep. One LoRA × strengths, one prompt, one seed.

    `no_trigger=True` is the user's explicit statement that this LoRA has no
    activation word (a style/utility LoRA genuinely has none). It is required
    when `trigger` is empty: we neither guess a trigger nor block the launch —
    guessing produces a false verdict, blocking makes style LoRAs untestable.
    """
    entry = resolve_bench_lora(filename)
    trig = (trigger or '').strip()
    if not trig and not no_trigger:
        raise ValueError(
            'no activation word given. Enter the one from the page you downloaded '
            'this LoRA from, or tick "this LoRA has no activation word" — testing a '
            'subject LoRA without its trigger renders images it never affected, '
            'which reads as a bad LoRA.')
    sweep = _sweep(strengths)
    ds = ensure_bench_dataset(user_id, trig)
    text = (prompt or '').strip() or lts.identity_prompt(ds).strip(' ,')
    res = lts.create_run(
        user_id, ds.id, [entry['filename']], sweep,
        seed=seed, prompt=text, family=entry['family'], count=1,
        bench_lora=entry['filename'])
    return {**res, 'dataset_id': ds.id, 'family': entry['family'],
            'filename': entry['filename'], 'label': entry['label'],
            'trigger': trig, 'prompt': text, 'strengths': sweep}


# --- History -----------------------------------------------------------------
def bench_runs(user_id, limit=20) -> list[dict]:
    """Past bench runs, newest first: [{run_id, label, filename, strengths,
    prompt, seed, total, done, rated}]. Empty when the scratch row is gone."""
    ds = get_bench_dataset(user_id)
    if ds is None:
        return []
    rows = (lts._cells().filter_by(dataset_id=ds.id)
            .order_by(LoraTestImage.id.desc()).limit(600).all())
    runs = {}
    order = []
    for r in rows:
        key = r.run_id or f'row-{r.id}'
        if key not in runs:
            runs[key] = {'run_id': r.run_id, 'filename': r.checkpoint,
                         'label': lts._basename(r.checkpoint or '').rsplit('.', 1)[0],
                         'prompt': r.prompt, 'seed': r.run_seed,
                         'strengths': [], 'total': 0, 'done': 0, 'rated': 0}
            order.append(key)
        e = runs[key]
        e['total'] += 1
        if r.status == 'done':
            e['done'] += 1
        if r.rating:
            e['rated'] += 1
        if r.strength is not None and r.strength not in e['strengths']:
            e['strengths'].append(r.strength)
    for e in runs.values():
        e['strengths'].sort()
    return [runs[k] for k in order[:limit]]


def clear_bench_history(user_id) -> int:
    """Delete every bench cell (and its file), keeping the scratch ROW.

    Dropping the row instead would cascade the same cells away, but it would also
    walk straight into the boot-time orphan sweep
    (`app.__init__._cleanup_orphaned_lora_test_images`): any cell that outlived
    its parent — a run finishing while the row is gone, for instance — is deleted
    without a word at the next start. Keeping the row makes the deletion happen
    here, in one place, where it can be counted.
    """
    ds = get_bench_dataset(user_id)
    if ds is None:
        return 0
    rows = lts._cells().filter_by(dataset_id=ds.id).all()
    folder = fds._dataset_path(ds.id)
    n = 0
    for r in rows:
        if r.filename:
            try:
                os.remove(os.path.join(folder, r.filename))
            except OSError:
                pass
        db.session.delete(r)
        n += 1
    db.session.commit()
    return n


def _bench_run_payload(user_id, ds, run_id):
    """The run's cells — but only if it is a BENCH run.

    `?run=` is user input, and a dataset run's id is just as valid a string. The
    page would then render another dataset's grid scored against the bench's
    aggregates: two different runs shown as one. The Studio's own route stays the
    place to look at a Studio run.
    """
    if not run_id or ds is None:
        return None
    payload = lts.studio_payload_run(user_id, run_id)
    if not payload:
        return None
    if any(c.get('dataset_id') != ds.id for c in payload.get('cells') or []):
        return None
    return payload


def bench_payload(user_id, run_id=None) -> dict:
    """Everything the bench page needs, in ONE poll.

    `run_id` folds in the live cells of a run by delegating to the Studio's own
    `studio_payload_run` — the same payload the Studio polls, not a copy. The
    lifecycle ACTIONS (cancel, resume, ComfyUI restart confirmation) deliberately
    stay on `/api/studio/run/<id>/…`: reading through one door is convenience,
    writing through two would be the start of a second pipeline.

    `scores` is `cell_scores` over the scratch dataset. Because every bench run
    ever lives on that one row, it aggregates per (LoRA file, strength) ACROSS
    runs — which is exactly the bench's question: at what strength does THIS file
    win. Same Wilson lower bound and same <3-votes low-confidence flag as the
    Studio; the page filters it down to the file on screen.
    """
    ds = get_bench_dataset(user_id)
    return {
        'run': _bench_run_payload(user_id, ds, run_id),
        'scores': lts.cell_scores(ds.id) if ds else [],
        'loras': list_bench_loras(),
        'families': [{'family': f, 'label': FAMILY_LABELS.get(f, f),
                      'folder': BENCH_FOLDERS[f]} for f in BENCH_FAMILIES],
        'folder_hint': bench_folder_hint(),
        'default_strengths': list(DEFAULT_STRENGTHS),
        'max_strengths': MAX_BENCH_STRENGTHS,
        # Null until the first launch: the page only needs it to build image
        # URLs, and there are no images before the scratch row exists.
        'dataset_id': ds.id if ds else None,
        'runs': bench_runs(user_id),
        'gpu_busy': lts.gpu_busy_reason(),
    }
