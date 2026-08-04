"""Model-file integrity: is a weights file on disk a REAL, loadable model, or just
a file that happens to have the right name and extension?

Two real incidents motivate this — both passed a plain "the file exists" check,
went green in Setup, then failed cryptically far downstream:

  1. A licence-gated model downloaded from a browser WITHOUT accepting the licence
     (or without an HF token) saves the HTML gate PAGE to ``<name>.safetensors``.
     ComfyUI's UNETLoader then dies at generation time on
     ``Expecting value: line 1 column 1 (char 0)`` — ``json.loads`` choking on
     ``<!doctype html>…`` — long after the Setup step reported the model present.
  2. A partial download or a broken Stability-Matrix symlink leaves a truncated /
     empty ``<name>.safetensors``. ComfyUI loads garbage and renders SILENTLY
     distorted images with no error anywhere (the kostas212 report).

This validates only the file HEADER, never the multi-GB weight body, so it is
cheap enough (~ms) to run from the probes / preflights that already fire at the
right moments. Layout of the containers we accept:

  * ``.safetensors`` / ``.sft``: an 8-byte little-endian header length ``N``,
    then ``N`` bytes of a JSON object (the tensor index). We read the 8 bytes,
    sanity-check ``N``, confirm the file is at least ``8 + N`` long, and parse the
    JSON object (bounded — a real header is well under a megabyte; anything past
    the parse budget is accepted structurally without reading it whole).
  * ``.gguf``: the 4-byte magic ``GGUF``. ComfyUI-GGUF quantised models are common
    in this community and the app already lists ``.gguf`` alongside safetensors.

Verdicts (see the constants): ``valid`` / ``html_or_text`` (a saved HTML gate
page, a Git-LFS pointer, a JSON error body — the gate case) / ``truncated_or_garbage``
(implausible header length, unparsable header, or a file shorter than its declared
header) / ``too_small`` (structurally valid but far below a plausible floor for its
type — advisory only, never blocking) / ``missing`` (not on disk — the missing-asset
preflights own that case, this validator does not block on it).

The structural verdict is a pure function of the file bytes; a deployed model never
mutates in place. It is cached by ``(abspath, mtime_ns, size)`` so repeated probe /
preflight passes read each header at most once. The ``too_small`` floor is applied
AFTER the cache (a cheap size compare) so the same file can be judged against
different floors without a re-read."""
from __future__ import annotations

import json
import logging
import os
import struct
import threading

logger = logging.getLogger(__name__)

# Verdict codes -------------------------------------------------------------
VALID = 'valid'
HTML_OR_TEXT = 'html_or_text'
TRUNCATED_OR_GARBAGE = 'truncated_or_garbage'
TOO_SMALL = 'too_small'
MISSING = 'missing'

# A real safetensors header is well under ~10 MB; past this the 8 leading bytes
# are not a header length at all (an HTML/text/garbage file read as a uint64).
_HEADER_LEN_MAX = 100 * 1024 * 1024
# Parse the JSON header in full up to here; a larger (but structurally plausible)
# header is accepted without reading it whole — the point is never to read the GB
# of weight tensors that follow, not to fully parse a pathologically large index.
_HEADER_PARSE_BUDGET = 8 * 1024 * 1024
# One cheap upfront read that covers the GGUF magic (4 B), the safetensors length
# (8 B) and enough of the header start to sniff a text/HTML/LFS signature.
_INITIAL_READ = 512

_MAGIC_GGUF = b'GGUF'

# Test seam: the module opens files through this name so a test can wrap it and
# assert the whole (multi-GB) file is never read — only the header.
_open = open

_lock = threading.Lock()
_cache: dict = {}   # (abspath, mtime_ns, size) -> (verdict_code, reason_or_None)
_quant_cache: dict = {}   # same key -> quantization_report() payload


def clear_cache() -> None:
    """Drop the structural-verdict and quantization caches (test hygiene;
    production self-invalidates on the (path, mtime, size) key)."""
    with _lock:
        _cache.clear()
        _quant_cache.clear()


