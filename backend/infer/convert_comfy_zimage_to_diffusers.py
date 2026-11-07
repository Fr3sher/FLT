"""Convert a single-file ComfyUI Z-Image checkpoint to the diffusers
transformer directory expected by ai-toolkit, using ComfyUI's official map.

z_image_to_diffusers is copied verbatim from comfy/utils.py, the
authoritative table used to load diffusers Z-Image models. It renames
grouped layers (all_x_embedder.2-1/all_final_layer.2-1) and splits fused
QKV attention into to_q/to_k/to_v.

Run with ai-toolkit Python for diffusers validation:
python convert_comfy_zimage_to_diffusers.py <input.safetensors> <official_config.json> [--save <out_dir>]
Without --save, validate keys/shapes against ZImageTransformer2DModel
on the meta device without writing.

Memory: never map the full checkpoint. safetensors.torch.load_file
previously mapped the entire container, immediately reserving Windows
commit. On an 11.46 GB checkpoint, opening alone grew private commit
from 0.18 to 11.67 GB in 0.1 seconds without changing resident memory.
Building Q/K/V clones reached 14.87 GB; writing touched the remaining
11.46 GB. A 16.9 GB checkpoint could need about 22 GB commit, causing
OSError 1455 or OOM on a 16 GB machine with a default pagefile, while
a development machine with a large pagefile hid the problem.

_Reader instead seeks header offsets and reads one tensor at a time.
Output keys/dtypes/shapes/offsets are derived purely from the source
header, so the output header precedes all weight reads. Each tensor
is read, sliced, written and released. Peak memory holds one tensor,
not a checkpoint. Validation reads no weight bytes because shapes
already live in the header. The same issue was fixed in fp8_export."""
import sys
import os
import json
import shutil
import re
import struct

import torch


# ---- ComfyUI comfy/utils.py: z_image_to_diffusers (verbatim, attribution) -----
def z_image_to_diffusers(mmdit_config, output_prefix=""):
    n_layers = mmdit_config.get("n_layers", 0)
    hidden_size = mmdit_config.get("dim", 0)
    n_context_refiner = mmdit_config.get("n_refiner_layers", 2)
    n_noise_refiner = mmdit_config.get("n_refiner_layers", 2)
    key_map = {}

    def add_block_keys(prefix_from, prefix_to, has_adaln=True):
        for end in ("weight", "bias"):
            k = "{}.attention.".format(prefix_from)
            qkv = "{}.attention.qkv.{}".format(prefix_to, end)
            key_map["{}to_q.{}".format(k, end)] = (qkv, (0, 0, hidden_size))
            key_map["{}to_k.{}".format(k, end)] = (qkv, (0, hidden_size, hidden_size))
            key_map["{}to_v.{}".format(k, end)] = (qkv, (0, hidden_size * 2, hidden_size))
        block_map = {
            "attention.norm_q.weight": "attention.q_norm.weight",
            "attention.norm_k.weight": "attention.k_norm.weight",
            "attention.to_out.0.weight": "attention.out.weight",
            "attention.to_out.0.bias": "attention.out.bias",
            "attention_norm1.weight": "attention_norm1.weight",
            "attention_norm2.weight": "attention_norm2.weight",
            "feed_forward.w1.weight": "feed_forward.w1.weight",
            "feed_forward.w2.weight": "feed_forward.w2.weight",
            "feed_forward.w3.weight": "feed_forward.w3.weight",
            "ffn_norm1.weight": "ffn_norm1.weight",
            "ffn_norm2.weight": "ffn_norm2.weight",
        }
        if has_adaln:
            block_map["adaLN_modulation.0.weight"] = "adaLN_modulation.0.weight"
            block_map["adaLN_modulation.0.bias"] = "adaLN_modulation.0.bias"
        for k, v in block_map.items():
            key_map["{}.{}".format(prefix_from, k)] = "{}.{}".format(prefix_to, v)

    for i in range(n_layers):
        add_block_keys("layers.{}".format(i), "{}layers.{}".format(output_prefix, i))
    for i in range(n_context_refiner):
        add_block_keys("context_refiner.{}".format(i), "{}context_refiner.{}".format(output_prefix, i))
    for i in range(n_noise_refiner):
        add_block_keys("noise_refiner.{}".format(i), "{}noise_refiner.{}".format(output_prefix, i))

    MAP_BASIC = [
        ("final_layer.linear.weight", "all_final_layer.2-1.linear.weight"),
        ("final_layer.linear.bias", "all_final_layer.2-1.linear.bias"),
        ("final_layer.adaLN_modulation.1.weight", "all_final_layer.2-1.adaLN_modulation.1.weight"),
        ("final_layer.adaLN_modulation.1.bias", "all_final_layer.2-1.adaLN_modulation.1.bias"),
        ("x_embedder.weight", "all_x_embedder.2-1.weight"),
        ("x_embedder.bias", "all_x_embedder.2-1.bias"),
        ("x_pad_token", "x_pad_token"),
        ("cap_embedder.0.weight", "cap_embedder.0.weight"),
        ("cap_embedder.1.weight", "cap_embedder.1.weight"),
        ("cap_embedder.1.bias", "cap_embedder.1.bias"),
        ("cap_pad_token", "cap_pad_token"),
        ("t_embedder.mlp.0.weight", "t_embedder.mlp.0.weight"),
        ("t_embedder.mlp.0.bias", "t_embedder.mlp.0.bias"),
        ("t_embedder.mlp.2.weight", "t_embedder.mlp.2.weight"),
        ("t_embedder.mlp.2.bias", "t_embedder.mlp.2.bias"),
    ]
    for c, diffusers in MAP_BASIC:
        key_map[diffusers] = "{}{}".format(output_prefix, c)
    return key_map


