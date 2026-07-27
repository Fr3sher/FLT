"""Keep the PIXELS of every image a run trained on, so a deleted image is still
visible in a comparison months later.

The gap this closes: "what changed between these two trainings?" is answered by
the manifest for everything except the one change that matters most — *"an image
was removed"*. Once it is gone from the dataset there is nothing left to look at,
and the diff can only recite an id.

The design that made this affordable rather than a per-run gigabyte:

* **Content-addressed.** A file is stored once under its own content hash
  (`run_images/ab/ab12…cd.jpg`), the same hash the run snapshot already computes.
  Ten runs on an unchanged dataset store nothing the second time; a run that
  edited three crops stores three files. Two datasets that share an image share
  its blob.
* **Off the launch path.** Copying happens in a daemon thread AFTER the record is
  committed. A launch never waits for it and never fails because of it.
* **Bounded.** The store stops growing at `provenance.archive_max_gb` (default 5)
  instead of quietly eating the disk. Past the ceiling nothing is added and the
  diff honestly reports the image as unavailable rather than showing a wrong one.
* **Copies, not hardlinks.** A hardlink would cost zero bytes, but the app
  rewrites images IN PLACE (re-crop, "Reset to auto", watermark cleaning) and an
  in-place rewrite reuses the inode — the "archived" copy would silently change
  into the new version, which is the exact lie this exists to prevent.

Measured on a real 20-dataset library: 1471 kept images, 444 MB in total, ~295 KB
mean. A full deduplicated archive of the entire training history is well under a
gigabyte, and an incremental launch copies only what actually changed.
"""
from __future__ import annotations

import logging
import os
import shutil
import threading

from .. import config as cfg

logger = logging.getLogger(__name__)

_DEFAULT_MAX_GB = 5.0
_ALLOWED_EXT = ('.png', '.jpg', '.jpeg', '.webp')

_lock = threading.Lock()
_size_cache = {'bytes': None}


def archive_root():
    root = cfg._data_dir() / 'run_images'
    root.mkdir(parents=True, exist_ok=True)
    return root


def _root_only():
    """The archive path WITHOUT creating it. `_blob_path` is called several times
    per image while probing extensions, and a compare payload probes a hundred
    images — an `mkdir` per probe is hundreds of pointless syscalls on a read
    path. Creation belongs to the write path (`store`), which calls
    `archive_root` itself."""
    return cfg._data_dir() / 'run_images'


def _blob_path(sig, ext):
    """`<root>/<first two hex chars>/<sig><ext>` — the two-level fan-out keeps a
    directory listing sane once the store holds thousands of blobs."""
    sig = str(sig)
    return _root_only() / sig[:2] / f'{sig}{ext}'


def _normalise_ext(filename):
    ext = os.path.splitext(str(filename or ''))[1].lower()
    return ext if ext in _ALLOWED_EXT else '.png'


def max_bytes() -> int:
    try:
        gb = float(cfg.get('provenance.archive_max_gb', _DEFAULT_MAX_GB))
    except (TypeError, ValueError):
        gb = _DEFAULT_MAX_GB
    return int(max(0.0, gb) * (1 << 30))


def enabled() -> bool:
    """False disables archiving entirely (`provenance.archive_max_gb: 0`). The
    diff then reports removed images as unavailable — honest, never invented."""
    return max_bytes() > 0


def size_bytes(refresh=False) -> int:
    """Bytes currently held by the archive. Cached: the Settings card asks for it
    on every open and walking thousands of small files each time is wasteful."""
    if not refresh and _size_cache['bytes'] is not None:
        return _size_cache['bytes']
    total = 0
    try:
        for dirpath, _dirs, files in os.walk(archive_root()):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, fn))
                except OSError:
                    continue
    except OSError:
        total = 0
    _size_cache['bytes'] = total
    return total


def clear() -> dict:
    """Delete every archived blob. Destroys the ability to SHOW images that have
    since left their dataset; the runs, their settings and their captions are in
    the database and are untouched."""
    freed = size_bytes(refresh=True)
    try:
        shutil.rmtree(archive_root(), ignore_errors=True)
    finally:
        _size_cache['bytes'] = None
    archive_root()
    return {'freed_bytes': freed}


def path_for(sig, ext=None):
    """Absolute path of an archived blob, or None when it isn't stored (never
    archived, archived before the ceiling was hit, or cleared). `ext` narrows the
    lookup; without it every known extension is probed."""
    if not sig or not str(sig).isalnum():
        return None
    for candidate in ((ext,) if ext else _ALLOWED_EXT):
        p = _blob_path(sig, candidate)
        if p.is_file():
            return str(p)
    return None


def store(plan) -> dict:
    """Copy every `(source_path, sig, filename)` of `plan` that isn't stored yet.
    Synchronous; returns `{'added', 'skipped', 'full'}`. Never raises."""
    added = skipped = 0
    full = False
    if not enabled():
        return {'added': 0, 'skipped': len(plan or ()), 'full': True}
    ceiling = max_bytes()
    archive_root()                      # the one place the folder is created
    with _lock:
        current = size_bytes()
        for src, sig, filename in (plan or ()):
            if not src or not sig:
                continue
            ext = _normalise_ext(filename)
            dst = _blob_path(sig, ext)
            try:
                if dst.is_file() or path_for(sig):
                    skipped += 1
                    continue
                size = os.path.getsize(src)
                if current + size > ceiling:
                    full = True
                    break
                dst.parent.mkdir(parents=True, exist_ok=True)
                # Copy to a temp name then rename: a crash mid-copy must never
                # leave a TRUNCATED blob sitting at the address of a valid hash.
                tmp = dst.with_suffix(dst.suffix + '.part')
                shutil.copyfile(src, tmp)
                os.replace(tmp, dst)
                current += size
                added += 1
            except OSError:
                logger.debug('could not archive %s', sig, exc_info=True)
                continue
        _size_cache['bytes'] = current
    if full:
        logger.info('run image archive is at its %.1f GB ceiling — not adding more',
                    ceiling / (1 << 30))
    return {'added': added, 'skipped': skipped, 'full': full}


def archive_async(plan) -> None:
    """Fire-and-forget `store(plan)` on a daemon thread. The launch has already
    committed by the time this is called; nothing downstream depends on it, so a
    machine that is killed mid-copy simply has fewer archived images."""
    if not plan or not enabled():
        return
    try:
        threading.Thread(target=_store_quietly, args=(list(plan),),
                         name='run-archive', daemon=True).start()
    except RuntimeError:
        logger.debug('could not start the archive thread', exc_info=True)


def _store_quietly(plan):
    try:
        store(plan)
    except Exception:
        logger.debug('run image archiving failed', exc_info=True)