def _human_size(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024 or unit == 'TB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n / 1024:.1f} {unit}'.replace('.0 ', ' ')
        n /= 1024
    return f'{n:.0f} B'


def _looks_textual(head: bytes):
    """A short flavour string if ``head`` looks like text / markup rather than a
    binary model header, else None. Covers the licence-gate HTML page, a Git-LFS
    pointer (repo cloned without LFS), and a JSON error body."""
    s = head.lstrip()
    if not s:
        return None
    low = s[:64].lower()
    if low.startswith(b'version https://git-lfs'):
        return 'lfs'
    if s[:1] == b'<':                    # <!doctype html>, <html>, <?xml, <!--
        return 'html'
    if s[:1] == b'{' and b'error' in s[:400].lower():
        return 'json_error'
    return None


# Reason sentences — the actionable message a user actually needs. `name` is the
# bare filename (no path — these bubble up to a paste-safe diagnostic and to the UI).
def _reason_text(name: str, flavour: str) -> str:
    if flavour == 'lfs':
        return (f"{name} is a Git LFS pointer, not the real weights — the repo was "
                f"cloned without Git LFS. Delete it and download the actual file "
                f"(or run 'git lfs pull').")
    if flavour == 'json_error':
        return (f"{name} is not a real model file — it looks like a JSON error "
                f"response, not model weights. Delete it and re-download.")
    return (f"{name} is not a real model (looks like an HTML page — a licence-gated "
            f"download saved without accepting the licence / without a token?). "
            f"Delete it and re-download the real weights.")


def _reason_garbage(name: str) -> str:
    return (f"{name} is not a valid model file — its header is unreadable "
            f"(a truncated or corrupted download?). Delete it and re-download.")


def _reason_truncated(name: str) -> str:
    return (f"{name} is incomplete — the file is shorter than its own header says "
            f"(a partial / interrupted download?). Delete it and re-download.")


def _reason_too_small(name: str, size: int) -> str:
    return (f"{name} is only {_human_size(size)} — far smaller than a real model file "
            f"(a partial download or broken symlink?). It may be incomplete; "
            f"re-download it if generation looks wrong.")


def _structural(path: str, size: int):
    """(verdict_code, reason_or_None) from the file HEADER only. One of VALID /
    HTML_OR_TEXT / TRUNCATED_OR_GARBAGE. Never raises; never reads the weight body."""
    name = os.path.basename(path)
    try:
        with _open(path, 'rb') as fh:
            head = fh.read(_INITIAL_READ)
            if len(head) < 8:
                # Not even room for a length prefix — an empty stub or a broken symlink.
                flavour = _looks_textual(head)
                return ((HTML_OR_TEXT, _reason_text(name, flavour)) if flavour
                        else (TRUNCATED_OR_GARBAGE, _reason_garbage(name)))
            if head[:4] == _MAGIC_GGUF:
                return VALID, None
            n = struct.unpack('<Q', head[:8])[0]
            if n <= 0 or n > _HEADER_LEN_MAX:
                # The 8 leading bytes aren't a plausible header length → this is not
                # a safetensors. Is it a recognisable text/HTML/LFS file (the gate case)?
                flavour = _looks_textual(head)
                return ((HTML_OR_TEXT, _reason_text(name, flavour)) if flavour
                        else (TRUNCATED_OR_GARBAGE, _reason_garbage(name)))
            if size < 8 + n:
                # Declared header doesn't fit in the file → truncated download.
                return TRUNCATED_OR_GARBAGE, _reason_truncated(name)
            want = min(n, _HEADER_PARSE_BUDGET)
            body = head[8:8 + want]
            if len(body) < want:
                body += fh.read(want - len(body))
            if body.lstrip()[:1] != b'{':
                # Plausible-looking length but the header isn't a JSON object.
                flavour = _looks_textual(head)
                return ((HTML_OR_TEXT, _reason_text(name, flavour)) if flavour
                        else (TRUNCATED_OR_GARBAGE, _reason_garbage(name)))
            if n > _HEADER_PARSE_BUDGET:
                # Structurally a JSON object of a plausible declared size, too large to
                # parse whole cheaply — accept it rather than read megabytes of index.
                return VALID, None
            try:
                obj = json.loads(body[:n].decode('utf-8'))
            except (ValueError, UnicodeDecodeError):
                return TRUNCATED_OR_GARBAGE, _reason_garbage(name)
            if not isinstance(obj, dict):
                return TRUNCATED_OR_GARBAGE, _reason_garbage(name)
            return VALID, None
    except OSError:
        return TRUNCATED_OR_GARBAGE, _reason_garbage(name)


# --- pre-quantized inference exports ------------------------------------------
# A second question the same header answers: is this file an INFERENCE-ONLY
# quantized export? Community fp8/int8 repacks of a base model (~10 GB instead of
# ~26 GB) are what people download to generate with. The signals below are all
# header-level, so the check costs the same few KB as the integrity one.
#
# "Quantized" hides TWO different files, and only one of them is a wall. What
# decides is the FORMAT — the set of tensor NAMES — never the bit width:
#
#   * a STRUCTURED export (ComfyUI's scaled fp8 and its modern `comfy_quant`
#     form, every int8 repack, this app's own fp8 export) carries its
#     dequantization tables as EXTRA TENSORS: a top-level `scaled_fp8` marker,
#     a `<layer>.scale_weight` / `.weight_scale` / `.comfy_quant` sibling per
#     quantized matrix. A trainer loads a base with
#     ``load_state_dict(state_dict, strict=True)``, so those unknown keys make
#     the LOAD fail — immediately, before a step runs, not "deep in the first
#     optimizer step". Verified against the installed ai-toolkit Krea 2 loader
#     (``extensions_built_in/diffusion_models/krea2``), which casts the state
#     dict and then loads it strictly.
#   * a BARE cast stores the payload as float8/int8 under the tensor names the
#     full-precision file already had, adding nothing. There is no unknown key
#     for the strict load to trip on, and the loader's cast step up-casts every
#     floating-point tensor to the training dtype. Measured on a real Krea 2
#     Turbo fp8 build: 266 F8_E4M3 out of 432 tensors, no marker, no scale
#     sibling, and 430 of its keys are the bf16 checkpoint's own keys with only
#     the dtype changed on 264 of them.
#
# Same conclusion outside this repo: musubi-tuner trains from an `fp8_e4m3fn`
# base (``--fp8_base`` without ``--fp8_scaled``) and documents that a scaled fp8
# checkpoint cannot be re-used by a trainer without converting it back.
#
# So the refusal is scoped to the structured form. The bare form is ALLOWED and
# WARNED about, with numbers (see `base_precision_warning`): the precision the
# cast dropped never comes back, and that is a cost to state, not a reason to
# forbid.
#
# SCOPE, stated because it was overclaimed once: this answers "is the file
# packed?", not "will this architecture accept these tensors?". The same measured
# Turbo conversion carries two extra 6144x6144 tensors under weight-shaped names
# (`last.down.weight`, `last.up.weight`) which its OWN metadata describes as an
# embedded image, not weights; ai-toolkit's Krea 2 final layer (norm / linear /
# modulation) declares nothing of the sort, so a strict load rejects them for a
# reason that has nothing to do with quantization. Nothing here can decide that:
# it would mean modelling every architecture's key set. The messages therefore
# say what was checked (the packing) and never promise that the run will start.

# Decisive marker keys — the STRUCTURED form. `_quantization_metadata` (ComfyUI's
# modern per-layer JSON) and `.comfy_quant` (its tensor form) exist for no other
# reason; `scaled_fp8` is the legacy marker; a `.scale_weight` / `.weight_scale`
# sibling is the per-tensor dequantization scale. Any ONE of them is proof, and
# every one of them is a KEY the trainer's strict load does not know.
_QUANT_METADATA_KEY = '_quantization_metadata'
_QUANT_MARKER_KEYS = ('scaled_fp8',)
_QUANT_KEY_SUFFIXES = ('.comfy_quant', '.scale_weight', '.weight_scale',
                       '.input_scale', '.scale_input')

# Quantized payload dtypes vs the dtypes a trainable checkpoint is stored in.
_QUANT_DTYPES = ('F8_E4M3', 'F8_E5M2', 'F8_E4M3FN', 'I8', 'U8', 'F4', 'I4')
_TRAINABLE_DTYPES = ('BF16', 'F16', 'F32', 'F64')

# The `form` values of a quantization report. '' = not quantized at all (or the
# header could not be read, which is reported separately by `checked`).
FORM_STRUCTURED = 'structured'
FORM_BARE_CAST = 'bare_cast'

# Significand bits, implicit leading bit included — how much of each weight
# survived the cast. Only used to put a NUMBER on the warning; a dtype absent
# from this table simply loses that half of the sentence.
_SIGNIFICAND_BITS = {'BF16': 8, 'F16': 11, 'F32': 24,
                     'F8_E4M3': 4, 'F8_E4M3FN': 4, 'F8_E5M2': 3, 'F4': 2}

QUANT_REFUSAL = (
    'This is a packed inference export: it stores its dequantization tables as '
    'extra tensors (scaled_fp8 / .scale_weight / .comfy_quant) that a trainer '
    'cannot load, so the load fails before the first step — the format is the '
    'obstacle, not the file size. Training needs the bf16/fp16 version of this '
    'model: a full-model run keeps that master next to its fp8 twin, and the '
    'Checkpoints panel lists it by name.')


def _header_index(path: str):
    """(``__metadata__`` dict, {tensor name: dtype}) — header ONLY, or None when
    the file is not a parsable safetensors container (a .gguf, an HTML gate page,
    a header past the parse budget). None means "cannot tell", never "clean"."""
    try:
        with _open(path, 'rb') as fh:
            head = fh.read(_INITIAL_READ)
            if len(head) < 8 or head[:4] == _MAGIC_GGUF:
                return None
            n = struct.unpack('<Q', head[:8])[0]
            if n <= 0 or n > _HEADER_PARSE_BUDGET:
                return None
            body = head[8:8 + n]
            if len(body) < n:
                body += fh.read(n - len(body))
            if len(body) < n:
                return None
            obj = json.loads(body[:n].decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    meta = obj.get('__metadata__')
    index = {k: str((v or {}).get('dtype') or '').upper()
             for k, v in obj.items()
             if k != '__metadata__' and isinstance(v, dict)}
    return (meta if isinstance(meta, dict) else {}), index


def quantization_report(path) -> dict:
    """``{quantized, form, trainable_as_base, signals, dtype_counts, checked}``
    for one weights file.

    ``quantized`` stays the broad "this file is not full precision" answer — it
    is what the fp8 exporter reads to refuse quantizing something twice.
    ``form`` and ``trainable_as_base`` are the training question, which is a
    different one: ``FORM_STRUCTURED`` carries loader-breaking extra keys and is
    NOT trainable, ``FORM_BARE_CAST`` is a plain low-precision payload the
    trainer up-casts, so it IS trainable (degraded — see
    `base_precision_warning`). See the block comment above for the measurements.

    ``checked=False`` means the header could not be read as a tensor index — the
    caller must treat that as "unknown" and let the file through: refusing a base
    nobody could inspect would be worse than the failure it prevents.

    Cached on (abspath, mtime_ns, size) like the structural verdict: a deployed
    model never mutates in place, and the training-base picker asks this of every
    listed checkpoint each time the panel opens.
    """
    key = None
    try:
        st = os.stat(str(path))
        key = (os.path.abspath(str(path)), st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    if key is not None:
        with _lock:
            hit = _quant_cache.get(key)
        if hit is not None:
            return _copy_report(hit)
    out = _quantization_report_uncached(path)
    if key is not None:
        with _lock:
            _quant_cache[key] = out
    return _copy_report(out)


def _copy_report(report: dict) -> dict:
    """A caller-owned copy: the report is cached, and its list/dict members would
    otherwise be shared with whoever mutated the previous one."""
    return {**report, 'signals': list(report['signals']),
            'dtype_counts': dict(report['dtype_counts'])}


def _quantization_report_uncached(path) -> dict:
    out = {'quantized': False, 'form': '', 'trainable_as_base': True,
           'signals': [], 'dtype_counts': {},
           'checked': False, 'filename': os.path.basename(str(path))}
    parsed = _header_index(str(path))
    if parsed is None:
        return out
    meta, index = parsed
    out['checked'] = True
    signals = out['signals']
    if _QUANT_METADATA_KEY in meta:
        signals.append(_QUANT_METADATA_KEY)
    for name in index:
        if name in _QUANT_MARKER_KEYS:
            signals.append(name)
        elif name.endswith(_QUANT_KEY_SUFFIXES):
            suffix = '.' + name.rsplit('.', 1)[-1]
            if suffix not in signals:
                signals.append(suffix)
    # Every signal collected so far is an EXTRA KEY (or the metadata that
    # announces them): that, and only that, is what a strict state-dict load
    # cannot survive.
    structured = bool(signals)
    counts = {}
    for dtype in index.values():
        counts[dtype] = counts.get(dtype, 0) + 1
    out['dtype_counts'] = counts
    quant_tensors = sum(counts.get(d, 0) for d in _QUANT_DTYPES)
    trainable_tensors = sum(counts.get(d, 0) for d in _TRAINABLE_DTYPES)
    # "Majority" is deliberately a strict comparison against the trainable
    # dtypes, not a fraction of ALL tensors: a scaled export is roughly half
    # fp8 payload and half F32 scales, so a ratio over the total would sit just
    # under any threshold worth setting.
    if quant_tensors and quant_tensors > trainable_tensors:
        signals.append('majority_quantized_dtypes')
    out['quantized'] = bool(signals)
    if structured:
        out['form'] = FORM_STRUCTURED
        out['trainable_as_base'] = False
    elif out['quantized']:
        out['form'] = FORM_BARE_CAST
    return out


def base_precision_warning(report) -> str | None:
    """The quantified caution for a base that trains but starts degraded, or None.

    Returned for the BARE form only: a structured export is refused outright, and
    a bf16/fp16 file has nothing to warn about. It is deliberately a COUNT and a
    bit width rather than an adjective — "266 of 432 tensors, 4 significand bits
    against bf16's 8" is checkable against the file; "lower quality" is not.
    """
    if not report or report.get('form') != FORM_BARE_CAST:
        return None
    counts = report.get('dtype_counts') or {}
    total = sum(counts.values())
    quantized = {d: n for d, n in counts.items() if d in _QUANT_DTYPES}
    n_quant = sum(quantized.values())
    if not total or not n_quant:
        return None
    dominant = max(quantized, key=lambda d: quantized[d])
    share = round(100 * n_quant / total)
    bits = _SIGNIFICAND_BITS.get(dominant)
    precision = f", {bits} significand bits per weight against bf16's 8" if bits else ''
    name = report.get('filename') or 'This file'
    return (f'{name} is a quantized cast: {n_quant} of its {total} tensors '
            f'({share}%) are stored as {dominant}{precision}. This kind of file '
            'is trainable — the trainer up-casts it as it loads, and it carries '
            'none of the decompression tensors that make a packed export '
            'unloadable — but the precision the cast dropped never comes back, '
            'so the run starts from an already-degraded base. Train on it if '
            'that is the file you have; the bf16/fp16 version of the same model '
            'gives a better LoRA for the same GPU time. (This check reads the '
            'packing, not the architecture: a checkpoint can still be refused '
            'at load for carrying tensors this model family does not have.)')


def training_base_advisory(path) -> dict:
    """``{trainable, level, note, form}`` for a weights file offered as a base.

    One place decides, so the picker's badge, the selection refusal and the
    pre-launch guard can never drift apart: ``level`` is ``'error'`` (refused,
    ``note`` is `QUANT_REFUSAL`), ``'warning'`` (allowed, ``note`` is the
    quantified caution) or ``''`` (nothing to say)."""
    report = quantization_report(path)
    if not report.get('trainable_as_base', True):
        return {'trainable': False, 'level': 'error', 'note': QUANT_REFUSAL,
                'form': report.get('form') or ''}
    note = base_precision_warning(report)
    return {'trainable': True, 'level': 'warning' if note else '', 'note': note,
            'form': report.get('form') or ''}


def _cached_structural(path: str, st: os.stat_result):
    key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    with _lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit
    res = _structural(path, st.st_size)
    with _lock:
        _cache[key] = res
    return res


def _result(verdict: str, path: str, size: int, reason) -> dict:
    return {
        'verdict': verdict,
        'ok': verdict == VALID,
        # Only html_or_text and truncated_or_garbage BLOCK — they mean the file
        # can't be loaded at all. too_small is advisory; missing is the other
        # preflight's job.
        'blocking': verdict in (HTML_OR_TEXT, TRUNCATED_OR_GARBAGE),
        'reason': reason,
        'filename': os.path.basename(path),
        'size': size,
    }


def validate_model_file(path, min_bytes=None) -> dict:
    """Header-only integrity verdict for a single model file. Returns a dict:
    ``{verdict, ok, blocking, reason, filename, size}`` (JSON-safe, so it drops
    straight into the capabilities payload / diagnostic).

    ``min_bytes`` — an optional lower bound for this file's TYPE. A structurally
    valid file below it is downgraded to ``too_small`` (advisory, ``blocking``
    False): a real model is orders of magnitude larger, so this catches a partial
    download / broken symlink that still happens to carry a complete small header.
    Absent ``min_bytes`` never yields ``too_small``.

    Never raises. ``valid``/``too_small`` mean "load will work" / "load will work
    but the file is suspiciously small"; ``blocking`` verdicts must stop the run
    with ``reason`` shown to the user."""
    try:
        st = os.stat(path)
    except OSError:
        name = os.path.basename(str(path))
        return _result(MISSING, str(path), 0, f'{name} is not on disk.')
    size = st.st_size
    verdict, reason = _cached_structural(str(path), st)
    if verdict == VALID and min_bytes and size < min_bytes:
        return _result(TOO_SMALL, str(path), size, _reason_too_small(os.path.basename(str(path)), size))
    return _result(verdict, str(path), size, reason)