PREFIX = "model.diffusion_model."

# Real safetensors headers are far smaller. Above this bound, the first
# eight bytes cannot plausibly be a header length.
_HEADER_LEN_MAX = 512 * 1024 * 1024

_DTYPE_BYTES = {
    'BOOL': 1, 'U8': 1, 'I8': 1, 'F8_E4M3': 1, 'F8_E5M2': 1,
    'I16': 2, 'U16': 2, 'F16': 2, 'BF16': 2,
    'I32': 4, 'U32': 4, 'F32': 4,
    'I64': 8, 'U64': 8, 'F64': 8,
}


def _torch_dtype_for(name):
    return {
        'BF16': torch.bfloat16, 'F16': torch.float16, 'F32': torch.float32,
        'F64': torch.float64, 'F8_E4M3': torch.float8_e4m3fn,
        'F8_E5M2': torch.float8_e5m2, 'I64': torch.int64, 'I32': torch.int32,
        'I16': torch.int16, 'I8': torch.int8, 'U8': torch.uint8,
        'BOOL': torch.bool,
    }.get(str(name).upper())


def read_header(path):
    """Safetensors tensor index and __metadata__ only. Never touch the
    multi-gigabyte weight body."""
    try:
        with open(path, 'rb') as fh:
            raw = fh.read(8)
            if len(raw) != 8:
                raise ValueError('file too short for a safetensors container')
            n = struct.unpack('<Q', raw)[0]
            if n <= 0 or n > _HEADER_LEN_MAX:
                raise ValueError("implausible safetensors header length")
            blob = fh.read(n)
            if len(blob) != n:
                raise ValueError("truncated safetensors header")
            obj = json.loads(blob.decode('utf-8'))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        raise RuntimeError(f'unreadable .safetensors file ({e})') from e
    if not isinstance(obj, dict):
        raise RuntimeError("safetensors header is not an object")
    return obj


def _entries(header):
    return {k: v for k, v in header.items()
            if k != '__metadata__' and isinstance(v, dict)}


