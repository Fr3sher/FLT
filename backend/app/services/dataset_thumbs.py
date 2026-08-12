"""Cached thumbnails for dataset images.

WHY THIS EXISTS. Every surface that shows a dataset image at ~100-400 px on
screen — the ◉ LoRA Canvas board, the dataset grid, the Test Studio sweep, the
checkpoint preview pills, the cloud-run cards — used to request
``/api/dataset/<id>/img/<name>``, which serves the ORIGINAL bytes: 1-4 megapixel
PNGs, megabytes each, fully decoded by the browser so it can draw a tile the
size of a postage stamp. A board with fifty pinned pictures paid that fifty
times, on every open.

The Bank solved the same problem years earlier (``image_bank_service.ensure_thumb``);
this is that mechanic ported to the dataset lane, with ONE deliberate difference:

  THE CACHE KEY CARRIES THE SOURCE'S mtime AND SIZE.

The Bank can key a thumbnail on a row id because a Bank image is immutable and
its derived variants (cleaned, rotated) each get their own name, dropped by an
explicit invalidation call. A dataset image is the opposite: crop, rotate,
✨ improve, watermark-clean and regenerate all rewrite the SAME filename in
place, from several code paths. A key that ignores the bytes would serve the
pre-crop picture forever, and every one of those code paths would have to
remember to call an invalidation helper — which is exactly the kind of debt
that gets forgotten by the sixth caller. Keying on (mtime_ns, size) makes
staleness structurally impossible instead of procedurally avoided.
"""
from __future__ import annotations

import hashlib
import os
import re
import warnings
from pathlib import Path

from PIL import Image

from .. import config as cfg
from . import image_encoding

# The ladder of thumbnail sizes the server is willing to materialise. `?s=` is
# snapped UP to the next rung rather than honoured verbatim: a free-form integer
# lets any caller (or any crafted URL) mint an unbounded number of cache entries
# per image, and nothing on screen needs 437 px specifically.
THUMB_SIDES = (128, 192, 256, 320, 384, 512, 640, 768, 1024)

# No `?s=` means "a tile", and 512 is the honest default for the biggest of the
# tile surfaces (a canvas image node resized large, a dataset grid at size L on
# a HiDPI screen). Consumers that know they are smaller ask for less.
DEFAULT_THUMB_SIDE = 512

# Same encoder settings as the Bank grid: WebP at 72 is visually clean at these
# sizes and roughly an order of magnitude smaller than the source PNG.
THUMB_FORMAT = 'WEBP'
THUMB_QUALITY = 72

# Raw byte cap before Pillow is handed the file at all — same number the Bank
# uses for its live sources. A thumbnail is never worth unbounded I/O.
SOURCE_MAX_BYTES = 96 * 1024 * 1024


def clamp_thumb_side(raw) -> int:
    """The size this request is allowed to get, snapped onto THUMB_SIDES.

    Anything unparseable or non-positive falls back to the default instead of
    erroring: a thumbnail route must never answer 400 over a query string —
    the caller wants a picture.
    """
    try:
        want = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_THUMB_SIDE
    if want <= 0:
        return DEFAULT_THUMB_SIDE
    for side in THUMB_SIDES:
        if want <= side:
            return side
    return THUMB_SIDES[-1]


_SAFE_BUCKET = re.compile(r'[^A-Za-z0-9_-]')


def thumbs_dir(bucket, create: bool = False) -> Path:
    """One cache folder per owner. `bucket` is a dataset id for dataset images
    and a `run-<share key>` label for a training run's sample; it is scrubbed
    down to `[A-Za-z0-9_-]` because it ends up as a directory NAME, and a value
    that reached here from a URL must not be able to steer where a file is
    written even if every caller above is already careful."""
    path = cfg.dataset_thumbs_root(create=create) / _SAFE_BUCKET.sub('_', str(bucket))
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _source_key(filename: str) -> str:
    """A filesystem-safe, collision-resistant stand-in for the image's name.

    Dataset filenames are user data — they carry unicode, spaces and (via the
    `<path:filename>` converter) sub-directories. Hashing sidesteps every
    encoding question in one move; the source name is never needed back.
    """
    digest = hashlib.sha256(filename.encode('utf-8', 'surrogatepass'))
    return digest.hexdigest()[:20]


def _cache_path(bucket, filename: str, side: int, stat: os.stat_result,
                create: bool = False) -> Path:
    return thumbs_dir(bucket, create=create) / (
        f'{_source_key(filename)}.{side}.{stat.st_mtime_ns}.{stat.st_size}.webp')


def _drop_other_generations(path: Path) -> None:
    """Remove the SAME image at the SAME size from an older generation.

    Bounded on purpose: only the `<key>.<side>.*` siblings go, so the other
    sizes this image is legitimately cached at survive. Best effort — on Windows
    a file may still be held open by the response that just served it, and a
    leftover nobody points at is harmless.
    """
    prefix = '.'.join(path.name.split('.')[:2])
    try:
        for stale in path.parent.glob(f'{prefix}.*.webp'):
            if stale == path:
                continue
            try:
                stale.unlink()
            except OSError:
                pass
    except OSError:
        pass


def ensure_thumb(bucket, src_path: str, filename: str, side: int) -> Path | None:
    """The cached thumbnail of one dataset image, built on first request.

    Returns ``None`` — never raises — whenever a thumbnail is not the right
    answer, and the caller is expected to fall back to the original bytes:

    * the file is missing (the route then 404s exactly like ``/img/`` does);
    * it is not a still raster this app edits (an animated GIF, a video, a
      format Pillow will not open): a thumbnail route that 500s on an odd file
      is worse than one that serves the file;
    * it is ALREADY smaller than the requested side — re-encoding a 256 px
      picture into a 512 px WebP costs CPU and disk to make it bigger.
    """
    try:
        stat = os.stat(src_path)
    except OSError:
        return None
    if not os.path.isfile(src_path) or stat.st_size > SOURCE_MAX_BYTES:
        return None
    cached = _cache_path(bucket, filename, side, stat)
    if cached.is_file():
        return cached
    try:
        with warnings.catch_warnings():
            # Promote the decompression-bomb warning to an exception LOCALLY —
            # a request handler must never mutate the process-wide policy.
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(src_path) as im:
                fmt = (im.format or '').upper()
                if fmt not in image_encoding.EDITABLE_FORMATS:
                    return None
                if getattr(im, 'n_frames', 1) != 1:
                    return None
                width, height = image_encoding.validate_input_header_dimensions(
                    im, label='dataset thumbnail')
                if max(width, height) <= side:
                    return None
                # draft() lets the JPEG decoder skip straight to a smaller DCT
                # scale — the cheap half of the win, before a single full-size
                # pixel is materialised. Harmless no-op on PNG/WebP.
                im.draft(None, (side * 2, side * 2))
                im = im.convert('RGB')
                im.thumbnail((side, side), Image.LANCZOS)
                target = _cache_path(bucket, filename, side, stat, create=True)
                im.save(target, THUMB_FORMAT, quality=THUMB_QUALITY)
    except (OSError, ValueError, MemoryError, Image.DecompressionBombError,
            Image.DecompressionBombWarning, Image.UnidentifiedImageError):
        return None
    _drop_other_generations(target)
    return target


def drop_dataset_thumbs(dataset_id) -> None:
    """Throw away a dataset's whole thumbnail cache (it was deleted).

    Best effort by design: this is derived data, and failing a dataset deletion
    because a cache file is locked would be the tail wagging the dog.
    """
    import shutil
    try:
        shutil.rmtree(thumbs_dir(dataset_id), ignore_errors=True)
    except OSError:
        pass
