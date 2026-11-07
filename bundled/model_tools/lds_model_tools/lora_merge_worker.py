"""Streaming tensor merge worker; the host imports only the shared header contract.

Runs in the configured Torch interpreter. The JSON-file input and progress/result
lines, float32 accumulation, tensor-by-tensor memory bound, atomic .part write
and verification remain the product's existing merge protocol.
"""
from __future__ import annotations
import json
import os
import struct
import sys
import time

# Resolve our explicitly owned sibling, then restore the isolated import path
# before any dependency import. Keeping this directory on sys.path would let a
# local torch.py shadow the selected interpreter's Torch.
_import_path = list(sys.path)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from lora_merge import (  # noqa: E402 — explicitly shared stdlib-only helper
        MergeError, _DTYPE_BYTES, _HEADER_LEN_MAX, _shape_of,
        tensor_entries, read_header, plan_merge, tensor_bytes, lora_modules,
        module_scale, weight_for, PROGRESS_PREFIX, RESULT_PREFIX,
    )
finally:
    sys.path[:] = _import_path


def torch_dtypes() -> dict:
    """safetensors dtype spelling -> torch dtype.

    A function, not a module constant: importing torch at module scope would
    make this file un-importable on the app's own environment, which is the
    whole reason the merge runs in a subprocess.
    """
    import torch
    return {
        'BF16': torch.bfloat16, 'F16': torch.float16, 'F32': torch.float32,
        'F64': torch.float64, 'F8_E4M3': torch.float8_e4m3fn,
        'F8_E5M2': torch.float8_e5m2, 'I64': torch.int64, 'I32': torch.int32,
        'I16': torch.int16, 'I8': torch.int8, 'U8': torch.uint8,
        'BOOL': torch.bool,
    }


class Reader:
    """One tensor at a time out of a .safetensors, by ordinary file I/O.

    DELIBERATELY NOT ``safetensors.safe_open``. That memory-maps the whole
    container, and on Windows a 26 GB mapping is charged against the pagefile the
    moment it is created — so opening the real Krea 2 base fails outright with
    ``OSError 1455`` ("the paging file is too small for this operation") on a
    machine with plenty of free RAM and 246 GB of free disk. Measured here, on
    the real file: the first end-to-end merge died on that line before reading a
    single tensor.

    A merge is a strictly sequential pass — read tensor, transform, write, drop —
    so a mapping buys nothing anyway. Seeking to the offset the header already
    gives us has the same peak memory (one tensor), no address-space cost, and no
    dependency on how the user happens to have configured their pagefile. The
    offsets are relative to the end of the header, which is where the data
    section starts.
    """

    def __init__(self, path):
        self.path = str(path)
        self._fh = open(self.path, 'rb')
        try:
            raw = self._fh.read(8)
            if len(raw) != 8:
                raise ValueError('file too short to be a safetensors container')
            n = struct.unpack('<Q', raw)[0]
            if n <= 0 or n > _HEADER_LEN_MAX:
                raise ValueError('implausible safetensors header length')
            self.header = json.loads(self._fh.read(n).decode('utf-8'))
        except Exception as e:
            self._fh.close()
            raise MergeError(f'not a readable .safetensors file ({e})') from e
        self._start = 8 + n
        self.entries = tensor_entries(self.header)

    def keys(self):
        return list(self.entries)

    def get_tensor(self, name):
        import torch
        spec = self.entries.get(name)
        if spec is None:
            raise MergeError(f'{name} is not in {os.path.basename(self.path)}')
        dtype = torch_dtypes().get(str(spec.get('dtype') or '').upper())
        if dtype is None:
            raise MergeError(f'unsupported dtype {spec.get("dtype")!r} on {name}')
        begin, end = int(spec['data_offsets'][0]), int(spec['data_offsets'][1])
        nbytes = end - begin
        self._fh.seek(self._start + begin)
        # readinto a bytearray, not `bytes(fh.read(...))`: torch.frombuffer warns
        # (once per tensor, so hundreds of times) about a read-only buffer, and
        # converting after the fact would hold two copies of a 200 MB tensor at
        # the peak for no reason.
        raw = bytearray(nbytes)
        got = self._fh.readinto(raw)
        if got != nbytes:
            raise MergeError(
                f'{os.path.basename(self.path)} is truncated: {name} claims '
                f'{nbytes} bytes and only {got} are there.')
        return torch.frombuffer(raw, dtype=dtype).reshape(_shape_of(spec))

    def close(self):
        try:
            self._fh.close()
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
        return False


def _raw_bytes(tensor) -> bytes:
    """Contiguous little-endian payload of any tensor, bf16 and fp8 included.

    ``numpy()`` has neither float8 nor bfloat16, so those buffers are
    reinterpreted through an integer view of the SAME itemsize: exact bytes, no
    conversion of the values.
    """
    import torch
    flat = tensor.detach().to('cpu').contiguous().reshape(-1)
    view = {torch.float8_e4m3fn: torch.uint8, torch.float8_e5m2: torch.uint8,
            torch.bfloat16: torch.int16}.get(flat.dtype)
    if view is not None:
        flat = flat.view(view)
    return flat.numpy().tobytes()