class _Reader:
    """Read one safetensors tensor at a time with ordinary file I/O.

    Deliberately avoid safetensors.safe_open/load_file, which map the entire
    container and immediately charge Windows commit (11.67 GB just to open
    an 11.46 GB file; see module documentation).

    Duplication of fp8_export._Reader is intentional: do not factor it out.
    This file runs as a CLI with a separate ai-toolkit interpreter/venv and
    can be sent as standalone source to a rented pod without LDS installed.
    Importing fp8_export would work locally but fail there."""

    def __init__(self, path):
        self.path = str(path)
        self._fh = open(self.path, 'rb')
        try:
            raw = self._fh.read(8)
            if len(raw) != 8:
                raise ValueError('file too short for a safetensors container')
            n = struct.unpack('<Q', raw)[0]
            if n <= 0 or n > _HEADER_LEN_MAX:
                raise ValueError("implausible safetensors header length")
            blob = self._fh.read(n)
            if len(blob) != n:
                raise ValueError("truncated safetensors header")
            self.header = json.loads(blob.decode('utf-8'))
            if not isinstance(self.header, dict):
                raise ValueError("safetensors header is not an object")
        except Exception as e:
            self._fh.close()
            raise RuntimeError(f'unreadable .safetensors file ({e})') from e
        self._start = 8 + n
        self.entries = _entries(self.header)

    def get_tensor(self, name):
        spec = self.entries.get(name)
        if spec is None:
            raise RuntimeError(f'{name} missing from {os.path.basename(self.path)}')
        dtype = _torch_dtype_for(spec.get('dtype'))
        if dtype is None:
            raise RuntimeError(f'unsupported dtype {spec.get("dtype")!r} for {name}')
        begin, end = int(spec['data_offsets'][0]), int(spec['data_offsets'][1])
        nbytes = end - begin
        self._fh.seek(self._start + begin)
        # Read into a bytearray: torch.frombuffer warns about read-only buffers,
        # and copying afterward would hold two copies of the tensor.
        raw = bytearray(nbytes)
        got = self._fh.readinto(raw)
        if got != nbytes:
            raise RuntimeError(
                f'{os.path.basename(self.path)} is truncated: {name} declares '
                f'{nbytes} bytes, {got} present.')
        shape = [int(d) for d in (spec.get('shape') or [])]
        return torch.frombuffer(raw, dtype=dtype).reshape(shape)

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


def _raw_bytes(tensor):
    """Contiguous little-endian bytes for any tensor, including bf16/fp8.
    NumPy lacks float8/bfloat16; reinterpret with a same-itemsize integer
    view to preserve exact bytes without value conversion."""
    flat = tensor.detach().to('cpu').contiguous().reshape(-1)
    view = {torch.float8_e4m3fn: torch.uint8, torch.float8_e5m2: torch.uint8,
            torch.bfloat16: torch.int16}.get(flat.dtype)
    if view is not None:
        flat = flat.view(view)
    return flat.numpy().tobytes()


def _pack_header(index, metadata=None):
    obj = dict(index)
    if metadata:
        obj['__metadata__'] = {str(k): str(v) for k, v in metadata.items()}
    blob = json.dumps(obj, separators=(',', ':')).encode('utf-8')
    blob += b' ' * ((-len(blob)) % 8)        # Align the data section to eight bytes.
    return struct.pack('<Q', len(blob)) + blob


def plan_diffusers_tensors(header):
    """Return (plan, unmapped, extra) purely from the source header.

    plan is an ordered list of (diffusers_key, source_key, slice_or_None,
    dtype, shape). A slice is (dim, start, length) for each fused-QKV part.
    Group by source so each tensor is read once even when it feeds three
    diffusers keys. Keys/shapes suffice for validation without weight I/O,
    and the output header can be written before streaming any tensors."""
    entries = _entries(header)
    src = {}
    for k, spec in entries.items():
        stripped = k[len(PREFIX):] if k.startswith(PREFIX) else k
        src[stripped] = (k, spec)

    n_layers = max([int(m.group(1)) for k in src if (m := re.match(r"layers\.(\d+)\.", k))], default=-1) + 1
    n_ref = max([int(m.group(1)) for k in src if (m := re.match(r"context_refiner\.(\d+)\.", k))], default=-1) + 1
    n_noise = max([int(m.group(1)) for k in src if (m := re.match(r"noise_refiner\.(\d+)\.", k))], default=-1) + 1
    if 'layers.0.attention.qkv.weight' not in src:
        raise RuntimeError(
            "layers.0.attention.qkv.weight missing: this is not a "
            "ComfyUI-format Z-Image checkpoint.")
    qkv_rows = int(src['layers.0.attention.qkv.weight'][1]['shape'][0])
    # Division by three assumes MHA: fused qkv=3*dim and n_kv_heads=n_heads.
    # Z-Image has 30 heads without GQA. Assert divisibility: a GQA layout
    # (qkv=dim+2*kv_dim) would yield wrong dimensions and shifted Q/K/V slices.
    if qkv_rows % 3 != 0:
        raise RuntimeError(
            f"qkv.weight rows={qkv_rows} not divisible by 3: non-MHA checkpoint "
            f"(GQA?) is not supported by this Z-Image converter.")
    dim = qkv_rows // 3
    print(f"  derived config: n_layers={n_layers} n_context_refiner={n_ref} n_noise_refiner={n_noise} dim={dim}")
    if n_noise != n_ref:
        # z_image_to_diffusers uses one n_refiner_layers for both refiners.
        # Different depths would emit only min(n_noise,n_ref) layers and silently
        # drop extras, while validation against a single-depth config could pass.
        # The target cannot represent asymmetric depths anyway: reject them
        # instead of reporting success for an incomplete transformer.
        raise RuntimeError(
            f"noise_refiner depth ({n_noise}) != context_refiner ({n_ref}): asymmetric depths "
            f"cannot be represented in diffusers ZImageTransformer2DModel "
            f"(single n_refiner_layers). Conversion refused to avoid losing weights.")
    key_map = z_image_to_diffusers({"n_layers": n_layers, "dim": dim, "n_refiner_layers": n_ref})

    plan, unmapped = [], []
    for diff_key, ref in key_map.items():
        cut = None
        ck = ref
        if isinstance(ref, tuple):
            ck, cut = ref[0], ref[1]
        if ck not in src:
            unmapped.append((diff_key, ck))
            continue
        real_key, spec = src[ck]
        shape = [int(d) for d in (spec.get('shape') or [])]
        if cut is not None:
            d, _start, length = cut
            if d >= len(shape):
                unmapped.append((diff_key, ck))
                continue
            shape = list(shape)
            shape[d] = int(length)
        plan.append((diff_key, real_key, cut, str(spec.get('dtype')), shape))
    used = {(s[0] if isinstance(s, tuple) else s) for s in key_map.values()}
    extra = [k for k in src if k not in used]
    # Group by source: fused qkv feeds to_q/to_k/to_v without being read
    # two or three times during writing.
    plan.sort(key=lambda e: (e[1], e[0]))
    print(f"  mapped {len(plan)} diffusers keys | {len(unmapped)} src-absent | {len(extra)} comfy keys unused")
    for mk in unmapped[:8]:
        print("     SRC-ABSENT:", mk)
    for e in extra[:8]:
        print("     UNUSED-COMFY:", e)
    return plan, unmapped, extra