def _pack_header(index: dict, metadata: dict | None) -> bytes:
    obj = dict(index)
    if metadata:
        obj['__metadata__'] = {str(k): str(v) for k, v in metadata.items()}
    blob = json.dumps(obj, separators=(',', ':')).encode('utf-8')
    blob += b' ' * ((-len(blob)) % 8)          # keep the data section 8-byte aligned
    return struct.pack('<Q', len(blob)) + blob


def merge_delta(base_tensor, a_tensor, b_tensor, *, weight, scale):
    """``W + weight * scale * (B @ A)``, accumulated in float32.

    Returns a tensor in the BASE's dtype. float32 throughout is the whole point:
    a bf16 accumulator has ~8 bits of mantissa, and a delta two orders of
    magnitude below the weight it corrects would round away to nothing —
    silently, and worse with every LoRA stacked on top.
    """
    import torch
    work = base_tensor.detach().to(torch.float32)
    delta = torch.matmul(b_tensor.detach().to(torch.float32),
                         a_tensor.detach().to(torch.float32))
    if tuple(delta.shape) != tuple(work.shape):   # guarded in plan_merge; belt and braces
        raise MergeError(
            f'internal shape mismatch: delta {tuple(delta.shape)} vs weight '
            f'{tuple(work.shape)}')
    work += float(weight) * float(scale) * delta
    return work.to(base_tensor.dtype)


def merge_into_base(base_path, dst_path, loras, *, metadata=None, family=None,
                    progress=None, budget_seconds=None, _now=time.monotonic) -> dict:
    """Write ``base_path`` with ``loras`` folded in, to ``dst_path``.

    ``loras`` is a list of ``{'path': str, 'weight': float}`` (optionally
    ``'key_weights'``). Streaming: the output header is computed from the source
    header (identical keys/shapes/dtypes), then each tensor is read, updated if
    any LoRA targets it, and appended once.

    Writes to ``<dst>.part`` and renames only on success, so a merge that dies
    half way — out of disk, killed, power cut — leaves no truncated checkpoint
    that looks loadable, and never touches the base.
    """
    base_header = read_header(base_path)
    lora_headers = [(os.path.basename(str(item['path'])), read_header(item['path']))
                    for item in loras]
    plan = plan_merge(base_header, lora_headers, family=family)
    entries = tensor_entries(base_header)
    targets = plan['targets']

    order = sorted(entries)
    index, offset = {}, 0
    for name in order:
        spec = entries[name]
        dtype = str(spec.get('dtype') or '').upper()
        if dtype not in _DTYPE_BYTES:
            raise MergeError(f'unsupported dtype {dtype!r} on {name}')
        nbytes = tensor_bytes(spec)
        index[name] = {'dtype': dtype, 'shape': _shape_of(spec),
                       'data_offsets': [offset, offset + nbytes]}
        offset += nbytes

    out_meta = {k: v for k, v in (base_header.get('__metadata__') or {}).items()
                if isinstance(k, str)}
    # Merging ONTO a merged model is a route we actively suggest (the refusal for
    # too many LoRAs says "merge in two rounds", and the output of one merge is a
    # valid base for the next). Without this, the second merge's metadata would
    # overwrite the first one's and the file would claim a lineage one step deep
    # while being two — the precise failure this metadata exists to prevent.
    prior = {k: out_meta[k] for k in ('lds_merge_base', 'lds_merge_loras',
                                      'lds_merge_date') if k in out_meta}
    if prior:
        out_meta['lds_merge_previous'] = json.dumps(prior, separators=(',', ':'))
    out_meta.update({str(k): str(v) for k, v in (metadata or {}).items()})

    # Per-LoRA module maps, resolved once (header maths, no weights).
    module_maps = [lora_modules(header) for _label, header in lora_headers]

    started = _now()
    tmp = str(dst_path) + '.part'
    merged_count = 0
    readers = []
    try:
        try:
            for item in loras:
                readers.append(Reader(item['path']))
            with Reader(base_path) as base_reader, open(tmp, 'wb') as out:
                out.write(_pack_header(index, out_meta))
                for done, name in enumerate(order, start=1):
                    if budget_seconds and (_now() - started) > budget_seconds:
                        raise MergeError(
                            f'the merge exceeded its {int(budget_seconds)}s budget '
                            f'after {done}/{len(order)} tensors')
                    tensor = base_reader.get_tensor(name)
                    for lora_index in targets.get(name, []):
                        slot = module_maps[lora_index][name]
                        reader = readers[lora_index]
                        a_tensor = reader.get_tensor(slot['A_key'])
                        b_tensor = reader.get_tensor(slot['B_key'])
                        alpha = None
                        if slot['alpha_key']:
                            alpha = float(reader.get_tensor(slot['alpha_key']).item())
                        tensor = merge_delta(
                            tensor, a_tensor, b_tensor,
                            weight=weight_for(loras[lora_index], name),
                            scale=module_scale(a_tensor.shape[0], alpha))
                        del a_tensor, b_tensor
                    if name in targets:
                        merged_count += 1
                    out.write(_raw_bytes(tensor))
                    del tensor
                    if progress:
                        try:
                            progress(done, len(order))
                        except Exception:      # noqa: BLE001 — never fatal
                            progress = None
        finally:
            for reader in readers:
                reader.close()
        os.replace(tmp, dst_path)
    except MergeError:
        _unlink(tmp)
        raise
    except Exception as e:                     # noqa: BLE001
        _unlink(tmp)
        raise MergeError(f'the merge failed: {e}') from e
    return {'path': str(dst_path), 'tensors': len(order),
            'merged_tensors': merged_count,
            'carried_over': len(plan['carried_over']),
            'loras': [{'name': os.path.basename(str(i['path'])),
                       'weight': float(i.get('weight') or 0)} for i in loras],
            'bytes_after': os.path.getsize(dst_path),
            'seconds': round(_now() - started, 1)}