def gate(plan, cfg_path):
    """Compare plan keys/shapes against ZImageTransformer2DModel from cfg_path
    on the meta device. Read no weight bytes; shapes come from the header."""
    with open(cfg_path) as f:
        cfg = json.load(f)
    try:
        from diffusers import ZImageTransformer2DModel
    except ImportError:
        from diffusers.models.transformers.transformer_z_image import ZImageTransformer2DModel
    with torch.device("meta"):
        model = ZImageTransformer2DModel.from_config(cfg)
    exp = {k: tuple(v.shape) for k, v in model.state_dict().items()}
    got = {e[0]: tuple(e[4]) for e in plan}
    missing = [k for k in exp if k not in got]
    unexpected = [k for k in got if k not in exp]
    mism = [(k, exp[k], got[k]) for k in exp if k in got and exp[k] != got[k]]
    print(f"\n=== GATE === model keys={len(exp)} | converted={len(got)}")
    print(f"  missing={len(missing)}  unexpected={len(unexpected)}  shape_mismatch={len(mism)}")
    for m in missing[:15]:
        print("     missing:", m)
    for u in unexpected[:10]:
        print("     unexpected:", u)
    for k, e, g in mism[:10]:
        print(f"     shape: {k} expected {e} got {g}")
    # Unexpected keys must fail validation: diffusers/ai-toolkit load with
    # strict=True and reject extras. Ignoring them could report PASSED then
    # write unloadable attention biases or context_refiner adaLN weights.
    ok = (len(missing) == 0 and len(mism) == 0 and len(unexpected) == 0)
    print("\n[GATE PASSED] all diffusers keys populated, shapes OK, no extra keys" if ok
          else "\n[GATE FAILED] incomplete remap (missing keys / shapes / unexpected keys)")
    return ok


def write_transformer(comfy_path, plan, out_path):
    """Stream diffusers safetensors: derive the output header from the plan
    and source header, then read, optionally slice, write and release each
    source tensor once. Peak memory holds one tensor and nothing is mapped,
    so file size no longer determines commit needs. Write to .part and
    rename on completion so interrupted conversions cannot leave an
    apparently valid, half-written cached transformer."""
    index, offset = {}, 0
    for diff_key, _src_key, _cut, dtype, shape in plan:
        width = _DTYPE_BYTES.get(str(dtype).upper())
        if not width:
            raise RuntimeError(f'unsupported dtype {dtype!r} for {diff_key}')
        numel = 1
        for d in shape:
            numel *= int(d)
        nbytes = numel * width
        index[diff_key] = {'dtype': dtype, 'shape': list(shape),
                           'data_offsets': [offset, offset + nbytes]}
        offset += nbytes

    tmp = str(out_path) + '.part'
    written = 0
    try:
        with _Reader(comfy_path) as reader, open(tmp, 'wb') as out:
            out.write(_pack_header(index))
            cached_key, cached = None, None
            for diff_key, src_key, cut, _dtype, _shape in plan:
                if src_key != cached_key:
                    cached, cached_key = reader.get_tensor(src_key), src_key
                tensor = cached
                if cut is not None:
                    d, start, length = cut
                    tensor = cached.narrow(d, int(start), int(length))
                out.write(_raw_bytes(tensor))
                written += 1
            del cached
        os.replace(tmp, out_path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return written


def main():
    inp, cfg_path = sys.argv[1], sys.argv[2]
    save_dir = None
    if "--save" in sys.argv:
        save_dir = sys.argv[sys.argv.index("--save") + 1]
    print(f"Loading {inp} ...")
    plan, _unmapped, _extra = plan_diffusers_tensors(read_header(inp))
    ok = gate(plan, cfg_path)
    if ok and save_dir:
        tdir = os.path.join(save_dir, "transformer")
        os.makedirs(tdir, exist_ok=True)
        n = write_transformer(inp, plan,
                              os.path.join(tdir, "diffusion_pytorch_model.safetensors"))
        shutil.copy2(cfg_path, os.path.join(tdir, "config.json"))
        print(f"\nsaved diffusers transformer ({n} tensors) -> {tdir}")


if __name__ == "__main__":
    main()