def _unlink(path):
    try:
        os.remove(path)
    except OSError:
        pass


def verify_merge(path, base_path) -> dict:
    """Re-open what we just wrote and prove it is still the model it claims to be.

    A merge that produced an unloadable file must say so HERE, not at generation
    time days later. Checks the key set and every shape against the base, that
    the traceability metadata survived, and that a real weight reads back finite
    — a NaN from a pathological LoRA would otherwise only show up as black images.
    """
    out = {'verified': False, 'verify_error': None}
    try:
        header = read_header(path)
        produced = tensor_entries(header)
        expected = tensor_entries(read_header(base_path))
        if set(produced) != set(expected):
            missing = sorted(set(expected) - set(produced))[:3]
            extra = sorted(set(produced) - set(expected))[:3]
            raise ValueError(f'the key set changed (missing {missing}, extra {extra})')
        for name, spec in produced.items():
            if _shape_of(spec) != _shape_of(expected[name]):
                raise ValueError(f'{name} changed shape')
            if str(spec.get('dtype')) != str(expected[name].get('dtype')):
                raise ValueError(f'{name} changed dtype')
        if not (header.get('__metadata__') or {}).get('lds_merge'):
            raise ValueError('the merge metadata was not written')
        import torch
        with Reader(path) as fh:
            probe = next((k for k in sorted(fh.keys()) if k.endswith('.weight')), None)
            if probe is None:
                raise ValueError('no weight tensor in the output')
            sample = fh.get_tensor(probe)
        if not bool(torch.isfinite(sample.to(torch.float32)).all().item()):
            raise ValueError(f'{probe} contains NaN or infinity after the merge')
        # NOT 'tensors': the CLI merges this dict into the writer's summary, which
        # already reports a tensor count. Two keys of the same name there is a
        # TypeError that surfaces as "the merge failed" AFTER a 26 GB write has
        # succeeded — the worst possible place to lose a result.
        out.update(verified=True, verified_tensors=len(produced))
    except Exception as e:                     # noqa: BLE001 — reported, not raised
        out['verify_error'] = str(e)[:300]
    return out


def main(argv=None) -> int:
    """Worker entry point. Reads a JSON spec file, prints one result line.

    The spec arrives in a FILE rather than as arguments: a command line is
    visible to every process on the machine and the paths involved are the
    user's own folders. It also sidesteps quoting a Windows path through a
    subprocess argument list, which is where this kind of worker usually breaks.
    """
    import argparse
    parser = argparse.ArgumentParser(prog='lds-lora-merge')
    parser.add_argument('--spec', required=True)
    parser.add_argument('--progress', action='store_true')
    parser.add_argument('--budget-seconds', type=int, default=0)
    args = parser.parse_args(argv)

    result = {'ok': False, 'error': None, 'path': None}
    try:
        with open(args.spec, encoding='utf-8') as fh:
            spec = json.load(fh)

        def report(done, total):
            print(f'{PROGRESS_PREFIX} {done} {total}', flush=True)

        summary = merge_into_base(
            spec['base'], spec['destination'], spec['loras'],
            metadata=spec.get('metadata'), family=spec.get('family'),
            budget_seconds=args.budget_seconds or None,
            progress=report if args.progress else None)
        result.update(ok=True, **summary,
                      **verify_merge(spec['destination'], spec['base']))
    except Exception as e:                     # noqa: BLE001 — reported, not raised
        result['error'] = str(e)[:500]
    print(RESULT_PREFIX + ' ' + json.dumps(result))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
