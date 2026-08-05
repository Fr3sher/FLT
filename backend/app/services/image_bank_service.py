"""🗃️ Image bank service — triage a big unsorted folder into dataset-ready
selections.

The founding use case: "I exported 9 000 images from Telegram — now what?".
A bank references that folder IN PLACE (no copy, the source files are never
written to) and layers a funnel on top:

  1. inventory      — instant: walk the folder, register every image file;
  2. quality pass   — background thread, CPU/pure-PIL: sharpness, noise,
                      uniformity, dimensions, dHash + duplicate groups;
                      raw scores persist, FLAGS are computed at read time
                      against the config thresholds ('bank' section) so
                      recalibrating never needs a rescan;
  3. duplicates     — near-duplicate groups (same 64-bit dHash family as the
                      dataset import dedup) with keep-best / keep-first /
                      manual resolution — losers are REJECTED (a status),
                      never deleted from disk;
  4. subject pass   — optional, needs the face-scoring extra: InsightFace
                      embeddings (cached in an .npz next to the thumbs) +
                      person clustering, to sort a mixed dump by WHO is in
                      the frame without any reference photo;
  5. promotion      — the kept selection enters a dataset through the configured
                      import policy (raw-preserve by default, optional WebP
                      normalisation) + perceptual dedup, inheriting every downstream tool
                      (captions, watermarks, face scoring, training).

Long passes run through bank_jobs (one background thread per bank, polled via
the bank payload) — a 9 000-image folder must scan in minutes without ever
holding an HTTP request open or freezing the UI.
"""
from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import warnings
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import and_, case, func, or_, text

from .. import config as cfg
from ..extensions import db
from ..models import BankImage, FaceDataset, FaceDatasetImage, ImageBank
from . import (bank_jobs, bank_transfer_metadata, bank_undo, caption_origin,
               image_encoding, path_guard, trash)
from .face_dataset_service import (SCRAPE_IMPORT_MAX, _dhash, _download_scrape_item,
                                   _dataset_ingest_lock,
                                   _existing_dhash_rows, _hamming, _SCRAPE_DL_WORKERS,
                                   _watermark_regions_payload,
                                   _source_metadata_storage, bank_deterministic_analysis,
                                   import_images, _preserved_import_extension,
                                   normalize_watermark_regions)
from .image_quality import ANALYSIS_MAX_SIDE, quality_metrics
from .image_provenance import ORIGINS, provenance_metrics

logger = logging.getLogger(__name__)

IMG_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
# Sanity cap — a bank is a triage layer, not a filesystem indexer: this is what
# catches "I pointed it at a whole drive", nothing more. Measured on a synthetic
# tree of 200 000 files (50 subfolders, warm cache): the walk refresh_bank runs
# costs 2.5 s, the per-file getsize 1.8 s, the chunked INSERT of every row 0.2 s,
# and reading the known-relpath set back 0.14 s. The walk is the only real cost and
# it is already cooldown-limited (FOLDER_SYNC_COOLDOWN), so 50 000 was far below
# what the code can carry; the per-image passes that ARE expensive have always
# been background jobs with their own progress bar.
BANK_MAX_FILES = 200_000
THUMB_MAX_SIDE = 320
_COMMIT_EVERY = 25          # scan DB flush cadence
_PROMOTE_CHUNK = 20         # files per import_images call (bounded memory)
_SQL_IN_CHUNK = 500         # SQLite bound-variable ceiling is 999
# --- duplicate regrouping budgets (see rebuild_dup_groups) -------------------
# Rows written between two commits. The whole regrouping used to be ONE
# transaction: a global clear plus one UPDATE per group, ~5 000 of them on a
# 50 000-image bank, measured holding the single SQLite write lock 6 to 9.5 s —
# past the 5 s busy_timeout, so every other writer in the app died on
# `database is locked` (3 attempts out of 3) while the progress bar sat at 100 %.
_DUP_WRITE_ROWS = 2000
# And the pause AFTER each batch. Without it the next batch re-takes the write
# lock in the microsecond after the commit, inside the sleep of another writer's
# busy handler: batching alone still left a concurrent writer waiting 620 ms and
# refused (measured, test_bank_scan_no_db_lock.py). Five batches on a 50 000-image
# bank make this 100 ms of wall time in total.
_DUP_WRITE_YIELD = 0.02
# Bucket size from which the pairwise comparison goes to numpy. Below it the
# plain Python loop is cheaper than allocating arrays, and it is bounded by
# construction (at most 21 pairs).
_DUP_NUMPY_FROM = 8
# Ceiling on the cells of ONE comparison block, so peak memory follows this
# constant and not the bucket size: 2e6 cells ≈ 34 MB of uint64 XOR plus its
# popcount lookup, freed at every block.
_DUP_BLOCK_CELLS = 2_000_000
_POPCOUNT8 = None           # lazily built uint8 popcount table (see _popcount_lut)
# A quality pass that keeps finding NOTHING on disk is not looking at a bank of
# broken images — it is looking at the wrong folder. Bail out after this many
# absent files (when they are at least half of what has been walked) rather than
# grind through 30 000 of them; a handful of genuinely deleted files stays a
# non-event and only shows up in the folder-sync note.
_MISSING_ABORT_AT = 20
MOVED_FOLDER_MSG = (
    "this folder no longer holds the bank's images — it may have been moved, "
    'renamed, or sit on a drive that is disconnected. Nothing was changed: '
    'point the bank at its new folder, then run the pass again.')

# A Bank points at a live user folder: files can arrive or be replaced long after
# import.  Keep the same byte/pixel envelope as Dataset ingress before any Bank
# consumer decodes, copies to an infer child, or reads the whole file into RAM.
# 96 MiB covers a valid 16 MP RGBA/BMP master plus container overhead.
BANK_SOURCE_MAX_BYTES = 96 * 1024 * 1024


def _bank_source_size_guard(path, *, label: str) -> int:
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError, MemoryError) as exc:
        raise ValueError(f'{label} is unavailable') from exc
    if size > BANK_SOURCE_MAX_BYTES:
        raise ValueError(
            f'{label} is too large (max {BANK_SOURCE_MAX_BYTES // (1024 * 1024)} MiB)')
    return size


@contextmanager
def safe_bank_source(path, *, label: str = 'bank image'):
    """Open one live Bank source after static/header safety validation.

    The yielded Pillow object remains open so callers can safely perform their
    one intended decode.  Header validation happens first, with Pillow's bomb
    warning promoted locally to an exception; the global warning policy is never
    mutated by a background worker.
    """
    _bank_source_size_guard(path, label=label)
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(path) as image:
            fmt = (image.format or '').upper()
            if fmt not in image_encoding.EDITABLE_FORMATS:
                raise ValueError(f'{label} has unsupported format: {fmt or "unknown"}')
            if getattr(image, 'n_frames', 1) != 1:
                raise ValueError(f'{label} must be a static image')
            image_encoding.validate_input_header_dimensions(image, label=label)
            yield image


def _read_safe_bank_source_bytes(path, *, label: str = 'bank image') -> bytes:
    """Read one live source with both a raw-byte cap and content validation.

    This closes the time-of-check/time-of-use gap for paths handed as bytes to
    Dataset import or Ollama: the exact bounded bytes read are revalidated before
    any downstream service sees them.
    """
    _bank_source_size_guard(path, label=label)
    try:
        with open(path, 'rb') as source:
            raw = source.read(BANK_SOURCE_MAX_BYTES + 1)
    except (OSError, TypeError, MemoryError) as exc:
        raise ValueError(f'{label} is unavailable') from exc
    if len(raw) > BANK_SOURCE_MAX_BYTES:
        raise ValueError(
            f'{label} is too large (max {BANK_SOURCE_MAX_BYTES // (1024 * 1024)} MiB)')
    try:
        _preserved_import_extension(raw, label=label)
    except MemoryError as exc:
        raise ValueError(f'{label} is invalid') from exc
    return raw


def _is_safe_bank_source(path, *, label: str = 'bank image') -> bool:
    """Header-check a live source for an infer/caption path without decoding it."""
    if not path or not os.path.isfile(path):
        return False
    try:
        with safe_bank_source(path, label=label):
            return True
    except (OSError, ValueError, MemoryError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        return False


# --- thresholds -------------------------------------------------------------
def thresholds() -> dict:
    """The 'bank' config section, sanitized (a corrupt config.json value falls
    back to the default instead of poisoning every flag computation)."""
    out = {}
    for key, default in cfg.DEFAULTS['bank'].items():
        try:
            out[key] = float(cfg.get(f'bank.{key}', default))
        except (TypeError, ValueError):
            out[key] = float(default)
    out['dup_distance'] = int(out['dup_distance'])
    out['min_side'] = int(out['min_side'])
    return out


# --- storage helpers --------------------------------------------------------
def _bank_dir(bank_id) -> Path:
    return cfg.banks_root() / str(bank_id)


def _thumbs_dir(bank_id) -> Path:
    return _bank_dir(bank_id) / 'thumbs'


def _face_cache_path(bank_id) -> Path:
    return _bank_dir(bank_id) / 'face_cache.npz'


def _score_cache_path(bank_id) -> Path:
    return _bank_dir(bank_id) / 'score_cache.npz'


def _abs_under(base: str, relpath: str) -> str | None:
    """The containment-checked realpath of ``relpath`` under an ALREADY resolved
    ``base``. Split out of ``abs_image_path`` so a loop over thousands of rows can
    resolve the bank folder ONCE instead of per row: ``os.path.realpath`` is a
    filesystem call, and re-resolving the same unchanging bank folder for every
    image cost 424 ms of the 6 353-row curation pool alone (measured). Same
    strings out, one syscall in."""
    full = os.path.realpath(os.path.join(base, relpath))
    if os.path.normcase(full).startswith(os.path.normcase(base + os.sep)):
        return full
    return None


def abs_image_path(bank: ImageBank, row: BankImage) -> str | None:
    """Absolute SOURCE path of a bank image, or None when it escapes the
    bank's folder (belt & braces — relpaths only ever come from our own walk).

    ⚠️ This is the user's own file. It is READ-ONLY for us, and it is NOT what
    the app should display or copy once a watermark has been cleaned — every
    reader must go through resolved_image_path() instead (see its docstring)."""
    return _abs_under(os.path.realpath(bank.source_path), row.relpath)


def _clean_dir(bank_id) -> Path:
    """Where watermark-cleaned versions live — the bank's OWN working directory,
    next to thumbs/. Never inside the user's folder."""
    return _bank_dir(bank_id) / 'clean'


def clean_image_path(bank_id, image_id) -> Path:
    """The cleaned blob of one image (may not exist)."""
    return _clean_dir(bank_id) / f'{image_id}.webp'


def _rotated_dir(bank_id) -> Path:
    """Where manually TURNED copies live — the bank's own working directory,
    next to clean/. Never inside the user's folder."""
    return _bank_dir(bank_id) / 'rotated'


def rotated_image_path(bank_id, image_id, rotation, source: str) -> Path:
    """Where the turned copy of one image lives. Keyed on the angle AND on the
    source's extension so a rotated PNG stays a PNG; keyed on the CLEAN state too
    (via the source name) is unnecessary because every clean change drops the
    whole derived set (see drop_derived)."""
    ext = os.path.splitext(source)[1].lower() or '.png'
    return _rotated_dir(bank_id) / f'{image_id}.r{int(rotation)}{ext}'


def _ensure_rotated(bank_id, row: BankImage, source: str) -> str:
    """Materialise (once) the turned copy of ``source`` and return its path.

    ALWAYS built from the pristine source — never from a previously rotated copy
    — so the angle is applied exactly once no matter how many times the user
    clicked. Fails OPEN: an encoder problem serves the un-turned image rather
    than a 404, because a bank must stay browsable."""
    from .face_dataset_service import (normalize_rotation,
                                       transformed_image_bytes, rotate_transform)
    try:
        turn = normalize_rotation(row.rotation)
    except ValueError:
        return source
    if not turn:
        return source
    dst = rotated_image_path(bank_id, row.id, turn, source)
    if dst.is_file():
        return str(dst)
    try:
        # The generic transform below also checks the pixel budget. This Bank
        # gate additionally constrains raw bytes/static content from a live
        # user folder before any edit helper gets a chance to decode it.
        with safe_bank_source(source, label='bank rotation'):
            pass
        payload = transformed_image_bytes(
            source, rotate_transform(turn), max_source_bytes=BANK_SOURCE_MAX_BYTES)
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Two simultaneous GETs of the same turned image (grid + lightbox) each
        # build it. A SHARED temp name would make one of them fail on Windows
        # (the other still holds it) and degrade to serving the un-turned source;
        # a unique one lets both win and the last atomic replace decide.
        tmp = dst.with_name(f'{dst.name}.{os.getpid()}-{threading.get_ident()}.tmp')
        try:
            tmp.write_bytes(payload)
            os.replace(tmp, dst)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return str(dst)
    except (ValueError, OSError) as e:
        logger.warning('bank image %s could not be rotated: %s', row.id, e)
        return source


def resolved_image_path(bank: ImageBank, row: BankImage) -> str | None:
    """THE path every reader must use: the watermark-cleaned version when one
    exists, the untouched source otherwise — turned by the row's manual rotation
    when it carries one.

    A bank is a read-only view over a folder we must never write to, so neither
    cleaning a watermark nor turning an image can rewrite the source: both write
    a separate blob under the bank's working directory. That only pays off if the
    READERS prefer it, so there is exactly ONE resolver and all three known
    readers call it: promotion (the blob handed to import_images), the grid
    thumbnail, and the /bank/<id>/file route. A new reader calling
    abs_image_path() directly would silently serve the watermarked original —
    test_bank_watermark_clean.py asserts these three go through here."""
    path = None
    if row.watermark_clean_method:
        cleaned = clean_image_path(bank.id, row.id)
        if cleaned.is_file():
            path = str(cleaned)
    if path is None:
        path = abs_image_path(bank, row)
    if path is None or not getattr(row, 'rotation', None):
        return path
    return _ensure_rotated(bank.id, row, path)


# --- CRUD -------------------------------------------------------------------
def get_bank(user_id, bank_id) -> ImageBank | None:
    return ImageBank.query.filter_by(id=bank_id, user_id=user_id).first()


def create_bank(user_id, name, folder):
    """Register a folder as a bank: walk it recursively and create one row per
    image file. Instant (no decode) — scoring is the separate scan pass.
    Returns (bank, added). ValueError on a missing folder / too many files."""
    name = (name or '').strip()
    # Windows «Copier en tant que chemin» pastes the path quoted — unquote so
    # the direct paste works first try (same nicety as the dataset folder import).
    folder = (folder or '').strip().strip('"\'')
    if not name:
        raise ValueError('name is required')
    if not folder or not os.path.isdir(folder):
        raise ValueError(f'folder not found or not readable: {folder or "(empty)"}')
    # A bank and a dataset only ever TRANSIT images (by copy) — they never share
    # them. This folder is the one place that door was open: a dataset's storage
    # folder pasted here made a bank over the dataset's LIVE files, and this
    # bank's 🗑 Delete rejected then deleted images out of the dataset.
    conflict = path_guard.dataset_folder_conflict(folder)
    if conflict:
        raise ValueError(conflict['message'])
    folder = os.path.realpath(folder)
    rels = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(IMG_EXTS):
                rels.append(os.path.relpath(os.path.join(root, f), folder))
                if len(rels) > BANK_MAX_FILES:
                    # Bail on the walk itself: a bank pointed at a whole drive
                    # must not be counted to the end before being refused.
                    raise ValueError(
                        f'this folder holds more than {BANK_MAX_FILES:,} images '
                        '— point the bank at a subfolder, or split it in two')
    bank = ImageBank(user_id=user_id, name=name, source_path=folder)
    db.session.add(bank)
    db.session.flush()          # need bank.id for the child rows
    _insert_bank_images(bank.id, folder, rels)
    db.session.commit()
    return bank, len(rels)


_INSERT_CHUNK = 2000


def _insert_bank_images(bank_id, folder, rels) -> int:
    """Insert one BankImage per relpath, in chunks, through a CORE insert.

    Row-by-row ``db.session.add`` costs ~141 us/file (measured: 7.1 s for a
    50 000-image folder), which at the folder sizes this app now accepts would
    hold the HTTP request open for half a minute. The same rows through a
    chunked core insert cost a fraction of that, and Python-side column defaults
    (status, timestamps) are applied exactly as the ORM would."""
    rows = []
    for rel in rels:
        try:
            size = os.path.getsize(os.path.join(folder, rel))
        except OSError:
            size = None
        rows.append({'bank_id': bank_id, 'relpath': rel, 'file_size': size})
    # A "this subfolder is one person" assertion is a RULE, not a stamp: a file
    # that lands in an asserted folder joins its person group here, on insert,
    # with no pass and no click (see services/folder_person.py).
    from . import folder_person
    folder_person.stamp_new_rows(bank_id, rows)
    for i0 in range(0, len(rows), _INSERT_CHUNK):
        db.session.execute(BankImage.__table__.insert(),
                           rows[i0:i0 + _INSERT_CHUNK])
    return len(rows)


# --- folder sync (incremental re-inventory) ---------------------------------
# A bank points at a LIVE folder: the user keeps scraping/exporting into it long
# after the bank was created. Re-walking it is cheap (~5 ms for 3 000 files), so
# the app does it for them instead of making them rebuild a bank they have
# already triaged. The cooldown is not about CPU — it keeps the workspace's 2 s
# poll from hitting the disk (possibly a spun-down external drive) constantly.
FOLDER_SYNC_COOLDOWN = 60.0
_folder_sync = {}       # bank_id -> {'at': monotonic, 'result': {...}}
_EMPTY_SYNC = {'added': 0, 'missing': 0, 'unavailable': False, 'error': None,
               'not_added': 0, 'limit': BANK_MAX_FILES}


def reset_folder_sync():
    """Drop the per-bank walk cooldowns (tests: bank ids restart at 1 with an
    in-memory DB, so a stale entry would silently skip the next test's walk)."""
    _folder_sync.clear()


def _sync_cached(bank_id) -> dict:
    """The last known folder state, with the per-walk EVENTS zeroed — nothing was
    added, and nothing was left out, by the call being answered from the cache.
    Reporting them again would re-toast one walk's outcome on every 2 s poll."""
    last = _folder_sync.get(bank_id)
    return {**(last['result'] if last else _EMPTY_SYNC), 'added': 0, 'not_added': 0}


def refresh_bank(user_id, bank_id, force=False) -> dict | None:
    """Re-inventory a bank's source folder: register the images that appeared in
    it since the last walk.

    STRICTLY ADDITIVE — the only write is an INSERT of relpaths we don't know
    yet. No row is ever deleted and no decision is ever reset (status, scores,
    quality_state, duplicate/semantic groups, captions, face verdicts), so a
    bank triaged over hours survives any number of refreshes. New rows land
    exactly like freshly inventoried ones (pending, unscanned), which is all the
    downstream passes need: the quality scan already only picks up rows with no
    quality_state, and it rebuilds the duplicate groups when it lands.

    Files that VANISHED from the folder are counted, never removed: an unplugged
    drive or a renamed folder would otherwise wipe a whole triage in one silent
    pass. The count is surfaced so the user can decide.

    The BANK_MAX_FILES ceiling is counted against what the walk found ON DISK,
    never against the bank's row history, and it no longer refuses the batch: as
    many new files as fit are added and the remainder is reported in
    ``not_added``. See the comment at the check for the bug that motivated both.

    Returns {'added', 'missing', 'unavailable', 'error', 'not_added', 'limit'},
    or None when the bank is unknown. ``force`` bypasses the cooldown (bank
    opened by hand)."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        return None
    now = time.monotonic()
    last = _folder_sync.get(bank_id)
    if not force and last and (now - last['at']) < FOLDER_SYNC_COOLDOWN:
        return _sync_cached(bank_id)
    # A live pass owns this bank's rows (the scan job works off a snapshot of
    # them and reports progress against a fixed total). Adding rows underneath
    # it is harmless for the data but would silently fall outside that total —
    # the next refresh, a second later, picks them up.
    if bank_jobs.running(bank_id):
        return _sync_cached(bank_id)

    folder = bank.source_path
    if not folder or not os.path.isdir(folder):
        return _remember_sync(bank_id, now, {**_EMPTY_SYNC, 'unavailable': True})

    known = {os.path.normcase(rel) for (rel,) in
             db.session.query(BankImage.relpath).filter_by(bank_id=bank_id)}
    seen, new_rels = set(), []
    try:
        for root, _dirs, files in os.walk(folder, onerror=lambda _e: None):
            for f in files:
                if not f.lower().endswith(IMG_EXTS):
                    continue
                rel = os.path.relpath(os.path.join(root, f), folder)
                key = os.path.normcase(rel)
                seen.add(key)
                if key not in known:
                    new_rels.append(rel)
    except OSError:
        # The folder went away mid-walk (drive unplugged) — report it and keep
        # every row: a partial walk must never be read as "these files are gone".
        return _remember_sync(bank_id, now, {**_EMPTY_SYNC, 'unavailable': True})

    new_rels.sort()             # deterministic order — a partial add takes a PREFIX
    # The cap is a property of the FOLDER, not of the bank's history. ``seen`` is
    # what the walk just found on disk (surviving rows + new files); rows whose
    # file the user deleted are NOT in it and must not consume the budget.
    #
    # THE BUG THIS REPLACES: the test was `len(known) + len(new_rels) > cap`,
    # where `known` is every relpath ever inventoried — refresh is deliberately
    # additive and never drops a row for a vanished file. So a folder that once
    # held 50 000 images and now holds 10 000 still counted as 50 000 for ever,
    # and the refusal told the user "the folder now holds more than 50000
    # images" about a folder holding a fifth of that. Measured before the fix:
    # 10 001 files on disk, 50 000 rows, one new file → refused.
    not_added = 0
    over = len(seen) - BANK_MAX_FILES
    if over > 0:
        # Non-blocking: add what fits (oldest-first by name) instead of refusing
        # the whole batch. Everything already in the bank keeps working, and the
        # count that was left out is reported so the user can act on it.
        keep = max(len(new_rels) - over, 0)
        not_added = len(new_rels) - keep
        new_rels = new_rels[:keep]
    if new_rels:
        _insert_bank_images(bank_id, folder, new_rels)
        db.session.commit()
    return _remember_sync(bank_id, now, {
        'added': len(new_rels),
        'missing': sum(1 for k in known if k not in seen),
        'unavailable': False, 'error': None,
        # Reported every time so the UI can phrase a partial add honestly.
        'not_added': not_added, 'limit': BANK_MAX_FILES})


def _remember_sync(bank_id, at, result) -> dict:
    _folder_sync[bank_id] = {'at': at, 'result': result}
    return dict(result)


def refresh_banks(user_id, force=False) -> dict:
    """refresh_bank() over every bank of the user — {bank_id: result}. Used by
    the bank list, which is loaded when the user NAVIGATES to the page (never
    polled), so it forces the walk: opening the tab right after dropping files
    in a folder must show them, and the cooldown would swallow that. Measured on
    a real library of 6 banks / 22 000 images: ~175 ms in total, the bulk of it
    one 15 800-image bank. A bank whose folder is unavailable simply reports it;
    it never fails the list."""
    out = {}
    ids = [row.id for row in ImageBank.query.with_entities(ImageBank.id)
           .filter_by(user_id=user_id).all()]
    for bank_id in ids:
        res = refresh_bank(user_id, bank_id, force=force)
        if res is not None:
            out[bank_id] = res
    return out


# --- relocate ---------------------------------------------------------------
_MISSING_SAMPLE = 8         # relpaths quoted back so the user can recognise them


class BankRelocateMismatch(ValueError):
    """The candidate folder holds none of the bank's files. Carries the counts
    so the route can report them instead of a bare sentence."""
    def __init__(self, message, preview):
        super().__init__(message)
        self.preview = preview


def _relocate_target(folder) -> str:
    """Normalise a pasted folder into an absolute path we can walk. Same
    unquoting nicety as create_bank (Windows «Copy as path» pastes quoted)."""
    folder = (folder or '').strip().strip('"\'')
    if not folder:
        raise ValueError('a folder is required')
    if not os.path.isdir(folder):
        raise ValueError(f'folder not found or not readable: {folder}')
    # Relocation is the SAME door as creation, just later: repointing a bank at a
    # dataset's storage folder shares the files exactly as creating it there
    # would. Refused in the dry run too, so the dialog never offers the move.
    conflict = path_guard.dataset_folder_conflict(folder)
    if conflict:
        raise ValueError(conflict['message'])
    return os.path.realpath(folder)


def relocate_preview(user_id, bank_id, folder) -> dict:
    """Dry-run a relocation: how much of THIS bank is in THAT folder?

    Nothing is written. Every known relpath is looked up under the candidate
    folder (one os.walk, matched case-insensitively through normcase — same
    keying as refresh_bank, so a drive letter or a folder re-created in another
    case still counts as the same tree). Returns {folder, total, found, missing,
    missing_sample, extra, same_folder}; ValueError on an unknown bank/folder.

    The point of the two numbers is that the user decides: a bank moved whole
    reads 29 759 found / 0 missing, and a mistyped folder reads 0 / 29 759 — a
    distinction the caller must never make silently on their behalf."""
    bank = get_bank(user_id, bank_id)
    if bank is None:
        raise ValueError('bank not found')
    target = _relocate_target(folder)
    known = {}
    for (rel,) in db.session.query(BankImage.relpath).filter_by(bank_id=bank_id):
        known.setdefault(os.path.normcase(rel), rel)
    seen = set()
    for root, _dirs, files in os.walk(target, onerror=lambda _e: None):
        for f in files:
            if f.lower().endswith(IMG_EXTS):
                seen.add(os.path.normcase(
                    os.path.relpath(os.path.join(root, f), target)))
    hit = seen & set(known)
    gone = sorted(known[k] for k in set(known) - hit)
    return {
        'folder': target,
        'total': len(known),
        'found': len(hit),
        'missing': len(gone),
        'missing_sample': gone[:_MISSING_SAMPLE],
        'extra': len(seen - hit),
        'same_folder': os.path.normcase(target) == os.path.normcase(
            os.path.realpath(bank.source_path or '')),
    }


def relocate_bank(user_id, bank_id, folder, confirm=False) -> dict:
    """Point a bank at a NEW folder, keeping every row and every analysis.

    Moving a bank costs nothing by construction: BankImage.relpath is relative
    to source_path, and scores / dhash / duplicate groups / face verdicts /
    captions / keep-reject decisions all hang off the row id. So this only
    rewrites ONE string — the danger is never the write, it is aiming it wrong.

    Hence: no call applies anything without ``confirm``; a folder that holds
    NONE of the bank's files is refused outright (that is a different folder,
    not a moved one); and a partial match goes through but deletes nothing —
    rows whose file did not come along keep their analysis and simply read as
    missing in the folder-sync note. Returns the preview dict plus
    {'applied', 'needs_confirm', 'overlaps'}."""
    if bank_jobs.running(bank_id):
        raise bank_jobs.BankJobBusy(bank_jobs.get(bank_id)['kind'])
    out = relocate_preview(user_id, bank_id, folder)
    out['needs_confirm'] = out['missing'] > 0
    out['applied'] = False
    if out['total'] and not out['found']:
        raise BankRelocateMismatch(
            'none of this bank\'s '
            f"{out['total']} image(s) are in that folder — it does not look "
            'like this bank. Pick the folder that CONTAINS the images '
            '(the one you moved), not its parent.', out)
    if not confirm:
        return out
    bank = get_bank(user_id, bank_id)
    bank.source_path = out['folder']
    db.session.commit()
    _folder_sync.pop(bank_id, None)     # next walk must see the new folder
    out['applied'] = True
    out['overlaps'] = overlapping_banks(user_id, bank_id)
    return out


def _is_imported_source(path) -> bool:
    """True when the bank's folder is one WE made ("Import to bank"), i.e. it sits
    under bank_sources_root — as opposed to a folder of the user's own that a bank
    merely points at, which we must never touch."""
    try:
        root = os.path.realpath(cfg.bank_sources_root())
        p = os.path.realpath(str(path or ''))
        # commonpath RAISES on Windows when the two paths sit on different drives
        # ("Paths don't have the same drive") — and a bank pointing at another disk
        # is precisely the common case. Raising here turned every such delete into
        # a 500. Different drive == certainly not under our root, so: False.
        return bool(p) and os.path.commonpath([root, p]) == root and p != root
    except (OSError, ValueError):
        return False


def delete_bank(user_id, bank_id) -> bool:
    """Drop the bank's ROWS and working data (thumbs + face cache). A folder of the
    user's OWN and its images are never touched.

    The one exception is a bank built by "Import to bank": its folder is a copy WE
    made under bank_sources_root, so deleting the bank must take it too — otherwise
    a full duplicate of the dataset stays on disk forever with nothing in the UI
    pointing at it. It goes to Trash, not unlink, so it stays recoverable."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return False
    if bank_jobs.running(bank_id):
        bank_jobs.cancel(bank_id)
    imported_source = bank.source_path if _is_imported_source(bank.source_path) else None
    from . import folder_person
    folder_person.drop_for_bank(bank_id)   # children first — no relationship()
    folder_person.drop_probes_for_bank(bank_id)
    BankImage.query.filter_by(bank_id=bank_id).delete(synchronize_session=False)
    db.session.delete(bank)
    db.session.commit()
    bank_undo.clear(bank_id)     # its rows are gone; a stale offer would outlive them
    reset_score_memo()           # ~45 MB of embeddings for a bank that no longer is
    shutil.rmtree(_bank_dir(bank_id), ignore_errors=True)
    if imported_source and os.path.isdir(imported_source):
        try:
            trash.send_to_trash(imported_source, context=f'bank-{bank_id}')
        except OSError:
            logger.warning('delete_bank: could not trash the imported copy %s',
                           imported_source, exc_info=True)
    return True


# --- flags & payloads -------------------------------------------------------
def image_flags(row: BankImage, th: dict) -> list:
    """Threshold verdicts for one image, recomputed from the raw scores."""
    if row.quality_state == 'unreadable':
        return ['unreadable']
    flags = []
    if row.quality_state == 'ok':
        if row.blur_score is not None and row.blur_score < th['sharpness_min']:
            flags.append('blur')
        if row.noise_score is not None and row.noise_score > th['noise_max']:
            flags.append('noise')
        if row.uniformity_score is not None and row.uniformity_score < th['uniformity_min']:
            flags.append('uniform')
        if row.width and row.height and min(row.width, row.height) < th['min_side']:
            flags.append('small')
        # Effective resolution — the picture stops before the pixels do. Same
        # read-time-verdict philosophy as blur: raw score in, threshold applied
        # here, so retuning detail_min re-sorts the bank with no rescan.
        if row.detail_ratio is not None and row.detail_ratio < th['detail_min']:
            flags.append('soft_detail')
        if row.bars_ratio is not None and row.bars_ratio > th['bars_max']:
            flags.append('bars')
    # V2 scoring flags — derived from the persisted scores against the live
    # thresholds too, but NOT gated on the quality state (a watermarked or NSFW
    # image can be perfectly sharp). Only present once the relevant pass has run.
    if row.aesthetic_score is not None and row.aesthetic_score < th['aesthetic_min']:
        flags.append('low_aesthetic')
    if row.nsfw_score is not None and row.nsfw_score > th['nsfw_max']:
        flags.append('nsfw')
    if row.watermark_state == 'detected':
        flags.append('watermark')
    return flags


def _promoted_dataset_by_image(image_ids) -> dict:
    """{bank_image_id: dataset_id} for the images a dataset REALLY holds right
    now, read off the back-links. Only the ids of the page being rendered, so a
    30 000-image bank still costs one small query. An image promoted into
    several datasets reports the lowest id — the ⬆ badge only says THAT it
    landed somewhere, and a stable pick keeps the grid from flickering."""
    out: dict = {}
    ids = [int(i) for i in image_ids]
    for i0 in range(0, len(ids), _SQL_IN_CHUNK):
        rows = (db.session.query(FaceDatasetImage.bank_image_id,
                                 func.min(FaceDatasetImage.dataset_id))
                .filter(FaceDatasetImage.bank_image_id.in_(ids[i0:i0 + _SQL_IN_CHUNK]))
                .group_by(FaceDatasetImage.bank_image_id).all())
        out.update({bid: ds for bid, ds in rows})
    return out


def _page_images(rows, th: dict) -> list:
    """One page of grid payloads, with the ⬆ promoted state resolved in a single
    extra query for the whole page (never one per row)."""
    promoted_by = _promoted_dataset_by_image([r.id for r in rows])
    return [_image_dict(r, th, promoted_by) for r in rows]


def _image_dict(row: BankImage, th: dict, promoted_by: dict | None = None) -> dict:
    # ⬆ promoted = the dataset that holds this image TODAY (back-link), falling
    # back to the legacy one-way flag for promotions that predate it. Deriving it
    # means the badge disappears when the user deletes the image in the dataset,
    # instead of advertising a copy that is gone.
    promoted = (promoted_by or {}).get(row.id, row.promoted_dataset_id)
    # A quarter turn transposes what the user SEES. The columns keep the source's
    # own numbers (a re-scan rewrites them from the file, which never changed), so
    # the swap happens here, at read time — the payload can never drift out of
    # sync with the stored angle.
    rotation = int(row.rotation or 0) % 360
    width, height = ((row.height, row.width) if rotation in (90, 270)
                     else (row.width, row.height))
    # The mask editor's seed, carried ONLY on the rows that can open it: a bank
    # page is thousands of images and the other 99% would pay for three null keys.
    mask = {}
    if row.watermark_state == 'detected' or row.watermark_regions is not None:
        import json as _json
        try:
            bbox = _json.loads(row.watermark_bbox or '')
        except (ValueError, TypeError):
            bbox = None
        mask = {'watermark_bbox': bbox if isinstance(bbox, list) and len(bbox) == 4
                else None,
                **_watermark_regions_payload(row)}
    return {
        **mask,
        'id': row.id,
        'name': os.path.basename(row.relpath),
        'relpath': row.relpath,
        'rotation': rotation,
        'width': width, 'height': height, 'file_size': row.file_size,
        'quality_state': row.quality_state,
        'blur_score': row.blur_score, 'noise_score': row.noise_score,
        'uniformity_score': row.uniformity_score,
        'aesthetic_score': row.aesthetic_score, 'nsfw_score': row.nsfw_score,
        'style_cluster': row.style_cluster, 'watermark_state': row.watermark_state,
        'watermark_clean_method': row.watermark_clean_method,
        # Who ruled on THIS image, and with what score. Per image rather than per
        # bank because a bank scanned over weeks holds both routes' verdicts, and
        # "why is this one flagged?" is asked about one tile, not about a bank.
        # NULL source = scanned before the app recorded it; NULL score = the
        # vision route, which writes a sentence and not a number.
        'watermark_source': row.watermark_source,
        'watermark_score': row.watermark_score,
        'detail_ratio': row.detail_ratio, 'bars_ratio': row.bars_ratio,
        'jpeg_quality': row.jpeg_quality,
        'origin': row.origin, 'origin_evidence': row.origin_evidence,
        'subfolder': _subfolder_of(row.relpath),
        'flags': image_flags(row, th),
        'dup_group': row.dup_group,
        'semantic_dup_group': row.semantic_dup_group,
        'face_state': row.face_state, 'face_cluster': row.face_cluster,
        # 'asserted' = the person id came from the user's "this subfolder is one
        # person", not from an embedding. The grid says so rather than passing a
        # declaration off as a measurement.
        'face_cluster_origin': row.face_cluster_origin,
        'framing': row.framing,
        # 🎨 what the picture is made of, and how sure the classifier was. The
        # margin travels with the verdict on purpose: a tile badge that cannot
        # show its own confidence is how a guess becomes a fact.
        'medium': row.medium, 'medium_margin': row.medium_margin,
        # ⤢ the raw head yaw in degrees, signed as the detector reports it. The
        # BUCKET is not stored here — it is derived from this number by the same
        # two cuts the SQL uses, so a re-tune can never leave the badge and the
        # chip disagreeing.
        'face_yaw': row.face_yaw,
        'status': row.status, 'reject_reason': row.reject_reason,
        'promoted_dataset_id': promoted,
        # The OTHER destination. Kept as its own key rather than overloading the
        # dataset one, which is stored in user databases and read as a dataset id.
        'promoted_bank_id': row.promoted_bank_id,
        'caption': row.caption,
    }


def _flag_filter(flag: str, th: dict):
    """SQLAlchemy criterion for one flag name (mirrors image_flags)."""
    if flag == 'unreadable':
        return BankImage.quality_state == 'unreadable'
    # V2 scoring flags — not gated on quality_state (see image_flags) and only
    # true where the score actually exists (a NULL score is "not scored", never
    # "below threshold"). watermark is a discrete state, no threshold column.
    if flag == 'low_aesthetic':
        return and_(BankImage.aesthetic_score.isnot(None),
                    BankImage.aesthetic_score < th['aesthetic_min'])
    if flag == 'nsfw':
        return and_(BankImage.nsfw_score.isnot(None),
                    BankImage.nsfw_score > th['nsfw_max'])
    if flag == 'watermark':
        return BankImage.watermark_state == 'detected'
    ok = BankImage.quality_state == 'ok'
    crit = {
        'blur': BankImage.blur_score < th['sharpness_min'],
        'noise': BankImage.noise_score > th['noise_max'],
        'uniform': BankImage.uniformity_score < th['uniformity_min'],
        'small': or_(BankImage.width < th['min_side'],
                     BankImage.height < th['min_side']),
        # NULL-safe: a row scanned before the provenance pass existed carries no
        # score, and "not measured" must never read as "below threshold".
        'soft_detail': and_(BankImage.detail_ratio.isnot(None),
                            BankImage.detail_ratio < th['detail_min']),
        'bars': and_(BankImage.bars_ratio.isnot(None),
                     BankImage.bars_ratio > th['bars_max']),
    }.get(flag)
    return (ok & crit) if crit is not None else None


_QUALITY_FLAGS = ('blur', 'noise', 'uniform', 'small', 'soft_detail', 'bars',
                  'unreadable')
# V2 score-derived flags. Kept separate from _QUALITY_FLAGS so the "flagged" /
# "clean" quality aggregate stays about the CPU quality pass, while these count
# and filter independently (each only meaningful once its pass has run).
_SCORE_FLAGS = ('low_aesthetic', 'nsfw', 'watermark')

# Resolution tiers for the Bank grid — bucketed on MEGAPIXELS (width×height, the
# same rank as the resolution sort) so a mixed dump can be skimmed and mass-acted
# one tier at a time. Each entry is (stable_id, lo, hi) in raw pixels, a HALF-OPEN
# [lo, hi) range (lower-inclusive, upper-exclusive); hi=None means "no ceiling".
# So a 1000×1000 (1.00 MP) and a 1024×1024 (1.05 MP) both land in 'res_1_2', and a
# 2000×2000 (4.00 MP) lands in 'res_gt_4'. The 0.25 MP floor (not 0.30) is chosen
# so a 512×512 (0.26 MP) — a legit small training crop — sits in '0.25–1 MP', while
# only true junk (Telegram thumbnails ~0.1–0.2 MP, ≤448²) falls in '< 0.25 MP'.
# Ids are user-facing filter keys — never rename without an alias.
_RES_BUCKETS = (
    ('res_lt_025', 0, 250_000),
    ('res_025_1', 250_000, 1_000_000),
    ('res_1_2', 1_000_000, 2_000_000),
    ('res_2_4', 2_000_000, 4_000_000),
    ('res_gt_4', 4_000_000, None),
)
_RES_BOUNDS = {bid: (lo, hi) for bid, lo, hi in _RES_BUCKETS}

# Framing buckets — the SAME four shot types the datasets classify (face close-up,
# bust, full body, back view). 'unknown' is a parseable-but-not-one-of-four answer;
# it counts and filters but is never a training target. Ids are user-facing filter
# keys — never rename without an alias. The built-in character composition aims for
# a 12/6/6/1 face/bust/body/back mix; the coverage advice phrases against that
# proportion, never as a hard rule.
_FRAMINGS = ('face', 'bust', 'body', 'back')
_FRAMING_KEYS = _FRAMINGS + ('unknown',)
_FRAMING_TARGET = {'face': 12, 'bust': 6, 'body': 6, 'back': 1}


# --- 🎨 Medium: what the picture is MADE OF ---------------------------------
# A DIFFERENT question from `origin`, which reads the file's metadata. origin
# answers "who made this file" (a generator, a camera, or — usually — nobody can
# tell); medium answers "what does this picture look like it is". An AI-generated
# photorealistic portrait is origin='ai' AND medium='photo'; a scanned manga page
# is origin='unknown' AND medium='anime'. Neither implies the other and the UI
# must never present one as evidence for the other.
#
# Ids are user-facing filter keys AND stored column values — never rename one
# without an alias.
MEDIUMS = ('photo', 'anime', 'render3d', 'illustration')
MEDIUM_KEYS = MEDIUMS + ('unsure',)

# Zero-shot CLIP prototypes. Each bucket is the MEAN of its phrases, re-normed
# (standard prompt ensembling) — one vector per bucket, encoded ONCE per install
# and then cached on disk forever by clip_text_encoder.
#
# The two keys starting with '_' are DISTRACTORS and are deliberately NOT
# buckets: a forced four-way choice has no way to say "none of these", so every
# banner, website screenshot and thumbnail collage in a scrape dump had to land
# in one of the four — measured, that was the single biggest source of wrong
# verdicts (a '3D render' pile that was mostly text banners). Giving the junk
# somewhere honest to go and mapping it to 'unsure' removed 769 wrong verdicts
# out of 23 532 images on the reference bank without costing a single right one.
MEDIUM_PROTOTYPES = {
    'photo': ('a photograph', 'a photo of a real person',
              'a photograph taken with a camera', 'a real-life photo',
              'a candid snapshot of real people'),
    'anime': ('an anime drawing', 'an anime style illustration', 'a manga panel',
              'a cartoon character drawn in anime style', 'anime artwork'),
    'render3d': ('a 3D render', 'a 3D computer graphics render', 'a CGI render',
                 'a rendered 3D character', 'a videogame screenshot'),
    'illustration': ('an illustration', 'a digital painting', 'a pencil drawing',
                     'a painted artwork', 'a comic book drawing'),
    '_text': ('a text banner', 'a poster with large text', 'a logo',
              'an advertisement banner with writing', 'a page of text'),
    '_screen': ('a screenshot of a website', 'a screenshot of an app interface',
                'a computer desktop screenshot', 'a collage of thumbnails',
                'a photo grid montage'),
}

# The two cuts that turn a ranking into a VERDICT, and the reason they are not
# one number. Both are a cosine MARGIN — the winning prototype's similarity minus
# the runner-up's — never an absolute similarity, because this project has
# already measured (see search_by_text) that no absolute CLIP cut separates
# "relevant" from "unrelated" on a real corpus.
#
# MEASURED, on the reference machine's 23 532-image bank, against 167 images
# labelled BY EYE from contact sheets (100 uniformly random + the 25 strongest
# candidates of each non-photo bucket):
#   * at no cut at all, the four-way argmax is 99/100 right on the random sample
#     but only 2/25 right on its own top 'anime' picks and 4/25 on 'render3d' —
#     because CLIP reads a picture's SUBJECT as much as its medium, so a
#     photograph of somebody cosplaying an anime character scores as 'anime'.
#     That confusion is the whole reason the non-photo bar is where it is.
#   * photo verdicts survive a low bar: 0.005 keeps 90 of the 159 photographs
#     and got none of them wrong.
#   * non-photo verdicts need a bar six times higher: at 0.030 the pass named the
#     2 real anime drawings and nothing else, with zero false positives; at 0.020
#     it also named 3 cosplay photographs and a text banner.
# The result is a classifier that is almost never wrong and often silent — which
# is the trade this app takes everywhere else too. On that bank it answers
# photo for 21 138 images, anime for 2, and 'unsure' for 2 392. The 'unsure'
# pile is a REAL answer, and the UI says how big it is rather than hiding it.
MEDIUM_MARGIN_PHOTO = 0.005
MEDIUM_MARGIN_OTHER = 0.030


def medium_verdict(sims: dict) -> tuple:
    """(medium, margin) from {bucket: cosine} — the ONE place the cuts are
    applied, so the pass, the tests and any future re-tune read the same rule.

    A distractor winning, or a margin under this bucket's cut, is 'unsure'. The
    margin is returned either way: it is what makes the verdict re-tunable
    without recomputing a single embedding."""
    ranked = sorted(sims.items(), key=lambda kv: -kv[1])
    if len(ranked) < 2:
        return 'unsure', None
    name, best = ranked[0]
    margin = float(best - ranked[1][1])
    if name.startswith('_'):
        return 'unsure', margin
    cut = MEDIUM_MARGIN_PHOTO if name == 'photo' else MEDIUM_MARGIN_OTHER
    return (name if margin >= cut else 'unsure'), margin


def _medium_counts(bank_id) -> dict:
    """Per-bucket image counts for the 🎨 Medium chips in ONE GROUP BY. Rows with
    a NULL medium (never classified — no ✨ Score embedding to read) are excluded:
    "not classified yet" is a different statement from "unsure", and merging them
    would let an unrun pass look like an undecided one."""
    q = (db.session.query(BankImage.medium, func.count(BankImage.id))
         .filter(BankImage.bank_id == bank_id, BankImage.medium.isnot(None)))
    got = {k: n for k, n in q.group_by(BankImage.medium).all()}
    return {k: int(got.get(k, 0)) for k in MEDIUM_KEYS}


# --- ⤢ Angle: where the head is pointing ------------------------------------
# Measured IN THE PIXELS by the 🎭 Faces pass (InsightFace/antelopev2 estimates a
# head pose from its five landmarks), never guessed from a caption. Only the
# ABSOLUTE yaw is ever read: "turned left" and "turned right" are the same shot
# type for a training set, and treating them as two would halve every count for
# no gain.
#
# Ids are user-facing filter keys — never rename without an alias.
ANGLES = ('frontal', 'three_quarter', 'profile', 'behind')

# MEASURED on 144 randomly sampled face-scanned images of the reference bank,
# laid out in |yaw| order and read off contact sheets:
#   * 0-15°  nothing reads as turned at all;
#   * 16-25° the turn becomes visible around 20°, which is where the eye puts the
#     boundary — so 20 is kept (it was also the starting hypothesis, and here the
#     measurement agrees with it instead of the usual other way round);
#   * 26-50° unmistakably three-quarter, both eyes still visible at 47°;
#   * the sample contains NO face between 57.0° and 73.7°, and the four faces
#     above 73° are true profiles. Any cut inside that empty band is equally
#     supported by this data; 60 sits in the middle of it.
# Distribution obtained with these two numbers: 60% frontal, 38% three-quarter,
# 3% profile (n=144, |yaw| median 16.1°, p95 40.8°, max 78.8°).
#
# KNOWN LIMIT, and it is not small: a head turned far enough that one eye is
# hidden often defeats the DETECTOR, so the hardest profiles never reach this
# column at all — they come back as 'no_face' and count as "not measured". The
# 'profile' bucket therefore under-counts, and the UI says so instead of
# presenting 3% as the truth about a bank.
ANGLE_FRONTAL_MAX = 20.0
ANGLE_PROFILE_MIN = 60.0

# What one image costs the ⤢ backfill, in seconds — antelopev2 on the CPU path,
# measured at ~2 s/image over 144 images on the reference machine. Used ONLY to
# price the offer before the click; a slow machine takes longer and the wording
# says "about".
ANGLE_BACKFILL_S_PER_IMAGE = 2.0


def _angle_case():
    """A single SQL CASE mapping each row to its angle bucket id, or NULL for
    "not measured". Used to COUNT (one GROUP BY) and to FILTER, so the chips and
    the grid can never disagree about what a bucket contains.

    'behind' is the one bucket that is not a yaw: a back view has no face to
    measure, so it is the crossing of two facts the app ALREADY holds — the 🎭
    Faces pass found no face AND the 📐 Framing pass called the shot a back view.
    Requiring both is what keeps a landscape with nobody in it out of a bucket
    that claims a person is present; the cost is that 'behind' stays empty until
    BOTH passes have run, which the UI states rather than hides."""
    yaw = func.abs(BankImage.face_yaw)
    return case(
        (BankImage.face_yaw.isnot(None), case(
            (yaw < ANGLE_FRONTAL_MAX, 'frontal'),
            (yaw < ANGLE_PROFILE_MIN, 'three_quarter'),
            else_='profile')),
        ((BankImage.face_state == 'no_face') & (BankImage.framing == 'back'),
         'behind'),
        else_=None)


def _angle_counts(bank_id) -> dict:
    """Per-bucket image counts for the ⤢ Angle chips in ONE GROUP BY. Rows the
    CASE maps to NULL (no yaw, and not a proven back view) are "not measured" and
    are counted separately by bank_payload, never folded into 'frontal'."""
    bucket = _angle_case()
    rows = (db.session.query(bucket, func.count(BankImage.id))
            .filter(BankImage.bank_id == bank_id)
            .group_by(bucket).all())
    got = {k: n for k, n in rows if k is not None}
    return {k: int(got.get(k, 0)) for k in ANGLES}


def _framing_counts(bank_id, extra_crit=None) -> dict:
    """Per-bucket image counts for the 📐 Framing chips in ONE GROUP BY. Rows with
    a NULL framing (not classified) are excluded, so every key is present with a
    real count. ``extra_crit`` narrows the pool (e.g. status='keep' for coverage)."""
    q = (db.session.query(BankImage.framing, func.count(BankImage.id))
         .filter(BankImage.bank_id == bank_id, BankImage.framing.isnot(None)))
    if extra_crit is not None:
        q = q.filter(extra_crit)
    got = {k: n for k, n in q.group_by(BankImage.framing).all()}
    return {k: int(got.get(k, 0)) for k in _FRAMING_KEYS}


def _origin_counts(bank_id) -> dict:
    """Per-state image counts for the 🔎 Origin chips in ONE GROUP BY.

    Every state of ORIGINS is always present with a real count, INCLUDING
    'unknown' — which is the honest majority answer on any scraped or chat-sourced
    bank (measured: 3000/3000 on a real Telegram export) and has to be visible as
    such. Rows with a NULL origin (scanned before this pass existed, or
    unreadable) are excluded: they are "not measured", a different thing again."""
    q = (db.session.query(BankImage.origin, func.count(BankImage.id))
         .filter(BankImage.bank_id == bank_id, BankImage.origin.isnot(None)))
    got = {k: n for k, n in q.group_by(BankImage.origin).all()}
    return {k: int(got.get(k, 0)) for k in ORIGINS}


def _subfolder_of(relpath: str) -> str:
    """Top-level subfolder of a bank-relative path ('' for a root-level file) —
    the natural scoping axis for a Telegram export (one folder per chat/date)."""
    parts = (relpath or '').replace('\\', '/').split('/', 1)
    return parts[0] if len(parts) > 1 else ''


def _unresolved_dup_groups_q(bank_id, col=BankImage.dup_group):
    """Groups still holding ≥2 NON-rejected members — i.e. still to resolve. ``col``
    selects the stage: dup_group (exact/resized) or semantic_dup_group (crops)."""
    return (db.session.query(col)
            .filter(BankImage.bank_id == bank_id,
                    col.isnot(None),
                    BankImage.status != 'reject')
            .group_by(col)
            .having(func.count(BankImage.id) >= 2))


def _res_bucket_case():
    """A single SQL CASE mapping each scanned row to its resolution-tier id, used
    both to COUNT per tier (one GROUP BY) and — via _RES_BOUNDS — to FILTER a page
    to one tier. Rows with a NULL dimension never reach this (callers pre-filter
    width/height NOT NULL), so no NULL-misfile into the top tier."""
    area = BankImage.width * BankImage.height
    whens = [(area < hi, bid) for bid, _lo, hi in _RES_BUCKETS if hi is not None]
    return case(*whens, else_=_RES_BUCKETS[-1][0])


def _res_bucket_counts(bank_id) -> dict:
    """Per-tier image counts for the resolution chips (bank-wide, like the flag
    totals) in ONE GROUP BY. Unscanned rows (width/height NULL) are excluded, so a
    tier that no image falls into simply reports 0. Every tier id is present."""
    bucket = _res_bucket_case()
    rows = (db.session.query(bucket, func.count(BankImage.id))
            .filter(BankImage.bank_id == bank_id,
                    BankImage.width.isnot(None),
                    BankImage.height.isnot(None))
            .group_by(bucket).all())
    got = {bid: n for bid, n in rows}
    return {bid: int(got.get(bid, 0)) for bid, _lo, _hi in _RES_BUCKETS}


# --- explicit grid sorts -----------------------------------------------------
# The grid can ORDER on what the passes already MEASURED, instead of only
# filtering on it (asked for by nofaceman on Discord). One entry per sortable
# quantity; the UI offers each in both directions as '<key>_desc' / '<key>_asc'.
# Ids are user-facing query values — treat them like catalog labels and never
# rename one without an alias.
#   res       megapixels (width×height) — the original sort, kept as-is.
#   aesthetic the ✨ Score pass's 1–10 rating: ↓ surfaces the keepers, ↑ the duds.
#   sharp     the 🔎 Scan pass's Laplacian variance: ↑ surfaces the blurry misses.
# The first version stopped there, reasoning that noise / uniformity / bars /
# detail_ratio / NSFW each already have a CHIP that filters and orders worst-first.
# That reasoning does not survive contact with a real dump (asked again on
# Discord): a chip only ranks the rows that CROSS its threshold, so "the noisiest
# images I am keeping" — every one of them under the threshold — was unreachable,
# and no chip ranks the other way at all ("the cleanest first", "the safest
# first"). Sorting is not filtering, so the two do not duplicate each other; the
# precedent was already in this table, since 'sharp' coexists with the blur chip
# and 'res' with the small chip. So: EVERY quantity a pass persists on bank_image
# is sortable, both ways. The menu is grouped by pass in the UI to stay readable.
#   noise/flat/detail/bars/jpeg  the 🔎 Scan + provenance passes' raw figures.
#   nsfw                         the ✨ Score pass's 0–1 probability.
#   face                         the 🎭 Face pass's detection confidence.
#   size                         bytes on disk — the one figure NO chip exposes.
# Deliberately still NOT here: anything that is a LABEL rather than a measure
# (framing, origin, cluster and group ids, watermark/quality state). Those are
# facets — ordering by an id number means nothing to a reviewer.
_SORT_KEYS = {
    'aesthetic': lambda: BankImage.aesthetic_score,
    'sharp': lambda: BankImage.blur_score,
    'res': lambda: BankImage.width * BankImage.height,
    'noise': lambda: BankImage.noise_score,
    'flat': lambda: BankImage.uniformity_score,
    'detail': lambda: BankImage.detail_ratio,
    'bars': lambda: BankImage.bars_ratio,
    'jpeg': lambda: BankImage.jpeg_quality,
    'nsfw': lambda: BankImage.nsfw_score,
    'face': lambda: BankImage.face_det,
    'size': lambda: BankImage.file_size,
    #   yaw          the 🎭 Faces pass's head yaw, read as an ABSOLUTE angle so
    #                the two directions mean "most turned away" / "most
    #                face-on" rather than "turned left" / "turned right", which
    #                is not a distinction a training set cares about.
    'yaw': lambda: func.abs(BankImage.face_yaw),
    #   medium_conf  the 🎨 Medium pass's confidence gap. ↑ is the useful one: it
    #                opens on the images the classifier nearly could not call,
    #                which is exactly the pile a human should check by hand.
    'medium_conf': lambda: BankImage.medium_margin,
}
# Menu order (the UI renders it in this order); ids are stored query values, so a
# key may be added here but never renamed without an alias.
_SORT_ORDER = ('res', 'size', 'aesthetic', 'nsfw', 'sharp', 'noise', 'flat',
               'detail', 'bars', 'jpeg', 'face', 'yaw', 'medium_conf')
GRID_SORTS = tuple(f'{k}_{d}' for k in _SORT_ORDER for d in ('desc', 'asc'))


def _sort_order(sort):
    """The ORDER BY tuple for an explicit grid sort, or None for 'default' and
    for anything unknown (an unrecognised value must degrade to the server's own
    order, never 500). Rows the relevant pass never reached carry NULL and sink
    to the END in BOTH directions — ordering by "is NULL" first (0 before 1)
    — because a sort that opens on the un-measured pile is worse than no sort.
    Tie-break on id so a page boundary is stable."""
    key, _, direction = (sort or '').rpartition('_')
    if direction not in ('asc', 'desc') or key not in _SORT_KEYS:
        return None
    col = _SORT_KEYS[key]()
    ranked = col.desc() if direction == 'desc' else col.asc()
    return (col.is_(None).asc(), ranked, BankImage.id.asc())


def _flag_counts(bank_id, th) -> tuple[dict, dict]:
    """Two per-flag maps, because the UI asks two different questions of them.

    ``flags[f]``      — every image in the bank carrying the flag, whatever its
                        status. This is the FACET number: clicking the chip shows
                        exactly these rows, rejected ones included.
    ``actionable[f]`` — what a 🧹 Auto-reject on that flag would really flip.
                        ``apply_flags`` only ever touches ``status='pending'``
                        (its contract: a manual — or an earlier automatic — ✓/✕
                        is never overridden), so it is the same criterion
                        narrowed to the undecided pile.

    The two coincide on a bank nothing has been decided on yet, and diverge the
    moment one pass has run — which is exactly when the user starts trusting the
    number. Measured on a real 99 000-image bank at its SECOND pass: the button
    offered "5 930 flagged" for blur and rejected 0, because all 5 930 had been
    rejected by the first pass. Reading that as "the feature is broken" is the
    only reasonable conclusion, and it was the counter's fault, not the pass's.

    One query per flag, not two: the pending half rides along as a conditional
    SUM, so telling the truth costs nothing extra on a 100 000-image bank."""
    flags, actionable = {}, {}
    for flag in _QUALITY_FLAGS + _SCORE_FLAGS:
        crit = _flag_filter(flag, th)
        if crit is None:
            flags[flag] = actionable[flag] = 0
            continue
        total, pending = (
            db.session.query(
                func.count(BankImage.id),
                func.coalesce(
                    func.sum(case((BankImage.status == 'pending', 1), else_=0)), 0))
            .filter(BankImage.bank_id == bank_id).filter(crit).one())
        flags[flag] = int(total or 0)
        actionable[flag] = int(pending or 0)
    return flags, actionable


def bank_payload(user_id, bank_id) -> dict | None:
    """Everything the bank workspace needs on one poll: counts, flag totals,
    duplicate/cluster summaries, live job, thresholds."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    th = thresholds()
    base = BankImage.query.filter_by(bank_id=bank_id)
    total = base.count()
    # 🏷️ What each caption SCOPE would really caption: in that status AND still
    # without a caption. NOT counts.keep / counts.pending — the pass skips rows
    # that already have one, so quoting the status total would advertise a number
    # the run does not act on. That exact mistake was paid for once already by the
    # 🧹 Auto-reject counter (see _flag_counts): a button that offers "5 930" and
    # moves 0 reads as a broken feature, and it is the counter's fault. One query,
    # two conditional sums, so telling the truth costs nothing on a 100 000-image
    # bank.
    #
    # THREE figures per pile, not one, because 🔄 Re-caption has three different
    # things to say and folding any two of them would be a lie of a familiar kind:
    #   caption_todo_*     : no caption at all — what a normal pass writes;
    #   caption_asserted_* : a caption a HUMAN wrote — what a forced pass now SKIPS
    #                        (services/caption_origin.py), so "keeping the 3 you
    #                        wrote" is a measured number and not a hope;
    #   caption_unrecorded_*: a caption whose author was never recorded — rewritten
    #                        like any other, but it is NOT "machine-written", and
    #                        the screen must not claim it is.
    # Whatever is left (pile − the three) is machine-written and rewritten in silence.
    def _cap_sum(status, condition):
        return func.coalesce(func.sum(
            case((and_(BankImage.status == status, condition), 1), else_=0)), 0)

    no_caption = or_(BankImage.caption.is_(None), BankImage.caption == '')
    asserted = caption_origin.protected_clause(BankImage)
    unrecorded = caption_origin.unrecorded_clause(BankImage)
    (todo_keep, todo_pending, asserted_keep, asserted_pending,
     unrecorded_keep, unrecorded_pending) = (
        db.session.query(
            _cap_sum('keep', no_caption), _cap_sum('pending', no_caption),
            _cap_sum('keep', asserted), _cap_sum('pending', asserted),
            _cap_sum('keep', unrecorded), _cap_sum('pending', unrecorded))
        .filter(BankImage.bank_id == bank_id).one())
    counts = {
        'total': total,
        'scanned': base.filter(BankImage.quality_state.isnot(None)).count(),
        # The blind spot, named. An image no quality pass ever measured carries
        # no verdict, and EVERY quality flag is gated on `quality_state == 'ok'`
        # (see _flag_filter) — so these rows are structurally unreachable by
        # 🧹 Auto-reject. That is not "they are clean": it is "we know nothing
        # about them", and the two must never render as the same 0.
        'unscanned': base.filter(BankImage.quality_state.is_(None)).count(),
        # ...and how many of those a 🔎 Scan would actually pick up. Rejected
        # rows are out of the scan pool (_scan_pool), so the two numbers differ
        # by exactly the images that were thrown away before being measured. The
        # UI offers the gesture, so it quotes the number the gesture moves.
        'unscanned_scannable': base.filter(BankImage.quality_state.is_(None),
                                           BankImage.status != 'reject').count(),
        'pending': base.filter_by(status='pending').count(),
        'keep': base.filter_by(status='keep').count(),
        'reject': base.filter_by(status='reject').count(),
        # …and the caption-pass sizes of the two scopes it can be aimed at.
        'caption_todo_keep': int(todo_keep or 0),
        'caption_todo_pending': int(todo_pending or 0),
        # …and the two figures 🔄 Re-caption needs to stop lumping "what you wrote"
        # together with "what nobody recorded".
        'caption_asserted_keep': int(asserted_keep or 0),
        'caption_asserted_pending': int(asserted_pending or 0),
        'caption_unrecorded_keep': int(unrecorded_keep or 0),
        'caption_unrecorded_pending': int(unrecorded_pending or 0),
        # Images a dataset REALLY holds today (back-link), plus the ones promoted
        # before that link existed (legacy flag). Counting the flag alone kept
        # advertising copies the user had since deleted.
        'promoted': base.filter(or_(
            BankImage.promoted_dataset_id.isnot(None),
            # ...or into another BANK, the second destination. Counted here so
            # the "promoted" stat and the ⬆ badge on the tiles never disagree.
            BankImage.promoted_bank_id.isnot(None),
            BankImage.id.in_(db.session.query(FaceDatasetImage.bank_image_id)
                             .filter(FaceDatasetImage.bank_image_id.isnot(None))),
        )).count(),
        # V2 pass progress — how many images the scoring / watermark passes reached
        # (so the UI can show "scored 0/9000" and enable the threshold facets).
        'scored': base.filter(or_(BankImage.aesthetic_score.isnot(None),
                                  BankImage.nsfw_score.isnot(None))).count(),
        'watermark_scanned': base.filter(BankImage.watermark_state.isnot(None)).count(),
        'framing_classified': base.filter(BankImage.framing.isnot(None)).count(),
        # 🎨 Medium — how many rows the pass has a verdict for ('unsure'
        # included: it IS a verdict). Drives the chip row's appearance and the
        # Sort menu's "run 🎨 Medium first" state.
        'medium_classified': base.filter(BankImage.medium.isnot(None)).count(),
        # ⤢ Angle — how many rows carry a measured yaw…
        'angle_measured': base.filter(BankImage.face_yaw.isnot(None)).count(),
        # …and how many were face-scanned by a build that computed the yaw and
        # threw it away. This is the ONLY number that can offer the backfill
        # honestly: it is the exact size of the re-measure job, so the UI can
        # price the click before the user makes it instead of after.
        'angle_backfillable': base.filter(BankImage.face_state.isnot(None),
                                          BankImage.face_yaw.is_(None)).count(),
    }
    framing = _framing_counts(bank_id)
    flags, flags_actionable = _flag_counts(bank_id, th)
    res_buckets = _res_bucket_counts(bank_id)
    origins = _origin_counts(bank_id)
    dup_rows = (db.session.query(BankImage.dup_group, func.count(BankImage.id))
                .filter(BankImage.bank_id == bank_id,
                        BankImage.dup_group.isnot(None))
                .group_by(BankImage.dup_group).all())
    dup = {'groups': len(dup_rows),
           'images': sum(n for _g, n in dup_rows),
           'unresolved': _unresolved_dup_groups_q(bank_id).count()}
    # Stage-2 semantic near-duplicate groups (crops/variants), same summary shape.
    sem_rows = (db.session.query(BankImage.semantic_dup_group, func.count(BankImage.id))
                .filter(BankImage.bank_id == bank_id,
                        BankImage.semantic_dup_group.isnot(None))
                .group_by(BankImage.semantic_dup_group).all())
    semantic_dup = {
        'groups': len(sem_rows),
        'images': sum(n for _g, n in sem_rows),
        'unresolved': _unresolved_dup_groups_q(
            bank_id, BankImage.semantic_dup_group).count()}
    # Person clusters, biggest first; cover = the member with the surest face.
    cl_rows = (db.session.query(BankImage.face_cluster, func.count(BankImage.id))
               .filter(BankImage.bank_id == bank_id,
                       BankImage.face_cluster.isnot(None))
               .group_by(BankImage.face_cluster)
               .order_by(func.count(BankImage.id).desc(),
                         BankImage.face_cluster.asc())
               .limit(40).all())
    clusters = []
    for cid, size in cl_rows:
        cover = (BankImage.query
                 .filter_by(bank_id=bank_id, face_cluster=cid)
                 .order_by(BankImage.face_det.desc().nullslast(),
                           BankImage.id.asc())
                 .first())
        clusters.append({'id': cid, 'size': size,
                         'cover_image_id': cover.id if cover else None})
    faces_scanned = base.filter(BankImage.face_state.isnot(None)).count()
    # Style clusters (group by visual style), biggest first — the "group by
    # style" counterpart to the person clusters above. Cover = the lowest id of
    # the cluster (stable, no per-image quality signal to rank by here).
    st_rows = (db.session.query(BankImage.style_cluster, func.count(BankImage.id))
               .filter(BankImage.bank_id == bank_id,
                       BankImage.style_cluster.isnot(None))
               .group_by(BankImage.style_cluster)
               .order_by(func.count(BankImage.id).desc(),
                         BankImage.style_cluster.asc())
               .limit(40).all())
    style_clusters = []
    for cid, size in st_rows:
        cover = (BankImage.query
                 .filter_by(bank_id=bank_id, style_cluster=cid)
                 .order_by(BankImage.id.asc()).first())
        style_clusters.append({'id': cid, 'size': size,
                               'cover_image_id': cover.id if cover else None})
    return {
        'id': bank.id, 'name': bank.name, 'source_path': bank.source_path,
        'created_at': bank.created_at.isoformat() if bank.created_at else None,
        'counts': counts, 'flags': flags,
        # A SECOND map, not a replacement: 'flags' answers the facet's question
        # ("show me these") and 'flags_actionable' answers the button's ("how
        # many would this reject"). Overwriting the first would have broken the
        # chip row, whose count legitimately includes already-rejected images.
        'flags_actionable': flags_actionable,
        'res_buckets': res_buckets,
        'framing': framing, 'origins': origins,
        'mediums': _medium_counts(bank_id), 'angles': _angle_counts(bank_id),
        # What the ⤢ backfill would cost, in the app's own words. ~2 s/image is
        # the MEASURED cost of antelopev2 on this project's CPU path (144 images,
        # ~2 s each); it is a ballpark shown before the click, never a promise.
        'angle_backfill_minutes': max(1, round(
            counts['angle_backfillable'] * ANGLE_BACKFILL_S_PER_IMAGE / 60)
        ) if counts['angle_backfillable'] else None,
        'dup': dup,
        'semantic_dup': semantic_dup,
        'clusters': clusters, 'faces_scanned': faces_scanned,
        'style_clusters': style_clusters,
        'activity': bank_jobs.get(bank_id),
        # ↩ the one-step-back offer, so the bar survives a reload (the decision
        # it takes back is in the database, not in a tab).
        'undo': bank_undo.peek(bank_id),
        'pipeline_report': _load_pipeline_report(bank),
        'score_device': score_device_info(bank_id),
        # Non-null only on a bank created before the create-time guard, whose
        # folder IS a dataset's storage. The workspace turns it into a standing
        # banner and disables 🗑 Delete rejected, which the server refuses anyway.
        'dataset_conflict': bank_dataset_conflict(user_id, bank_id),
        'thresholds': th,
    }


def flag_preview(user_id, bank_id, overrides=None) -> dict | None:
    """Per-flag image counts for a CANDIDATE threshold set — what the bank WOULD
    look like at those numbers, without saving anything.

    This is what turns tuning a threshold from a guess into a decision: the
    quality scan persists RAW scores and every verdict is recomputed at read
    time (see BankImage's docstring), so answering "how many images would a
    sharpness floor of 140 flag?" is the same COUNT the payload already runs,
    with a different dict. No decode, no pass, no write.

    Only the read-time thresholds are meaningful here. The four grouping ones
    (dup_distance, face/style/semantic similarity) are baked into stored group
    ids by their pass, so a count against a candidate value would be a number
    about the OLD grouping — the UI says "applies at the next pass" instead.

    Unknown keys and junk values are ignored rather than 400: this is a live
    preview firing on every keystroke, and a half-typed "0." must degrade to
    "no change yet", never to an error toast."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    th = thresholds()
    for key, val in (overrides or {}).items():
        if key not in cfg.DEFAULTS['bank']:
            continue
        try:
            th[key] = float(val)
        except (TypeError, ValueError):
            continue
    th['dup_distance'] = int(th['dup_distance'])
    th['min_side'] = int(th['min_side'])
    base = BankImage.query.filter_by(bank_id=bank_id)
    # Same producer as the workspace payload, so the two can never answer the
    # same question differently — and so the panel's "before/after" line can
    # tell "would be flagged" from "would be rejected" if it ever needs to.
    flags, flags_actionable = _flag_counts(bank_id, th)
    return {'flags': flags, 'flags_actionable': flags_actionable,
            'thresholds': th, 'total': base.count()}


def _load_pipeline_report(bank: ImageBank):
    """The persisted 'Launch all' summary (parsed), or None. A corrupt blob is
    swallowed — a broken report must never 500 the whole bank payload."""
    import json as _json
    raw = getattr(bank, 'pipeline_report', None)
    if not raw:
        return None
    try:
        return _json.loads(raw)
    except (ValueError, TypeError):
        return None


def list_banks(user_id, dataset_id=None) -> list:
    """Every bank of the user, newest first, with its triage counters, the ids
    of its card preview images — and, when ``dataset_id`` is given, how many
    kept images each bank would promote into THAT dataset (``promotable``).

    The promotable counts ride along on purpose: the dataset-side bank chooser
    used to ask /bank/<id>/promotable once per bank, so a library of 12 banks
    cost 13 requests to open one panel. One grouped query answers them all."""
    promotable = _promotable_counts(user_id, dataset_id) if dataset_id is not None else None
    out = []
    for bank in (ImageBank.query.filter_by(user_id=user_id)
                 .order_by(ImageBank.created_at.desc()).all()):
        base = BankImage.query.filter_by(bank_id=bank.id)
        row = {
            'id': bank.id, 'name': bank.name, 'source_path': bank.source_path,
            'created_at': bank.created_at.isoformat() if bank.created_at else None,
            'total': base.count(),
            'keep': base.filter_by(status='keep').count(),
            'reject': base.filter_by(status='reject').count(),
            'scanned': base.filter(BankImage.quality_state.isnot(None)).count(),
            'preview_ids': _preview_ids(bank.id),
            'activity': bank_jobs.get(bank.id),
        }
        if promotable is not None:
            row['promotable'] = promotable.get(bank.id, 0)
        out.append(row)
    return out


def _promotable_counts(user_id, dataset_id) -> dict | None:
    """{bank_id: promotable count} for EVERY bank at once — the batched form of
    promotable_count(), same eligibility rule (see _promotable_query). None when
    the dataset is gone or the id is junk, so the caller omits the field rather
    than publishing zeros it can't stand behind. Banks with nothing eligible are
    absent from the mapping; list_banks reads them as 0."""
    try:
        dataset_id = int(dataset_id)
    except (TypeError, ValueError):
        return None
    if not FaceDataset.query.filter_by(id=dataset_id, user_id=user_id).first():
        return None
    rows = (db.session.query(BankImage.bank_id, func.count(BankImage.id))
            .join(ImageBank, ImageBank.id == BankImage.bank_id)
            .filter(ImageBank.user_id == user_id,
                    BankImage.status == 'keep',
                    _not_already_on(dataset_id))
            .group_by(BankImage.bank_id).all())
    return {bank_id: n for bank_id, n in rows}


PREVIEW_COUNT = 5


def _preview_ids(bank_id, limit=PREVIEW_COUNT) -> list:
    """The first few image ids of a bank, for the card's thumbnail strip.
    Ordered by id (= inventory order), so the strip is STABLE across reloads —
    and rejected shots are skipped so a triaged bank doesn't advertise its
    discards. Kept images are deliberately NOT promoted to the front: most banks
    sit at zero keeps for their whole life, and re-ordering the strip as the user
    triages would make the card flicker under them. One query per bank, so the
    whole page still costs a single HTTP request."""
    rows = (BankImage.query.with_entities(BankImage.id)
            .filter(BankImage.bank_id == bank_id, BankImage.status != 'reject')
            .order_by(BankImage.id.asc()).limit(limit).all())
    return [r[0] for r in rows]


# --- free-text matching (the search bar, and its inverse) --------------------
# ONE definition of "this image's text mentions <term>", used by the search
# filter, by the exclude filter and by the curation pool, so the three can never
# drift into disagreeing about what a term matches.
_MAX_TEXT_TERMS = 12          # a checklist has a handful of tags, not a corpus


def _text_match(term):
    """Rows whose CAPTION or RELPATH contains `term`, case-insensitively. LIKE
    metacharacters in the term are escaped so a literal '%'/'_' matches itself.
    The caption is COALESCED to '' because this criterion is also used NEGATED:
    in SQL, NULL LIKE x is NULL, and NOT NULL is still NULL — so an uncaptioned
    row would be dropped by an exclude filter instead of kept, which is the exact
    opposite of "show me what does NOT have this tag yet"."""
    esc = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    like = f'%{esc}%'
    return or_(func.coalesce(BankImage.caption, '').ilike(like, escape='\\'),
               BankImage.relpath.ilike(like, escape='\\'))


# Separators a caption puts around a word. The word-boundary match below turns
# each of them into a space, then looks for ' <tag> ' in the padded result — the
# closest a plain LIKE gets to \b without a REGEXP function, and it needs no
# extension, no engine hook and no index.
_WORD_SEPARATORS = (',', '.', ';', ':', '!', '?', '(', ')', '[', ']', '"', "'",
                    '/', '\\', '-', '_', '\n', '\r', '\t')


def _spaced_text():
    """`' ' || lower(caption) || ' ' || lower(relpath) || ' '` with every
    separator replaced by a space — the haystack a whole-word match looks in."""
    haystack = func.lower(
        func.coalesce(BankImage.caption, '') + ' ' + BankImage.relpath)
    for sep in _WORD_SEPARATORS:
        haystack = func.replace(haystack, sep, ' ')
    return ' ' + haystack + ' '


def _tag_match(tag):
    """Rows whose caption or path mentions `tag` AS A WORD.

    Deliberately stricter than the 🚫 exclude field's substring match, and the
    difference is not an inconsistency: an exclude term is typed by hand, where
    a partial match is often what someone means, while a tag chip comes FROM a
    caption's own tokens — matching 'car' inside 'scarf' would make the feature
    lie about what it found. The substring/word-boundary split between the two
    is the known parity debt; this is the side that pays it first."""
    esc = tag.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return _spaced_text().ilike(f'% {esc} %', escape='\\')


def _text_terms(value) -> list:
    """Split an exclude field into terms on commas, trimmed, de-duplicated
    case-insensitively and capped. One field, several tags ('nsfw, logo') — a
    checklist pass usually hides more than one thing at a time."""
    out, seen = [], set()
    for tok in str(value or '').split(','):
        tok = tok.strip()
        if tok and tok.lower() not in seen:
            seen.add(tok.lower())
            out.append(tok)
    return out[:_MAX_TEXT_TERMS]


def _apply_text_filters(q, search=None, exclude=None, tags=None):
    """search ∩ ALL(tags) ∩ NOT(exclude₁) ∩ NOT(exclude₂)… — the positive term
    narrows to what mentions it, each exclude term hides what mentions it. They
    compose: searching 'dress' while excluding 'red' is a legitimate (and useful)
    question. An exclude term that is ALSO the search term simply yields nothing,
    honestly.

    ``tags`` is the 🏷️ chip filter, and it is an AND on purpose: the gesture is
    "images that have THIS and THIS", i.e. narrowing from one image's attributes.
    An OR would grow the result set with every chip ticked, which reads as the
    filter going backwards. Each tag matches as a WORD (see _tag_match) — a
    dedicated parameter with its own criterion, never folded into `search` or
    `exclude`, so two features can never fight over one key."""
    term = (search or '').strip()
    if term:
        q = q.filter(_text_match(term))
    for tag in _text_terms(tags):
        q = q.filter(_tag_match(tag))
    for bad in _text_terms(exclude):
        q = q.filter(~_text_match(bad))
    return q


def list_images(user_id, bank_id, status=None, flag=None, cluster=None,
                group=None, style=None, subfolder=None, search=None,
                semantic_group=None, sort=None, res_bucket=None, framing=None,
                origin=None, medium=None, angle=None, ids=None, exclude=None,
                tags=None, ids_only=False, offset=0, limit=200) -> dict | None:
    """One PAGE of the bank grid (a 9 000-image bank must never ship whole).
    Filters compose: status ∩ flag ∩ cluster ∩ dup-group ∩ style ∩ subfolder ∩ search.
    ``search`` is a plain full-text term matched (case-insensitive LIKE) against the
    caption AND the relpath — so captions double as searchable tags for a big dump
    ("red dress"), combinable with every other filter.
    ``exclude`` is the INVERSE of that search and the reason both live here: a
    comma-separated list of terms, each HIDING the images whose caption or path
    mentions it. Searching answers "where is X"; excluding answers "what have I
    not done yet", which is how a captioned bank gets worked through as a
    checklist. Uncaptioned rows are never hidden by it (see _text_match).
    Flag filters sort by the relevant score (worst first) so the review reads
    top-down. ``sort`` (a GRID_SORTS id) overrides that order and covers EVERY
    quantity the passes persist — resolution (megapixels, so 900×900 outranks
    1200×300), file size, aesthetic rating, NSFW probability, sharpness, noise,
    flatness, detail ratio, letterbox bars, JPEG quality, face confidence — each
    way. Rows the matching pass never reached (NULL) always sink to the end, in
    BOTH directions (see _sort_order). It composes with every filter,
    and — since "Select all in filter" / ▶ Review page this SAME endpoint — the
    selection walks the order the user is looking at.
    ``res_bucket`` (a _RES_BUCKETS id) narrows to one resolution tier — a
    half-open [lo, hi) megapixel band — and composes with every filter AND the
    sort (the tier + Resolution↑/↓ combo is the mixed-dump cleanup flow).
    ``medium`` (a MEDIUM_KEYS id) narrows to one medium — what the picture is
    MADE of, from the 🎨 Medium pass — including 'unsure', which is a real
    verdict and has to be reachable. ``angle`` (an ANGLES id) narrows to one head
    angle, recomputed from the stored yaw at read time. Both compose with
    everything, like every other facet.
    ``ids`` is the "show selected" VIEW: an explicit ordered list of image ids
    that OVERRIDES every facet/sort (the selection IS the scope) and renders the
    page in the SAME order the caller passed — so a similarity ranking from
    ``select_similar`` shows reference-first, closest-to-farthest, instead of the
    default id order. Unknown/foreign ids are dropped silently."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    th = thresholds()
    if ids is not None:
        # Explicit id view — the selection is the scope, order is preserved.
        # Dedupe keeping first occurrence so the requested order is authoritative.
        seen = set()
        ordered = [i for i in ids if not (i in seen or seen.add(i))]
        by_id = {}
        # Chunk the IN() so a big selection can't blow past SQLite's bound-
        # variable limit (default 999); the curation cap is 2 000 ids.
        for start in range(0, len(ordered), 500):
            chunk = ordered[start:start + 500]
            for r in (BankImage.query
                      .filter(BankImage.bank_id == bank_id,
                              BankImage.id.in_(chunk)).all()):
                by_id[r.id] = r
        ordered_rows = [by_id[i] for i in ordered if i in by_id]
        if ids_only:
            # Same scope, same order, ids only — the caller passed a selection and
            # wants it back minus the ids that no longer exist.
            return {'ids': [r.id for r in ordered_rows]}
        total = len(ordered_rows)
        off = max(0, int(offset))
        page = ordered_rows[off:off + max(1, min(500, int(limit)))]
        return {'images': _page_images(page, th), 'total': total, 'offset': off}
    q = BankImage.query.filter_by(bank_id=bank_id)
    if status in ('pending', 'keep', 'reject'):
        q = q.filter(BankImage.status == status)
    order = BankImage.id.asc()
    if flag == 'flagged':
        crits = [c for c in (_flag_filter(f, th) for f in _QUALITY_FLAGS)
                 if c is not None]
        q = q.filter(or_(*crits))
    elif flag == 'clean':
        q = q.filter(BankImage.quality_state == 'ok')
        # Every quality flag except 'unreadable' (that one IS the quality_state
        # already pinned to 'ok' above). Each criterion is NULL-safe, so a row
        # from a build that predates one of these scores still counts as clean
        # for it instead of dropping out of the chip entirely.
        for f in ('blur', 'noise', 'uniform', 'small', 'soft_detail', 'bars'):
            q = q.filter(~_flag_filter(f, th))
    elif flag == 'dups':
        q = q.filter(BankImage.dup_group.isnot(None))
        order = (BankImage.dup_group.asc(), BankImage.id.asc())
    elif flag == 'semantic_dups':
        q = q.filter(BankImage.semantic_dup_group.isnot(None))
        order = (BankImage.semantic_dup_group.asc(), BankImage.id.asc())
    elif flag == 'no_face':
        # Literally "no face was found" — ONLY face_state == 'no_face'. The other
        # non-scorable states (low_det / too_small / extreme_pose) DID detect a
        # face; lumping them in here surfaced photos with visible faces under a
        # "No face" chip. 'unreadable'/'error' are read failures, not "no face".
        q = q.filter(BankImage.face_state == 'no_face')
    elif flag in _QUALITY_FLAGS:
        crit = _flag_filter(flag, th)
        if crit is not None:
            q = q.filter(crit)
        order = {'blur': BankImage.blur_score.asc(),
                 'noise': BankImage.noise_score.desc(),
                 'uniform': BankImage.uniformity_score.asc(),
                 'small': BankImage.width.asc(),
                 'soft_detail': BankImage.detail_ratio.asc(),
                 'bars': BankImage.bars_ratio.desc(),
                 'unreadable': BankImage.id.asc()}[flag]
    elif flag in _SCORE_FLAGS:
        crit = _flag_filter(flag, th)
        if crit is not None:
            q = q.filter(crit)
        # Worst first: least aesthetic / most-confident NSFW at the top.
        order = {'low_aesthetic': BankImage.aesthetic_score.asc(),
                 'nsfw': BankImage.nsfw_score.desc(),
                 'watermark': BankImage.id.asc()}[flag]
    if cluster is not None:
        q = q.filter(BankImage.face_cluster == int(cluster))
    if group is not None:
        q = q.filter(BankImage.dup_group == int(group))
    if semantic_group is not None:
        q = q.filter(BankImage.semantic_dup_group == int(semantic_group))
    if style is not None:
        q = q.filter(BankImage.style_cluster == int(style))
    if framing in _FRAMING_KEYS:
        # One framing bucket (face/bust/body/back/unknown) — composes with every
        # other facet. An unknown/absent value simply doesn't filter.
        q = q.filter(BankImage.framing == framing)
    if origin in ORIGINS:
        # One provenance state. 'unknown' is a real, selectable answer — it is
        # what a stripped file honestly is, and the user must be able to see that
        # pile rather than have it silently merged into "not AI".
        q = q.filter(BankImage.origin == origin)
    if medium in MEDIUM_KEYS:
        # One medium bucket. 'unsure' is selectable on purpose — it is the pile
        # the classifier honestly could not call, and the only way to work
        # through it is to be able to look at it.
        q = q.filter(BankImage.medium == medium)
    if angle in ANGLES:
        # One head-angle bucket, recomputed from the stored yaw at read time (so
        # re-tuning the two cuts re-slices the bank with no rescan) — see
        # _angle_case for what 'behind' costs and requires.
        q = q.filter(_angle_case() == angle)
    if subfolder is not None:
        # '' scopes to root-level files; any other value to that top-level folder
        # and everything nested under it. startswith() escapes LIKE metachars.
        if subfolder == '':
            q = q.filter(~BankImage.relpath.contains(os.sep))
        else:
            q = q.filter(BankImage.relpath.startswith(subfolder + os.sep))
    # Full-text over caption + relpath, positive (search) and negative (exclude).
    q = _apply_text_filters(q, search, exclude, tags)
    if res_bucket in _RES_BOUNDS:
        # One resolution tier: [lo, hi) on megapixels (width×height). The NOT-NULL
        # guards drop unscanned rows (a NULL product would satisfy neither bound
        # cleanly), so a tier never leaks unscanned images. Composes with the sort.
        lo, hi = _RES_BOUNDS[res_bucket]
        area = BankImage.width * BankImage.height
        q = q.filter(BankImage.width.isnot(None), BankImage.height.isnot(None))
        if lo:
            q = q.filter(area >= lo)
        if hi is not None:
            q = q.filter(area < hi)
    explicit = _sort_order(sort)
    if explicit is not None:
        # An explicit sort (resolution / aesthetic / sharpness) wins over the flag
        # worst-first order; see _sort_order for the NULL-sinks-last contract.
        order = explicit
    order_by = order if isinstance(order, tuple) else (order,)
    if ids_only:
        # The LEAN answer: the ids of the WHOLE filter, in the order above, in one
        # query and one response. ▶ Review and "Select all in filter" want a
        # snapshot of ids and nothing else; walking the paginated grid for it made
        # the browser ask 46 times for 16 MB of image payloads — thumbnails, flags,
        # captions, promotion state — and throw all but the integer away. Measured
        # on a 22 940-image bank: 3.8 s with an active measure sort, because every
        # one of those 46 pages re-ran the COUNT and re-applied the ORDER BY over
        # the full table with a growing OFFSET.
        # No pagination here on purpose: 23 000 ids are ~180 kB of JSON, where the
        # same 23 000 rows are 16 MB. The cap that matters is the bank's size, and
        # a bank that cannot fit its own ids in a response cannot fit its grid either.
        return {'ids': [r[0] for r in
                        q.with_entities(BankImage.id).order_by(*order_by).all()]}
    total = q.count()
    rows = q.order_by(*order_by).offset(max(0, int(offset))) \
            .limit(max(1, min(500, int(limit)))).all()
    return {'images': _page_images(rows, th), 'total': total,
            'offset': max(0, int(offset))}


# --- thumbnails -------------------------------------------------------------
def _thumb_path(bank_id, row: BankImage) -> Path:
    """Where this image's thumbnail lives. A watermark-cleaned or manually
    TURNED image gets its OWN thumbnail file, named after the cleaning method and
    the angle: the cached source thumbnail is never overwritten (so an undo — or
    a fourth quarter turn — instantly shows the original again) and the grid can
    never serve a stale pre-clean crop or a sideways tile. Deleting a cached
    thumbnail in place would be the fragile version of this — on Windows the file
    may still be held open by the response that just served it."""
    suffix = f'.{row.watermark_clean_method}' if row.watermark_clean_method else ''
    if getattr(row, 'rotation', None):
        suffix += f'.r{int(row.rotation)}'
    return _thumbs_dir(bank_id) / f'{row.id}{suffix}.webp'


def drop_derived(bank_id, image_id) -> None:
    """Best-effort removal of every DERIVED blob of one image — the cleaned and
    turned thumbnails plus the turned full-size copies (an undo, a re-scan or a
    new clean just invalidated them). The pristine `<id>.webp` thumbnail of the
    untouched source is deliberately kept. A leftover is harmless — nothing
    points at it once the row's state moved on — so a locked file is not an
    error."""
    for pattern, folder in ((f'{image_id}.*.webp', _thumbs_dir(bank_id)),
                            (f'{image_id}.r*', _rotated_dir(bank_id))):
        try:
            for stale in folder.glob(pattern):
                try:
                    stale.unlink()
                except OSError:
                    pass
        except OSError:
            pass


#: Historical alias — external callers/tests may still name the narrow version.
drop_clean_thumbs = drop_derived


def ensure_thumb(bank: ImageBank, row: BankImage) -> Path | None:
    """The image's grid thumbnail, generated lazily when the scan hasn't made
    it yet (so the grid is browsable straight after inventory). Built from the
    RESOLVED path, so a cleaned image shows clean in the grid."""
    tpath = _thumb_path(bank.id, row)
    if tpath.is_file():
        return tpath
    src = resolved_image_path(bank, row)
    if not src or not os.path.isfile(src):
        return None
    try:
        tpath.parent.mkdir(parents=True, exist_ok=True)
        with safe_bank_source(src, label='bank thumbnail') as im:
            im.draft(None, (THUMB_MAX_SIDE * 2, THUMB_MAX_SIDE * 2))
            im = im.convert('RGB')
            im.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE), Image.LANCZOS)
            im.save(tpath, 'WEBP', quality=72)
        return tpath
    except (OSError, ValueError, MemoryError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        return None


# --- quality scan (background) ----------------------------------------------
def _scan_one(src_root: str, thumbs: Path, item: tuple) -> dict:
    """Worker: decode ONE file, compute metrics + dHash + thumbnail. Pure
    filesystem/PIL — no DB access (the job thread owns the session)."""
    image_id, relpath = item
    path = os.path.join(src_root, relpath)
    out = {'id': image_id, 'quality_state': 'unreadable', 'width': None,
           'height': None, 'file_size': None, 'dhash': None, 'metrics': None,
           'provenance': None}
    try:
        out['file_size'] = os.path.getsize(path)
    except OSError:
        # ABSENT ≠ CORRUPT. A file that is simply not there says nothing about
        # the image — the folder moved, or its drive is unplugged. 'missing' is
        # an in-memory signal for the job loop only (it is never written to
        # quality_state, so the row stays unscanned and a later pass retries it).
        if not os.path.exists(path):
            out['quality_state'] = 'missing'
            return out
    try:
        with safe_bank_source(path, label='bank scan') as im:
            out['width'], out['height'] = im.size
            # JPEG fast path: decode at reduced scale — the metrics run on a
            # ≤1024 working copy anyway, and dHash (9×8) is resize-invariant.
            im.draft(None, (ANALYSIS_MAX_SIDE * 2, ANALYSIS_MAX_SIDE * 2))
            im.load()
            out['metrics'] = quality_metrics(im)
            # Provenance rides along on the SAME decode — re-opening the file for
            # it would double the I/O of a 36 000-image pass for nothing. It reads
            # the drafted image (native pixels up to ANALYSIS_MAX_SIDE*2), which is
            # what the effective-resolution measure needs: it crops, never resizes.
            out['provenance'] = provenance_metrics(im)
            out['dhash'] = f'{_dhash(im):016x}'
            tpath = thumbs / f'{image_id}.webp'
            if not tpath.is_file():
                t = im.convert('RGB')
                t.thumbnail((THUMB_MAX_SIDE, THUMB_MAX_SIDE), Image.LANCZOS)
                t.save(tpath, 'WEBP', quality=72)
        out['quality_state'] = 'ok'
    except (OSError, ValueError, SyntaxError, MemoryError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        pass  # stays 'unreadable' — surfaced as a flag, never fatal
    return out


def start_scan(app, user_id, bank_id, rescan=False, regroup=False):
    """Launch the quality pass. Raises BankJobBusy when a job is already live,
    ValueError when the bank is unknown.

    ``regroup`` asks for the duplicate grouping EXPLICITLY, whatever the scan
    itself finds. That is what the 🎚 threshold panel's "↻ Re-group duplicates"
    sends: on an already-scanned bank its pool is empty, and the tail of the pass
    now only regroups when the stored hashes moved — without this flag that
    button would have quietly become a no-op."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    total = _scan_pool(bank_id, rescan).count()
    return bank_jobs.start(app, bank_id, 'scan',
                           _scan_job(bank_id, rescan, regroup=regroup),
                           total=total)


def _scan_pool(bank_id, rescan):
    """What the quality pass has to look at. Rejected images are OUT, like every
    other pass: on a 30 000-image bank two thirds of a rescan went to shots the
    user had already thrown away.

    Skipping them cannot swallow a FIRST scan: an image is only rejected by hand
    (after it was scanned) or by this very pass when it turns out unreadable, so
    a never-scanned image is still pending here. Un-reject one and it comes back
    into the pool on its own — that is why the filter is `!= reject` rather than
    an explicit pending/keep list."""
    q = (BankImage.query.filter_by(bank_id=bank_id)
         .filter(BankImage.status != 'reject'))
    if not rescan:
        # Never-scanned rows, PLUS rows a previous build scanned before the
        # provenance signals existed. Retrofitting the bank the user already has
        # is the point: telling them "only images scanned from now on get an
        # effective resolution" would leave a 36 000-image bank permanently half
        # measured, with no way to fix it short of a full rescan of everything.
        # `origin` is the sentinel because it is the one signal that always lands
        # on a readable file (one of ai/camera/unknown, never NULL) — keying off
        # detail_ratio would re-pick flat images forever, since those legitimately
        # measure nothing.
        q = q.filter(or_(BankImage.quality_state.is_(None),
                         and_(BankImage.quality_state == 'ok',
                              BankImage.origin.is_(None))))
    return q


def _scan_job(bank_id, rescan, regroup=False):
    def run(job):
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        items = [(r.id, r.relpath) for r in
                 _scan_pool(bank_id, rescan).order_by(BankImage.id.asc()).all()]
        bank_jobs.progress(job, done=0, total=len(items), detail='quality scan')
        thumbs = _thumbs_dir(bank_id)
        thumbs.mkdir(parents=True, exist_ok=True)
        src_root = bank.source_path
        if items and not os.path.isdir(src_root or ''):
            bank_jobs.fail(job, MOVED_FOLDER_MSG)
            return
        workers = min(8, os.cpu_count() or 4)
        done = 0
        missing = 0
        vanished = 0
        hashed = 0      # rows whose STORED hash actually changed (see the tail)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            it = iter(items)
            futures = deque()

            def submit_next():
                nxt = next(it, None)
                if nxt is not None:
                    futures.append(ex.submit(_scan_one, src_root, thumbs, nxt))

            for _ in range(workers * 2):
                submit_next()
            while futures:
                res = futures.popleft().result()
                if res['quality_state'] == 'missing':
                    # Leave the row EXACTLY as it was (unscanned, undecided) and
                    # count it. Grading an absent file would auto-reject it, and
                    # a folder that moved makes every file absent at once — that
                    # path silently rejects a whole bank, so it must not exist.
                    missing += 1
                    done += 1
                    bank_jobs.bump(job)
                    if missing >= _MISSING_ABORT_AT and missing * 2 >= done:
                        db.session.commit()
                        bank_jobs.fail(job, MOVED_FOLDER_MSG)
                        return
                    if not bank_jobs.cancelled(job):
                        submit_next()
                    continue
                # no_autoflush: this re-read is a SELECT, and SQLAlchemy flushes
                # the session before one by default. That flush takes the single
                # SQLite write lock at the FIRST image after a mutation and holds
                # it until the commit 25 images later, so every other writer in
                # the app queues behind a scan it has nothing to do with —
                # measured on a live bank: a sort click went from 5.0 ms median
                # to 327.6 ms (p90 2 183 ms, worst 5 564 ms, one HTTP 500 out of
                # 62 clicks). Suppressing the flush here took the worst wait to
                # 16.7 ms with zero failures and no change in scan throughput
                # (70-81 img/s): the rows are still written, by the commit that
                # already paces this loop.
                with db.session.no_autoflush:
                    row = _live_image(res['id'])
                if row is None:
                    # Deleted while the pass ran (see _live_image): skip it and
                    # keep going rather than sinking a scan of thousands.
                    vanished += 1
                else:
                    if row.dhash != res['dhash']:
                        hashed += 1
                    row.quality_state = res['quality_state']
                    row.width, row.height = res['width'], res['height']
                    if res['file_size'] is not None:
                        row.file_size = res['file_size']
                    row.dhash = res['dhash']
                    if res['metrics']:
                        row.blur_score = res['metrics']['blur_score']
                        row.noise_score = res['metrics']['noise_score']
                        row.uniformity_score = res['metrics']['uniformity_score']
                    if res['provenance']:
                        p = res['provenance']
                        row.detail_ratio = p['detail_ratio']
                        row.bars_ratio = p['bars_ratio']
                        row.jpeg_quality = p['jpeg_quality']
                        row.origin = p['origin']
                        row.origin_evidence = p['origin_evidence']
                    # An unreadable file can never be promoted — auto-reject it
                    # (only over 'pending': a manual decision is never flipped).
                    if res['quality_state'] == 'unreadable' and row.status == 'pending':
                        row.status, row.reject_reason = 'reject', 'unreadable'
                done += 1
                if done % _COMMIT_EVERY == 0:
                    db.session.commit()
                bank_jobs.bump(job)
                if not bank_jobs.cancelled(job):
                    submit_next()
        db.session.commit()
        if bank_jobs.cancelled(job):
            return
        tail = (f' — {missing} file(s) were not on disk and were left '
                'untouched') if missing else ''
        if vanished:
            tail += f', {vanished} skipped (deleted while the pass ran)'
        # Regroup only when the input to the grouping CHANGED, or when the
        # caller asked for it on purpose (the 🎚 panel's "↻ Re-group duplicates",
        # which is how a new dup_distance is applied without decoding anything).
        #
        # This is the whole freeze the owner reported. A scan with rescan off has
        # an empty-to-tiny pool on an already-scanned bank — measured 2 rows out
        # of 50 397 — and the tail then re-grouped the 50 389 hashed rows anyway:
        # the bar reached 100 %, said "grouping duplicates", and the app went
        # away for 96 to 124 s. When no stored hash moved and no row disappeared,
        # the grouping's input is byte-for-byte what produced the groups already
        # on screen, so running it can only reproduce them.
        if regroup or hashed or vanished:
            bank_jobs.progress(job, detail='grouping duplicates')
            groups = rebuild_dup_groups(bank_id, job=job)
            if bank_jobs.cancelled(job):
                return
            head = f'done — {groups} duplicate group(s)'
        elif done:
            head = f'done — {done} image(s) checked, no new hash to group'
        else:
            head = 'done — every image was already scanned'
        bank_jobs.progress(job, detail=f'{head}{tail}')
    return run


# --- duplicate groups -------------------------------------------------------
def _job_progress(job, **values):
    """bank_jobs.progress for a phase that also runs OUTSIDE a job (tests, and
    any future caller): no job, no reporting, no branch at every call site."""
    if job is not None:
        bank_jobs.progress(job, **values)


def _job_cancelled(job) -> bool:
    return job is not None and bank_jobs.cancelled(job)


def _popcount_lut():
    """256-entry uint8 popcount table, built once.

    numpy only grew `bitwise_count` in 2.0 and the app still ships on 1.26, so
    the table is the portable way to popcount a whole XOR block in one C pass —
    which is also the point: the GIL is released for the duration instead of
    being held by a Python loop over pairs."""
    global _POPCOUNT8
    if _POPCOUNT8 is None:
        import numpy as np
        _POPCOUNT8 = np.array([bin(i).count('1') for i in range(256)],
                              dtype='uint8')
    return _POPCOUNT8


def _dup_groups_from_hashes(hashes, d, job=None):
    """The grouping itself: 64-bit hashes in, groups of ≥2 POSITIONS out, biggest
    group first and ties broken by the smallest position. None when the job was
    stopped mid-way (nothing has been written at that point).

    Banded prefilter (pigeonhole: two hashes within Hamming d share at least one
    of d+1 equal bands) keeps this out of the full O(n²); candidate pairs are
    then verified exactly and grouped by union-find.

    WHY IT LOOKS LIKE `rebuild_semantic_dup_groups`. The pairs used to be walked
    in Python, with a `set` of every pair already looked at. That set is not
    bounded by anything: 13 MB at 2 000 images, 829 MB at 16 000, ~4.3 GB
    extrapolated at 36 000 — and the garbage collector sweeping it was ~79 % of
    the wall time (disabling the GC took one measured phase from 68 s to 14 s and
    a typical handler's p95 from 351 ms back to 22 ms). Comparing a whole block
    at once in numpy has no such set, releases the GIL while it works, and caps
    its own memory at `_DUP_BLOCK_CELLS`. The pair set it unions is EXACTLY the
    one the Python loops produced — same buckets, same `x < y`, same threshold —
    so the groups are identical, which `test_bank_dup_groups_identity.py` pins
    against a verbatim copy of the old code.
    """
    import numpy as np
    n = len(hashes)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    bands = max(1, min(16, d + 1))
    band_bits = 64 // bands
    buckets: dict = {}
    for i, h in enumerate(hashes):
        for b in range(bands):
            key = (b, (h >> (b * band_bits)) & ((1 << band_bits) - 1))
            buckets.setdefault(key, []).append(i)
    work = [m for m in buckets.values() if len(m) >= 2]
    total = sum(len(m) for m in work)
    _job_progress(job, done=0, total=total,
                  detail=f'grouping duplicates — comparing {n} hash(es)')
    lut = _popcount_lut()
    seen = 0
    for members in work:
        if _job_cancelled(job):
            return None
        m = len(members)
        if m < _DUP_NUMPY_FROM:
            # Tiny buckets are the majority and an array costs more than the
            # handful of comparisons it would save.
            for x in range(m):
                for y in range(x + 1, m):
                    a, b = members[x], members[y]
                    if find(a) != find(b) and _hamming(hashes[a], hashes[b]) <= d:
                        union(a, b)
            seen += m
            _job_progress(job, done=seen)
            continue
        arr = np.array([hashes[i] for i in members], dtype='uint64')
        cols = np.arange(m, dtype='int64')[None, :]
        step = max(1, min(m, _DUP_BLOCK_CELLS // m))
        for i0 in range(0, m, step):
            if _job_cancelled(job):
                return None
            block = arr[i0:i0 + step, None] ^ arr[None, :]
            rows_n = block.shape[0]
            dist = lut[block.view('uint8').reshape(rows_n, m, 8)].sum(
                axis=2, dtype='uint8')
            # `> row index` is the vectorised form of the old `for y in
            # range(x + 1, ...)`: the diagonal and the mirror pair are skipped,
            # so each unordered pair is offered to union-find exactly once.
            keep = (dist <= d) & (cols > np.arange(
                i0, i0 + rows_n, dtype='int64')[:, None])
            for a_rel, b in np.argwhere(keep):
                union(members[i0 + int(a_rel)], members[int(b)])
            seen += rows_n
            _job_progress(job, done=min(seen, total))
    comps: dict = {}
    for i in range(n):
        comps.setdefault(find(i), []).append(i)
    return sorted((m for m in comps.values() if len(m) >= 2),
                  key=lambda m: (-len(m), m[0]))


def rebuild_dup_groups(bank_id, max_distance=None, job=None) -> int:
    """Recompute near-duplicate groups over every hashed image of the bank.
    Groups of ≥2 get a 1-based id ordered by size (biggest first). Returns the
    group count (what was written, when the job was stopped part-way).

    ``job`` makes the phase VISIBLE and STOPPABLE. It used to be neither: no
    progress, no cancel check anywhere in its body, so a bank of 50 000 images
    left the progress bar at 100 % under the words "grouping duplicates" for 96
    to 124 s with no way out — which reads as a dead application, and was
    reported as one."""
    th = thresholds()
    d = int(th['dup_distance'] if max_distance is None else max_distance)
    rows = (db.session.query(BankImage.id, BankImage.dhash)
            .filter(BankImage.bank_id == bank_id, BankImage.dhash.isnot(None))
            .order_by(BankImage.id.asc()).all())
    ids = [r[0] for r in rows]
    hashes = [int(r[1], 16) for r in rows]
    # Everything below the comparison is pure CPU over data already in memory,
    # so the session must not sit on a transaction across it — same guard, same
    # reason, as every inference pass (see _release_db_before_inference).
    _release_db_before_inference()
    groups = _dup_groups_from_hashes(hashes, d, job=job)
    if groups is None:
        return 0            # stopped before any write: the bank is untouched
    _job_progress(job, done=0, total=len(groups),
                  detail=f'grouping duplicates — writing {len(groups)} group(s)')
    BankImage.query.filter_by(bank_id=bank_id).update(
        {'dup_group': None}, synchronize_session=False)
    db.session.commit()
    # ONE prepared statement per batch, and a real pause between batches.
    #
    # The clear plus one `UPDATE ... WHERE id IN (…)` per group — about 5 000 of
    # them on a 50 000-image bank — used to be a single transaction holding the
    # write lock 6 to 9.5 s, past the 5 s busy_timeout: `database is locked` for
    # everybody else, 3 attempts out of 3. Splitting it into batches is only half
    # the fix, and the half that measures nothing on its own:
    #   • 4 000 separate UPDATE statements cost 0.67 s of pure statement overhead
    #     whatever the transaction boundaries are; one executemany over the same
    #     8 000 rows is ~30 ms, so the lock is barely taken at all;
    #   • and without the pause, the next batch re-takes the lock in the
    #     microsecond after the commit, inside the sleep of the other writer's
    #     busy handler. Batching alone left a concurrent writer waiting 620 ms
    #     and still refused — measured, and the reason this loop yields.
    # The cost of the trade is stated where the user reads it: groups land
    # biggest-first, and a stop part-way keeps the ones already written (the
    # panel already says "the groups are whatever it had reached").
    stmt = text('UPDATE bank_image SET dup_group = :gid WHERE id = :iid')
    pending: list = []

    def flush():
        if not pending:
            return
        db.session.execute(stmt, pending)
        db.session.commit()
        pending.clear()
        time.sleep(_DUP_WRITE_YIELD)

    for gid, members in enumerate(groups, start=1):
        pending.extend({'gid': gid, 'iid': ids[i]} for i in members)
        if len(pending) >= _DUP_WRITE_ROWS:
            flush()
            _job_progress(job, done=gid)
            if _job_cancelled(job):
                return gid
    flush()
    _job_progress(job, done=len(groups))
    return len(groups)


# --- semantic near-duplicate groups (stage 2 — crops / re-compressed variants) --
# One-entry memo for the parsed score cache. Reading it is 350 ms on a 14 700-row
# bank (40 MB .npz + a stat per row), and a user tuning a curation slider clicks
# three or four times on the SAME unchanged cache — that was 350 ms paid over and
# over for a file nobody touched. Bounded on purpose:
#   • ONE bank at a time (~45 MB of float32 at 14 700 × 768 — switching banks frees
#     the previous one rather than accumulating);
#   • keyed on the .npz's own (size, mtime_ns), so a finished ✨ Score pass — which
#     rewrites the file — invalidates it without anyone having to remember to;
#   • and it expires anyway after _SCORE_MEMO_TTL, because the per-row staleness
#     stats it skips are how a since-edited IMAGE gets dropped. A short window
#     covers the double-click; a session-long one would hide a real edit.
_SCORE_MEMO_TTL = 60.0
_score_memo = None            # (key, at, {path: emb}) — see reset_score_memo()


def reset_score_memo() -> None:
    """Drop the parsed-score-cache memo (tests; bank deletion)."""
    global _score_memo
    _score_memo = None


def _load_score_embeddings(bank: ImageBank) -> dict:
    """{abs_path: emb (np.float32, L2-normed)} from the ✨ Score pass cache, for the
    scored 'ok' images whose file still matches what was scored. Empty when the pass
    never ran (no cache) — the caller then surfaces the "run Score first" hint. A
    STALE entry (a same-path edit since scoring, detected via the cached size+mtime
    signature) is dropped, so a semantic group is never built on an outdated
    embedding. Reads the .npz directly (numpy is in the Flask venv); torch/open_clip
    are NOT needed here — stage 2 costs no new GPU work, it reuses Score's output."""
    global _score_memo
    import numpy as np
    path = _score_cache_path(bank.id)
    if not path.is_file():
        return {}
    try:
        st = path.stat()
        key = (bank.id, str(path), st.st_size, st.st_mtime_ns)
    except OSError:
        key = None
    if key is not None and _score_memo is not None:
        mkey, at, cached = _score_memo
        if mkey == key and (time.time() - at) < _SCORE_MEMO_TTL:
            return cached
    try:
        with np.load(str(path), allow_pickle=False) as z:
            paths = [str(p) for p in z['paths']]
            states = [str(s) for s in z['states']]
            embs = z['embs']
            sigs = ([str(s) for s in z['sigs']] if 'sigs' in z.files
                    else [''] * len(paths))
    except Exception as e:  # noqa: BLE001 — a corrupt cache = "no embeddings", never fatal
        logger.warning('bank %s score cache unreadable: %s', bank.id, e)
        return {}
    out = {}
    for i, p in enumerate(paths):
        if states[i] != 'ok':
            continue
        emb = embs[i]
        if float(np.abs(emb).sum()) <= 0:       # zero sentinel = errored image
            continue
        sig = sigs[i]
        if sig:                                 # drop a since-edited file
            try:
                st = os.stat(p)
                if f'{st.st_size}:{st.st_mtime_ns}' != sig:
                    continue
            except OSError:
                continue
        out[p] = np.asarray(emb, dtype='float32')
    if key is not None:
        _score_memo = (key, time.time(), out)
    return out


def rebuild_semantic_dup_groups(bank_id, threshold=None) -> int | None:
    """Stage-2 near-duplicate grouping over the CLIP embeddings the ✨ Score pass
    cached — catches crops and re-compressed variants of the SAME shot that the
    dHash (stage 1) misses. Returns the group count (groups of ≥2), or None when NO
    embeddings are available (Score hasn't run) so the caller shows the "run Score
    first" hint instead of a silent empty result.

    Cost: a semantic near-dup (cosine ≥ threshold) is necessarily inside one style
    union-find component (that clustering uses style_threshold ≤ threshold), so we
    BLOCK by style_cluster and only compare within a block — Σ block² dot-products,
    not the full n². A config with style_threshold > threshold would break that
    guarantee, so we fall back to a single global block then. Re-running at another
    threshold is CPU-only and near-instant: it re-reads the cached embeddings — no
    GPU, no re-scan."""
    import numpy as np
    bank = db.session.get(ImageBank, bank_id)
    if not bank:
        return None
    emb_by_path = _load_score_embeddings(bank)
    if not emb_by_path:
        return None
    th = thresholds()
    t = float(threshold if threshold is not None else th['semantic_dup_threshold'])
    block_by_style = th['style_threshold'] <= t
    rows = (BankImage.query.filter_by(bank_id=bank_id)
            .order_by(BankImage.id.asc()).all())
    items = []      # (image_id, block_key, emb)
    for r in rows:
        p = abs_image_path(bank, r)
        emb = emb_by_path.get(p) if p else None
        if emb is None:
            continue
        block = (r.style_cluster if r.style_cluster is not None else -1) \
            if block_by_style else 0
        items.append((r.id, block, emb))
    # A re-run fully recomputes — clear every semantic group first.
    BankImage.query.filter_by(bank_id=bank_id).update(
        {'semantic_dup_group': None}, synchronize_session=False)
    if not items:
        db.session.commit()
        return 0
    blocks: dict = {}
    for idx, (_id, block, _emb) in enumerate(items):
        blocks.setdefault(block, []).append(idx)
    parent = list(range(len(items)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    chunk = 512
    for members in blocks.values():
        if len(members) < 2:
            continue
        E = np.stack([items[i][2] for i in members]).astype('float32')
        E /= (np.linalg.norm(E, axis=1, keepdims=True) + 1e-8)
        m = len(members)
        for i0 in range(0, m, chunk):
            sims = E[i0:i0 + chunk] @ E.T
            for a, b in np.argwhere(sims >= t):
                a += i0
                if a < b:                       # skip the diagonal + mirror pairs
                    union(members[int(a)], members[int(b)])
    comps: dict = {}
    for i in range(len(items)):
        comps.setdefault(find(i), []).append(i)
    groups = sorted((m for m in comps.values() if len(m) >= 2),
                    key=lambda m: (-len(m), items[m[0]][0]))
    for gid, members in enumerate(groups, start=1):
        member_ids = [items[i][0] for i in members]
        for i0 in range(0, len(member_ids), _SQL_IN_CHUNK):
            BankImage.query.filter(
                BankImage.id.in_(member_ids[i0:i0 + _SQL_IN_CHUNK])).update(
                {'semantic_dup_group': gid}, synchronize_session=False)
    db.session.commit()
    return len(groups)


def start_semantic_dedup(app, user_id, bank_id, threshold=None):
    """Launch the stage-2 semantic near-duplicate pass (CPU, reuses the ✨ Score
    embeddings — no GPU). ValueError (→400) when Score hasn't produced any usable
    embedding yet, so the UI shows the clear "run Score first" hint rather than a
    job that quietly does nothing."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    if not _load_score_embeddings(bank):
        raise ValueError('run ✨ Score first — semantic near-duplicates reuse its '
                         'embeddings')
    return bank_jobs.start(app, bank_id, 'semantic_dedup',
                           _semantic_dedup_job(bank_id, threshold), total=0)


def _semantic_dedup_job(bank_id, threshold):
    def run(job):
        bank_jobs.progress(job, done=0, total=0, detail='finding crops & variants')
        n = rebuild_semantic_dup_groups(bank_id, threshold)
        if n is None:
            bank_jobs.progress(job, detail='no embeddings — run ✨ Score first')
            return
        bank_jobs.progress(job, detail=f'done — {n} semantic near-duplicate group(s)')
    return run


def dup_groups_payload(user_id, bank_id, offset=0, limit=50,
                       col=BankImage.dup_group) -> dict | None:
    """Unresolved groups (≥2 non-rejected members) with their full membership,
    for the resolution panel. ``col`` picks the stage: dup_group (exact/resized) or
    semantic_dup_group (crops/variants)."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    th = thresholds()
    gids = [g for (g,) in _unresolved_dup_groups_q(bank_id, col)
            .order_by(col.asc()).all()]
    total = len(gids)
    page = gids[max(0, int(offset)):max(0, int(offset)) + max(1, min(200, int(limit)))]
    groups = []
    for gid in page:
        rows = (BankImage.query.filter(BankImage.bank_id == bank_id, col == gid)
                .order_by(BankImage.id.asc()).all())
        groups.append({'group': gid,
                       'best_id': _best_of(rows).id if rows else None,
                       'images': _page_images(rows, th)})
    return {'groups': groups, 'total': total, 'offset': max(0, int(offset))}


def semantic_dup_groups_payload(user_id, bank_id, offset=0, limit=50) -> dict | None:
    """dup_groups_payload for stage 2 (semantic_dup_group)."""
    return dup_groups_payload(user_id, bank_id, offset=offset, limit=limit,
                              col=BankImage.semantic_dup_group)


def _best_of(rows):
    """'Keep best' heuristic for a duplicate group. When the aesthetic pass has
    run it leads (the ask: keep the NICE copy, not merely the biggest); a
    scored image always outranks an unscored one (sentinel -1 < the ~1..10 range).
    Then most pixels, sharpest, heaviest file — a Telegram dump's duplicates are
    mostly re-compressed or downscaled copies, so surface area is the honest
    fallback key."""
    def key(r):
        return (r.aesthetic_score if r.aesthetic_score is not None else -1.0,
                (r.width or 0) * (r.height or 0), r.blur_score or 0.0,
                r.file_size or 0, -r.id)
    return max(rows, key=key)


def resolve_dups(user_id, bank_id, strategy='best', group=None, keep_ids=None,
                 col=BankImage.dup_group, attr='dup_group', reason='duplicate',
                 respect_existing_keep=True, snapshot=None):
    """Resolve duplicate groups: keep one member, REJECT the others (a status,
    never a file deletion, so it's reversible). strategy 'best'|'first' applies to
    one group or, when ``group`` is None, to every unresolved group at once;
    explicit ``keep_ids`` (manual pick) applies to their own groups. Only
    non-rejected members are touched. ``col``/``attr``/``reason`` pick the stage:
    dup_group (exact/'duplicate') or semantic_dup_group (crops/'semantic_dup').

    ``respect_existing_keep`` (default True) protects members the user already
    KEPT from a bulk resolve — right for the AUTOMATIC pipeline auto-reject, so a
    mass resolve never un-keeps a manual pick. An EXPLICIT resolve the user fired
    from a dup/same-shot group passes False: the whole point is to collapse the
    group to ONE, and the members of a same-shot group are typically ALL 'keep',
    so respecting keep would reject nobody. The elected keeper is always safe
    (``r.id in keep``); with False every OTHER member falls to reject, keep
    included. Returns {'resolved': groups, 'rejected': images}.

    ``snapshot``: pass a live :class:`bank_undo.Snapshot` to fold this resolve
    into a WIDER undo step (the pipeline's auto-reject is a flag pass plus this
    one); omit it and the call publishes its own one-step undo offer."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    own_snapshot = snapshot is None
    if own_snapshot:
        snapshot = bank_undo.Snapshot(
            'Resolve same-shot groups' if reason == 'semantic_dup'
            else 'Resolve duplicate groups')
    keep_by_group = {}
    if keep_ids:
        rows = BankImage.query.filter(BankImage.bank_id == bank_id,
                                      BankImage.id.in_(list(keep_ids)[:_SQL_IN_CHUNK])).all()
        for r in rows:
            g = getattr(r, attr)
            if g:
                keep_by_group.setdefault(g, set()).add(r.id)
        gids = list(keep_by_group)
    elif group is not None:
        gids = [int(group)]
    else:
        gids = [g for (g,) in _unresolved_dup_groups_q(bank_id, col).all()]
    resolved = rejected = 0
    for gid in gids:
        rows = (BankImage.query.filter(BankImage.bank_id == bank_id, col == gid)
                .filter(BankImage.status != 'reject')
                .order_by(BankImage.id.asc()).all())
        if len(rows) < 2 and gid not in keep_by_group:
            continue
        if gid in keep_by_group:
            keep = keep_by_group[gid]
        elif strategy == 'first':
            keep = {rows[0].id}
        else:
            keep = {_best_of(rows).id}
        changed = False
        for r in rows:
            if r.id in keep or (respect_existing_keep and r.status == 'keep'):
                continue
            snapshot.note(r, 'reject', reason)
            r.status, r.reject_reason = 'reject', reason
            rejected += 1
            changed = True
        if changed or len(rows) >= 2:
            resolved += 1
    db.session.commit()
    if own_snapshot:
        snapshot.commit(bank_id)
    return {'resolved': resolved, 'rejected': rejected}


def resolve_semantic_dups(user_id, bank_id, strategy='best', group=None,
                          keep_ids=None, respect_existing_keep=True,
                          snapshot=None):
    """resolve_dups for stage 2 (semantic_dup_group, reject reason
    'semantic_dup')."""
    return resolve_dups(user_id, bank_id, strategy=strategy, group=group,
                        keep_ids=keep_ids, col=BankImage.semantic_dup_group,
                        attr='semantic_dup_group', reason='semantic_dup',
                        respect_existing_keep=respect_existing_keep,
                        snapshot=snapshot)


# --- statuses & flag application --------------------------------------------
_STATUS_UNDO_LABEL = {'keep': 'Keep images', 'reject': 'Reject images',
                      'pending': 'Set images back to undecided'}


def set_status(user_id, bank_id, ids, status) -> int:
    """Manual keep/reject/pending on a selection. Returns rows changed.

    Snapshots the prior (status, reason) of every row it actually flips, so the
    workspace can offer ONE step back — this is the gesture that puts hundreds of
    decisions in flight at once (select the whole filter, then ✕)."""
    if status not in ('pending', 'keep', 'reject'):
        raise ValueError('bad status')
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    ids = [int(i) for i in (ids or [])]
    reason = 'manual' if status == 'reject' else None
    snapshot = bank_undo.Snapshot(_STATUS_UNDO_LABEL[status])
    n = 0
    for i0 in range(0, len(ids), _SQL_IN_CHUNK):
        rows = BankImage.query.filter(
            BankImage.bank_id == bank_id,
            BankImage.id.in_(ids[i0:i0 + _SQL_IN_CHUNK])).all()
        for r in rows:
            snapshot.note(r, status, reason)
            r.status = status
            r.reject_reason = reason
            n += 1
    db.session.commit()
    snapshot.commit(bank_id)
    return n


def rotate_images(user_id, bank_id, ids, delta) -> dict:
    """Turn a selection by ``delta`` degrees CLOCKWISE (idea by 1Tomber, #17).

    The user's files are NEVER written to: the new angle is stored on the row and
    the derived blobs (turned copy + thumbnail) are dropped so the ONE resolver
    rebuilds them from the pristine source on the next read. That is what makes
    the turn free of loss where it counts — a fourth quarter turn puts the row
    back at 0 and every reader is served the original bytes again, byte for byte.

    ``delta`` may be negative (-90 = turn left). Returns {'rotated': n,
    'rotations': {image_id: angle}} so the grid can re-render without a refetch.
    """
    from .face_dataset_service import normalize_rotation
    step = normalize_rotation(delta)
    if step == 0:
        raise ValueError('rotation must be 90, 180 or 270 degrees')
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    ids = [int(i) for i in (ids or [])]
    if not ids:
        raise ValueError('select at least one image')
    rotations = {}
    for i0 in range(0, len(ids), _SQL_IN_CHUNK):
        rows = BankImage.query.filter(
            BankImage.bank_id == bank_id,
            BankImage.id.in_(ids[i0:i0 + _SQL_IN_CHUNK])).all()
        for r in rows:
            r.rotation = (int(r.rotation or 0) + step) % 360 or None
            drop_derived(bank_id, r.id)
            rotations[r.id] = int(r.rotation or 0)
    db.session.commit()
    return {'rotated': len(rotations), 'rotations': rotations}


def apply_flags(user_id, bank_id, flags, snapshot=None) -> dict:
    """Bulk-reject the PENDING images carrying the given flags. Manual ✓/✕
    decisions are never flipped (only status='pending' is touched) — same
    contract as the dataset auto-triage. Returns per-flag reject counts.

    This is the mis-set-threshold accident in one click, so it snapshots what it
    flipped. ``snapshot``: pass a live :class:`bank_undo.Snapshot` to fold the
    pass into a wider undo step (the pipeline does); omit it and the call
    publishes its own offer."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    own_snapshot = snapshot is None
    if own_snapshot:
        snapshot = bank_undo.Snapshot('Auto-reject by flag')
    th = thresholds()
    out = {}
    for flag in flags or []:
        if flag not in _QUALITY_FLAGS + _SCORE_FLAGS:
            continue
        crit = _flag_filter(flag, th)
        if crit is None:
            continue
        rows = (BankImage.query.filter_by(bank_id=bank_id, status='pending')
                .filter(crit).all())
        for r in rows:
            snapshot.note(r, 'reject', flag)
            r.status, r.reject_reason = 'reject', flag
        out[flag] = len(rows)
    db.session.commit()
    if own_snapshot:
        snapshot.commit(bank_id)
    return out


# --- ↩ undo the last bulk decision ------------------------------------------
_UNDO_NAME_SAMPLE = 8        # conflicting files quoted back so the user can find them


def undo_offer(user_id, bank_id) -> dict | None:
    """{label, count, at} for the workspace's ↩ bar, or None. Rides in the bank
    payload the workspace already polls, which is what makes the offer survive a
    reload — the decision it takes back lives in the database, not in a tab."""
    if not get_bank(user_id, bank_id):
        return None
    return bank_undo.peek(bank_id)


def undo_last(user_id, bank_id) -> dict:
    """Put every row the last bulk decision changed back to what it was.

    Three outcomes per row, all counted, because a restore that quietly missed
    half of its rows would be worse than no undo at all:

    * **restored** — the row is still there and still carries what the action
      set, so it goes back to its recorded prior value (status AND reason: the
      flag counters read the reason column);
    * **missing** — the row left the bank since (a re-scan dropped a file that
      disappeared from the folder);
    * **conflict** — someone changed it since (another tab, ▶ Review, a later
      pass). It is LEFT ALONE and named: overwriting a newer decision with an
      older one is not "undo", it is a second accident.

    Rows the action never touched are untouched here by construction — only the
    snapshot's ids are read. Synchronous even on a big lot: the work is one
    indexed SELECT plus in-place writes over the ids we already know, so a
    5 000-image restore lands in well under a second — a progress bar would take
    longer to render than the job it reports on.
    """
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    if bank_jobs.running(bank_id):
        raise RuntimeError('a pass is running on this bank — stop it first')
    snap = bank_undo.take(bank_id)
    if not snap or not snap['rows']:
        raise ValueError('nothing to undo')

    entries = snap['rows']
    ids = list(entries)
    seen = set()
    restored = conflicts = 0
    conflict_names = []
    for i0 in range(0, len(ids), _SQL_IN_CHUNK):
        rows = BankImage.query.filter(
            BankImage.bank_id == bank_id,
            BankImage.id.in_(ids[i0:i0 + _SQL_IN_CHUNK])).all()
        for r in rows:
            seen.add(r.id)
            entry = entries[r.id]
            if (r.status, r.reject_reason) != tuple(entry['after']):
                conflicts += 1
                if len(conflict_names) < _UNDO_NAME_SAMPLE:
                    conflict_names.append(os.path.basename(r.relpath))
                continue
            r.status, r.reject_reason = entry['before']
            restored += 1
    db.session.commit()
    return {'label': snap['label'], 'total': len(ids), 'restored': restored,
            'missing': len(ids) - len(seen), 'conflicts': conflicts,
            'conflict_names': conflict_names}


# --- curation selectors (diversity · reference similarity) ------------------
# Both reuse the CLIP embeddings the ✨ Score pass already cached — no GPU, no
# re-scan (same contract as the semantic-dedup stage). They only ever build a
# SELECTION (a set of image ids the UI checks); the user reviews it before any
# Keep / Reject / Promote — nothing is mutated or deleted here.
_CURATION_MAX_N = 2000       # a curated LoRA set is 20–200 images; this is generous


def _pool_query(bank_id, th, *, status=None, flag=None, cluster=None,
                style=None, subfolder=None, search=None, exclude=None, tags=None,
                medium=None, angle=None):
    """The candidate-pool query for the curation selectors — the SAME filter
    composition as list_images (status ∩ flag ∩ cluster ∩ style ∩ subfolder ∩
    search ∩ NOT exclude), minus the ordering/pagination, so "give me 60 diverse
    images" is
    composable with whatever the grid is currently showing.

    Kept as its own function (a small, deliberate mirror of the list_images WHERE
    clauses) rather than a shared refactor: three curation-related branches touch
    this file in parallel, so an additive helper rebases clean where an edit to
    the list_images hot path would collide. When NO status is chosen the reject
    pile is excluded — you curate from what you might keep, never from the bin."""
    q = BankImage.query.filter_by(bank_id=bank_id)
    if status in ('pending', 'keep', 'reject'):
        q = q.filter(BankImage.status == status)
    else:
        q = q.filter(BankImage.status != 'reject')
    if flag == 'flagged':
        crits = [c for c in (_flag_filter(f, th) for f in _QUALITY_FLAGS)
                 if c is not None]
        q = q.filter(or_(*crits))
    elif flag == 'clean':
        q = q.filter(BankImage.quality_state == 'ok')
        # Every quality flag except 'unreadable' (that one IS the quality_state
        # already pinned to 'ok' above). Each criterion is NULL-safe, so a row
        # from a build that predates one of these scores still counts as clean
        # for it instead of dropping out of the chip entirely.
        for f in ('blur', 'noise', 'uniform', 'small', 'soft_detail', 'bars'):
            q = q.filter(~_flag_filter(f, th))
    elif flag == 'dups':
        q = q.filter(BankImage.dup_group.isnot(None))
    elif flag == 'semantic_dups':
        q = q.filter(BankImage.semantic_dup_group.isnot(None))
    elif flag == 'no_face':
        q = q.filter(BankImage.face_state == 'no_face')
    elif flag in _QUALITY_FLAGS + _SCORE_FLAGS:
        crit = _flag_filter(flag, th)
        if crit is not None:
            q = q.filter(crit)
    if cluster is not None:
        q = q.filter(BankImage.face_cluster == int(cluster))
    if style is not None:
        q = q.filter(BankImage.style_cluster == int(style))
    # The two newest facets narrow a curation pick exactly as they narrow the
    # grid — "60 diverse images, among the photographs, three-quarter only" has
    # to mean the same thing in both places or the selection stops matching what
    # the user is looking at.
    if medium in MEDIUM_KEYS:
        q = q.filter(BankImage.medium == medium)
    if angle in ANGLES:
        q = q.filter(_angle_case() == angle)
    if subfolder is not None:
        if subfolder == '':
            q = q.filter(~BankImage.relpath.contains(os.sep))
        else:
            q = q.filter(BankImage.relpath.startswith(subfolder + os.sep))
    return _apply_text_filters(q, search, exclude, tags)


def _pool_embeddings(bank, emb_by_path, filters):
    """(ids, E) for the filtered pool rows that HAVE a cached embedding: ids is a
    list ordered by image id (so every tie-break below is deterministic), E is the
    matching (m×d) float32 matrix, L2-normalised. Empty ids ⇒ E is None."""
    import numpy as np
    rows = (_pool_query(bank.id, thresholds(), **filters)
            .order_by(BankImage.id.asc()).all())
    base = os.path.realpath(bank.source_path)   # once, not once per row
    prefix = os.path.normcase(base + os.sep)
    ids, vecs = [], []
    for r in rows:
        # Fast path: the keys of emb_by_path were THEMSELVES produced by
        # _abs_under (the ✨ Score pass walks the same rows), so a lexical
        # normpath that HITS the dict is provably the very string realpath would
        # have returned — no filesystem call needed to know that. A miss is the
        # only case that can be a symlink/junction, and it falls through to the
        # real resolution, so the result set is identical either way. That matters
        # because realpath is a syscall and this loop runs once per pool image:
        # 756 ms of a 6 353-row pool, against 6 ms for the lexical form.
        p = os.path.normpath(os.path.join(base, r.relpath))
        emb = emb_by_path.get(p) if os.path.normcase(p).startswith(prefix) else None
        if emb is None:
            p = _abs_under(base, r.relpath)
            emb = emb_by_path.get(p) if p else None
        if emb is not None:
            ids.append(r.id)
            vecs.append(emb)
    if not ids:
        return ids, None
    E = np.stack(vecs).astype('float32')
    E /= (np.linalg.norm(E, axis=1, keepdims=True) + 1e-8)
    return ids, E


_TYPICALITY_DEFAULT = 0.5    # see select_diverse — 0 restores pure farthest-point
_TYPICALITY_K = 10           # neighbours whose mean similarity IS the local density
_TYPICALITY_BLOCK = 512      # rows per similarity block — NEVER a full (m×m) matrix
_TYPICALITY_Z = 3.0          # robust deviations below the median density = full penalty
_TYPICALITY_DECADES = 3.0    # novelty discount at full guard + full penalty: 10⁻³
_TYPICALITY_MIN_POOL = 32    # under this a median/MAD "tail" is noise — guard off

_BLAS_GEMM = ...             # unprobed sentinel; None once probed and unavailable


def _fast_gemm_nt():
    """scipy's single-precision GEMM (``A @ B.T``), or None when unreachable.

    WHY this exists, measured rather than assumed: the numpy wheels this app runs
    on ship WITHOUT an optimised BLAS (``threadpoolctl.threadpool_info()`` returns
    an empty list), so ``E @ E.T`` runs single-threaded at ~5 GFLOP/s. On a real
    6 353-image pool that is 12.6 s for ONE similarity pass — 89 % of a curation
    click. scipy's wheels bundle OpenBLAS (24 threads here): the identical product
    takes 0.14 s, ~90× less, for the same 62 GFLOP.

    scipy is not in ``requirements.txt``, and it does not need to be: this lane
    only runs when numpy is present, numpy only arrives with
    ``requirements-ml.txt``, and insightface (the first line of that file) depends
    on scipy. So every install that CAN reach this code has the fast path, and the
    numpy fallback below is the belt-and-braces branch, not the normal one.

    Probed once per process and remembered — importing scipy.linalg is ~200 ms."""
    global _BLAS_GEMM
    if _BLAS_GEMM is ...:
        try:
            from scipy.linalg.blas import sgemm
            _BLAS_GEMM = sgemm
        except Exception as e:  # noqa: BLE001 — no scipy / broken wheel = slow path
            logger.info('no scipy BLAS for curation sampling (%s); '
                        'falling back to numpy matmul', e)
            _BLAS_GEMM = None
    return _BLAS_GEMM


def _sim_block(A, E):
    """``A @ E.T`` for L2-normed float32 rows — the similarity block of the
    typicality pass, routed through an optimised BLAS when one is reachable.

    Returns a C-contiguous (len(A) × len(E)) float32 array: scipy hands back a
    Fortran-ordered result, and the ``np.partition(..., axis=1)`` that follows
    walks rows, so the copy pays for itself several times over.

    Float caveat, stated because it is the one thing this change can affect: a
    different BLAS sums the same products in a different order, so a similarity
    can differ from numpy's by ~1e-6 (measured max absolute deviation over the
    real bank). That is far below any threshold this module compares against, and
    the selections were verified id-for-id identical on the production bank across
    n ∈ {20, 60, 200} and typicality ∈ {0.25, 0.5, 1.0} — but it is an equality
    of results, not of bits. ``typicality=0`` never reaches here at all, so the
    golden "historical behaviour" path is untouched by construction."""
    import numpy as np
    gemm = _fast_gemm_nt()
    if gemm is not None and A.dtype == np.float32 and E.dtype == np.float32:
        try:
            return np.ascontiguousarray(gemm(1.0, A, E, trans_b=True))
        except Exception as e:  # noqa: BLE001 — never fail a click over an optimisation
            logger.warning('scipy BLAS gemm refused the pool (%s); using numpy', e)
    return A @ E.T


def _isolation_penalty(E, *, k=_TYPICALITY_K, block=_TYPICALITY_BLOCK):
    """How ALONE each row is, as (m,) floats in [0, 1] — 0 for anything at or above
    the pool's median local density, 1 for the genuinely isolated tail.

    Local density = mean cosine similarity to the ``k`` nearest OTHER rows (the
    same cached embeddings the whole curation lane uses). Turning that density
    into a penalty is done on a ROBUST scale — median and MAD, not min/max — for
    two reasons that matter here:

      • a single meme in 24 000 photos would own the whole min/max range and
        squash every real difference to nothing;
      • everything at or above the median density gets penalty exactly 0, so the
        normal population of the bank is left strictly untouched. This selector
        DISCOUNTS the isolated tail, it never REWARDS the centre — which is what
        keeps a typicality guard from quietly turning "the 60 most varied" into
        60 look-alikes from the middle of the cloud.

    The ramp is quadratic, so being *slightly* below the median density barely
    costs anything and only the real tail is hit hard: at 1 robust deviation the
    penalty is 0.11, at 2 it is 0.44, at 3 and beyond it saturates at 1.

    Memory: the similarity pass runs in row blocks, so peak allocation is
    (block × m) float32 (~49 MB at m=24 000, measured 148 MB peak including
    temporaries) instead of the ~2.3 GB a full ``E @ E.T`` would need.
    Deterministic — median/MAD/partition, no sampling, no RNG.

    Time: this is an exact all-pairs pass, Θ(m²·d) — the same shape of work the
    semantic-dedup stage already does, and the reason the guard is computed ONLY
    when it is on. It is also, by a wide margin, the most expensive thing a
    curation click does; ``_sim_block`` explains why the product goes through
    scipy's BLAS rather than numpy's (12.6 s → 0.14 s on a 6 353-image pool,
    measured — the numpy this app ships on has no optimised BLAS, so the "~50×
    slower" case that paragraph used to describe as a hazard WAS the normal one).
    An approximation (subsampling the reference set) was rejected on purpose: it
    would make a small but legitimate group — eight shots of one rare outfit —
    look isolated and get penalised, which is exactly the variety this selector
    exists to preserve."""
    import numpy as np
    m = int(E.shape[0])
    k = min(int(k), m - 1)
    if k < 1 or m < _TYPICALITY_MIN_POOL:
        # Too few rows for a median and a MAD to mean anything: a 12-image pool
        # has no "isolated tail", only 12 images. Staying out is the honest
        # answer AND keeps small banks on the historical behaviour.
        return np.zeros(m, dtype='float32')
    dens = np.empty(m, dtype='float32')
    for a in range(0, m, block):
        S = _sim_block(E[a:a + block], E)    # (b, m) block — never (m, m)
        rows = np.arange(S.shape[0])
        S[rows, rows + a] = -np.inf          # a row is not its own neighbour
        top = np.partition(S, m - k, axis=1)[:, m - k:]
        dens[a:a + block] = top.mean(axis=1)
    med = float(np.median(dens))
    mad = float(np.median(np.abs(dens - med)))
    scale = 1.4826 * mad                     # MAD → σ-comparable, robust
    if not (scale > 1e-6):                   # degenerate pool (all alike) ⇒ no tail
        return np.zeros(m, dtype='float32')
    z = (med - dens) / scale                 # >0 only BELOW the median density
    ramp = np.clip(z / _TYPICALITY_Z, 0.0, 1.0)
    return (ramp * ramp).astype('float32')


def _farthest_point(E, factor, n):
    """Greedy farthest-point sampling over the L2-normed rows of ``E`` (m×d),
    returning ``n`` ROW POSITIONS in pick order. Seeded on position 0 — callers
    pass rows in ascending id order, so the seed and every tie-break resolve to
    the lowest id and the result is deterministic.

    ``factor`` is the per-row novelty multiplier in (0, 1] (the typicality guard,
    see ``_isolation_penalty``) or None to sample on pure max-min distance. Shared
    by ``select_diverse`` (whole pool) and ``select_balanced`` (one call per
    bucket, on a slice of the same E and the same pool-wide factor) so the guard
    behaves identically in both — there is exactly one copy of this loop."""
    import numpy as np
    m = int(E.shape[0])
    if n <= 0 or m == 0:
        return []
    if n >= m:
        return list(range(m))
    # min_dist[i] = cosine distance from row i to the NEAREST chosen row so far.
    chosen = [0]                                 # seed = lowest id (E[0])
    min_dist = 1.0 - E @ E[0]
    min_dist[0] = -np.inf                        # never re-pick a chosen row
    for _ in range(n - 1):
        score = min_dist if factor is None else min_dist * factor
        nxt = int(np.argmax(score))              # ties → lowest index = lowest id
        if not np.isfinite(score[nxt]):          # pool exhausted (all chosen)
            break
        chosen.append(nxt)
        min_dist = np.minimum(min_dist, 1.0 - E @ E[nxt])
        min_dist[nxt] = -np.inf
    return chosen


def select_diverse(user_id, bank_id, n=60, *, typicality=_TYPICALITY_DEFAULT,
                   filters=None):
    """Farthest-point sampling over the ✨ Score CLIP embeddings, tempered by a
    TYPICALITY guard: the ``n`` images of the (filtered) pool that best COVER the
    visual space — the antidote to a dump of 4 000 near-identical shots. Greedy
    FPS: seed with the lowest-id row (deterministic), then repeatedly add the
    point whose nearest already-chosen neighbour is FARTHEST (max-min cosine
    distance). The SAMPLING itself is O(n·m·d) — one (m×d)·(d,) product per pick,
    110 ms at m=6 353 / n=60 (measured).

    That figure used to be quoted as the cost of the WHOLE call ("~sub-second
    even at m=24 000"), and on real data it was wrong by a factor of thirty: the
    click took 32 s, of which the loop below was 0.1 s. The rest was the guard's
    all-pairs pass (see ``_isolation_penalty`` / ``_sim_block``). Whatever else
    changes here, keep this docstring measured — a comment promising a second
    where the user waits half a minute is a debt, not documentation.

    ``typicality`` (0–1) exists because pure max-min distance is, mathematically,
    the criterion that prefers ISOLATED points: on a collected bank the first
    picks are therefore structurally biased towards the aberrations (a meme, a
    photo of someone else, a botched frame) rather than towards variety of the
    subject. Each candidate's novelty is multiplied by
    ``10 ** (-3 × typicality × isolation)`` (see ``_isolation_penalty``), so an
    image still gets picked for the variety it adds, but being alone stops being
    a quality in itself. The discount is GEOMETRIC on purpose: an aberration's
    distance advantage over a normal image is a ratio (2–4× in practice, and it
    grows as the easy variety gets used up), so a merely linear penalty would need
    a near-maximal setting to ever bite.

      • 0    → EXACTLY the historical behaviour, pick for pick (the guard is not
               even computed);
      • 0.5  → the default: a saturated outlier keeps ~3% of its novelty (÷32) —
               decisively beaten by any genuinely varied shot — while a merely
               below-average image (penalty 0.11) keeps 68%;
      • 1    → the isolated tail is all but excluded (÷1000).

    The guard is bounded on BOTH sides: rows at or above the median density are
    never penalised at all (factor exactly 1.0), so it cannot collapse the
    selection into look-alikes from the middle of the cloud.

    Returns {'image_ids': [...] (sorted), 'pool': m, 'requested': n,
    'typicality': w}. Raises ValueError (→400, "run ✨ Score first") when no
    embedding exists yet, so the UI shows the clear hint instead of an empty,
    unexplained selection."""
    import numpy as np
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    emb_by_path = _load_score_embeddings(bank)
    if not emb_by_path:
        raise ValueError('run ✨ Score first — diversity sampling reuses its '
                         'embeddings')
    n = max(1, min(int(n), _CURATION_MAX_N))
    try:
        w = 0.0 if typicality is None else float(typicality)
    except (TypeError, ValueError):
        w = _TYPICALITY_DEFAULT
    w = max(0.0, min(1.0, w))
    ids, E = _pool_embeddings(bank, emb_by_path, filters or {})
    m = len(ids)
    if m <= n:                                   # whole pool already fits
        return {'image_ids': sorted(ids), 'pool': m, 'requested': n,
                'typicality': w}
    # Novelty multiplier, in (0, 1] — never 0, so the -inf "already chosen"
    # sentinel below stays -inf (0 × -inf would be a NaN) and so even a fully
    # penalised row stays a last resort rather than an unpickable one.
    factor = None
    if w > 0.0:
        factor = 10.0 ** (-_TYPICALITY_DECADES * w * _isolation_penalty(E))
    chosen = _farthest_point(E, factor, n)
    return {'image_ids': sorted(ids[i] for i in chosen),
            'pool': m, 'requested': n, 'typicality': w}


# --- balanced selection (coverage of the LABELS, not of the embedding space) --
# `select_diverse` answers "is my set VARIED?"; this one answers a different
# question no per-image score can ask: "does my set COVER what I want to be able
# to generate?". Asking for the 60 best/most varied of a bank that is 49% full
# body and 3.6% face shots returns those proportions — the LoRA then renders one
# framing well and the rest badly, with nothing having said so.
#
# WHICH AXIS. Measured on a real 43 000-image bank rather than assumed: `framing`
# had 13 000 rows classified across all four buckets (body 49%, bust 37%, back
# 11%, face 3.6%) — a discrete label with a real, actionable imbalance. Over the
# same bank `face_cluster` covered 4.7% of the rows and shattered them into 561
# clusters whose biggest held 34% — on a mono-subject bank a semantic/identity
# split is sparse and arbitrary, so balancing on it would spread a selection over
# noise. Hence: framing is the DEFAULT axis, and person is an explicit opt-in for
# the genuinely multi-subject dump.
_BALANCE_AXES = ('framing', 'framing+person')
_BALANCE_DEFAULT_AXIS = 'framing'   # stored in localStorage — never rename


def _balanced_quotas(sizes: dict, n: int) -> dict:
    """Split ``n`` picks as evenly as possible over the buckets, capped by what
    each one actually HAS (largest-remainder water-filling).

    A bucket that cannot serve its equal share is filled to the brim and its
    unused share is redistributed over the buckets that still have room — the
    ARBITRATION being: asking for 60 when a perfect split only yields 42 returns
    60, not 42, because throwing 18 usable images away buys a purity nobody asked
    for. What is forbidden is doing it SILENTLY: every caller gets ``fair_share``
    next to ``selected`` per bucket, so the top-up is visible as the deficit it
    is. Deterministic: buckets are walked in sorted key order, and a leftover
    single pick goes to the bucket with the most room left (key ascending on a
    tie)."""
    keys = sorted(sizes)
    quota = {k: 0 for k in keys}
    open_keys = [k for k in keys if sizes[k] > 0]
    remaining = min(int(n), sum(sizes.values()))
    while open_keys and remaining > 0:
        base = remaining // len(open_keys)
        if base == 0:                       # fewer picks left than buckets
            order = sorted(open_keys, key=lambda k: (-(sizes[k] - quota[k]), k))
            for k in order[:remaining]:
                quota[k] += 1
            break
        capped = [k for k in open_keys if sizes[k] - quota[k] <= base]
        if capped:
            for k in capped:
                take = sizes[k] - quota[k]
                quota[k] += take
                remaining -= take
            capped_set = set(capped)
            open_keys = [k for k in open_keys if k not in capped_set]
        else:
            for k in open_keys:
                quota[k] += base
            remaining -= base * len(open_keys)
    return quota


def _pool_labels(bank, filters) -> dict:
    """{image_id: (framing, face_cluster)} for the same pool ``_pool_embeddings``
    walks — one extra column read, no GPU."""
    rows = _pool_query(bank.id, thresholds(), **(filters or {})).all()
    return {r.id: (r.framing, r.face_cluster) for r in rows}


def _balance_axis_hint(axis, m, unlabelled, unknown) -> str:
    """The honest message for a bank that simply has not been labelled yet — the
    DEFAULT state of a fresh bank, not an error. Names the pass that is missing
    and the numbers, instead of returning an empty or misleading selection."""
    what = ('the shot type of each image' if axis == 'framing'
            else 'the shot type AND the person of each image')
    passes = ('run the 📐 Framing pass first' if axis == 'framing'
              else 'run the 📐 Framing and 👥 Group by person passes first')
    tail = ''
    if unknown and not unlabelled:
        tail = (f' — {unknown} of {m} came back as "unknown" framing, which is a '
                f'classification the balance cannot use')
    else:
        tail = f' — {unlabelled} of {m} images here have no label yet'
    return (f'{passes}: balanced selection needs {what}{tail}. '
            f'🎨 Pick diverse works without it.')


def select_balanced(user_id, bank_id, n=60, *, axis=_BALANCE_DEFAULT_AXIS,
                    typicality=_TYPICALITY_DEFAULT, filters=None):
    """Select ``n`` images SPREAD OVER the labels of ``axis`` instead of taking
    the top of one ranking: an even split across framings (and optionally across
    people), each bucket filled with the same farthest-point + typicality
    sampling ``select_diverse`` uses. So it is "the most varied 15 face shots,
    the most varied 15 busts, …" rather than "the most varied 60", which on a
    lopsided bank is 30 bodies and 2 faces.

    It ACCOMPANIES ``select_diverse``, it does not replace it: variety inside a
    space and coverage of a label are different questions, and the diverse
    selector still works on a bank with no labels at all (which is most banks
    until the 📐 Framing pass has run).

    Composition with the typicality guard: the isolation penalty is computed ONCE
    over the WHOLE filtered pool and then sliced per bucket — deliberately, since
    "alone in the bank" is a property of the bank. Computing it per bucket would
    make every member of a small bucket look isolated and penalise exactly the
    images the balance exists to bring in.

    Returns {'image_ids', 'pool', 'requested', 'selected', 'typicality', 'axis',
    'buckets': [{key, framing, cluster, available, fair_share, selected, short}],
    'unlabelled', 'unknown', 'shortfall'}. Raises ValueError (→400) when Score
    has not run, or when nothing in the filter carries the axis label."""
    import numpy as np
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    if axis not in _BALANCE_AXES:
        axis = _BALANCE_DEFAULT_AXIS
    emb_by_path = _load_score_embeddings(bank)
    if not emb_by_path:
        raise ValueError('run ✨ Score first — balanced selection reuses its '
                         'embeddings')
    n = max(1, min(int(n), _CURATION_MAX_N))
    try:
        w = 0.0 if typicality is None else float(typicality)
    except (TypeError, ValueError):
        w = _TYPICALITY_DEFAULT
    w = max(0.0, min(1.0, w))
    ids, E = _pool_embeddings(bank, emb_by_path, filters or {})
    m = len(ids)
    if not m:
        raise ValueError('nothing to select from in the current filter')

    labels = _pool_labels(bank, filters or {})
    buckets, meta = {}, {}
    unlabelled = unknown = 0
    for pos, iid in enumerate(ids):
        fr, cl = labels.get(iid, (None, None))
        if fr is None:
            unlabelled += 1
            continue
        if fr not in _FRAMINGS:              # 'unknown' — a real classification,
            unknown += 1                     # but not one you can balance on
            continue
        if axis == 'framing+person':
            if cl is None:
                unlabelled += 1
                continue
            key = f'{fr}#{int(cl)}'
            meta[key] = (fr, int(cl))
        else:
            key = fr
            meta[key] = (fr, None)
        buckets.setdefault(key, []).append(pos)
    if not buckets:
        raise ValueError(_balance_axis_hint(axis, m, unlabelled, unknown))

    sizes = {k: len(v) for k, v in buckets.items()}
    quota = _balanced_quotas(sizes, n)
    # What a split with no ceiling WOULD have given each bucket — the yardstick
    # a shortfall is reported against ("back: 3 of an even 15").
    fair = _balanced_quotas({k: n for k in sizes}, n)

    factor = None
    if w > 0.0:
        factor = 10.0 ** (-_TYPICALITY_DECADES * w * _isolation_penalty(E))
    chosen, report = [], []
    for key in sorted(sizes):
        pos = buckets[key]                   # ascending id order (pool order)
        take = quota[key]
        if take >= len(pos):
            picked = list(pos)
        elif take <= 0:
            picked = []
        else:
            idx = np.asarray(pos)
            sub = np.ascontiguousarray(E[idx])
            subf = None if factor is None else np.ascontiguousarray(factor[idx])
            picked = [pos[i] for i in _farthest_point(sub, subf, take)]
        chosen.extend(picked)
        fr, cl = meta[key]
        report.append({'key': key, 'framing': fr, 'cluster': cl,
                       'available': len(pos), 'fair_share': fair[key],
                       'selected': len(picked),
                       'short': len(pos) < fair[key]})
    order = {k: i for i, k in enumerate(_FRAMINGS)}
    report.sort(key=lambda b: (order.get(b['framing'], 99),
                               b['cluster'] if b['cluster'] is not None else -1))
    return {'image_ids': sorted(ids[i] for i in chosen),
            'pool': m, 'requested': n, 'selected': len(chosen),
            'typicality': w, 'axis': axis, 'buckets': report,
            'unlabelled': unlabelled, 'unknown': unknown,
            'shortfall': max(0, n - len(chosen))}


def select_similar(user_id, bank_id, ref_id, n=60, min_score=None, *, filters=None):
    """Rank the (filtered) pool by CLIP cosine similarity to a REFERENCE bank image
    (its own cached ✨ Score embedding) — "keep what looks like THIS", to pull one
    person / look out of a mixed dump. Returns the top-``n`` most similar ids, OR
    everything with cosine ≥ ``min_score`` when that is given; the reference itself
    (cosine 1.0) is always included. Reuses the cached embeddings — no GPU.

    Returns {'results': [{id, score}], 'image_ids': [...], 'pool': m, 'ref_id'}.
    Raises ValueError (→400) when Score hasn't run or the reference has no cached
    embedding (e.g. it was rejected before Score, or edited since)."""
    import numpy as np
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    emb_by_path = _load_score_embeddings(bank)
    if not emb_by_path:
        raise ValueError('run ✨ Score first — reference similarity reuses its '
                         'embeddings')
    ref = db.session.get(BankImage, int(ref_id))
    if ref is None or ref.bank_id != bank_id:
        raise ValueError('reference image not found in this bank')
    ref_path = abs_image_path(bank, ref)
    ref_emb = emb_by_path.get(ref_path) if ref_path else None
    if ref_emb is None:
        raise ValueError('the reference image has no ✨ Score embedding — score '
                         'it first (it may have been rejected before Score ran)')
    ids, E = _pool_embeddings(bank, emb_by_path, filters or {})
    if not ids:
        return {'results': [], 'image_ids': [], 'pool': 0, 'ref_id': int(ref_id)}
    rv = np.asarray(ref_emb, dtype='float32')
    rv /= (np.linalg.norm(rv) + 1e-8)
    sims = E @ rv                                 # cosine similarity, (m,)
    order = np.argsort(-sims, kind='stable')     # desc; stable ⇒ id tie-break
    if min_score is not None:
        keep = [int(k) for k in order if sims[k] >= float(min_score)]
    else:
        n = max(1, min(int(n), _CURATION_MAX_N))
        keep = [int(k) for k in order[:n]]
    results = [{'id': ids[k], 'score': round(float(sims[k]), 4)} for k in keep]
    return {'results': results, 'image_ids': [ids[k] for k in keep],
            'pool': len(ids), 'ref_id': int(ref_id)}


# ── 🔤 pushing an attribute DOWN a text ranking ──────────────────────────────
# CLIP has no negation: "a woman without a bikini" ranks bikinis HIGHER, because
# the word is ignored rather than applied (measured: 60% of the top 60 carried
# a bikini against a 10.1% base rate — an inversion, not a miss). What the
# embedding space DOES support is arithmetic, so the exclusion is subtracted
# instead of spoken: score = sim(positive) − weight · sim(excluded).
#
# The weight below was calibrated on 2026-08-01 over 7,316 real bank images that
# carry BOTH a cached CLIP embedding and a vision caption — the caption supplies
# the ground truth (a different model from CLIP, so the labels are not circular).
# 19 positive/excluded pairs, top-60 measured against the app's own default n:
#
#   weight   top-60 carrying the excluded trait   top-60 still on-topic
#     0.00              23.0% (mean)                    89.7% (mean)
#     0.30              11.9%                           89.5%
#     0.50               8.9%                           88.5%
#     0.60               7.6%                           87.7%   ← the knee
#     0.75               6.3%                           85.8%
#     1.00               3.8%                           79.8%
#     1.50               1.4%                           64.4%
#
# Exclusion improves all the way up; RELEVANCE is what buys it, and it holds
# essentially flat to 0.6 (−2.0 points) then falls off a cliff (−9.9 at 1.0,
# −25.3 at 1.5). 0.6 is where two thirds of the unwanted trait is gone for a
# cost the ranking does not feel. The extremes are offered as Gentle/Strong
# because one measured case — excluding "a bikini" from "a woman at the beach"
# — is INSEPARABLE (the trait is most of what the positive query means), and no
# weight fixes that: at 0.6 it still returned 66.7% bikinis, and by the time the
# weight bites the beach is gone too. That case is why the UI promises a
# push-down and never an absence.
PUSH_DOWN_WEIGHT_DEFAULT = 0.6
PUSH_DOWN_WEIGHT_MAX = 2.0


def _push_down_weight(value):
    """The requested push-down strength, clamped. Anything unreadable falls back
    to the calibrated default rather than to 0 — a silently ignored exclusion
    would look exactly like an exclusion that found nothing."""
    try:
        w = float(value)
    except (TypeError, ValueError):
        return PUSH_DOWN_WEIGHT_DEFAULT
    if w != w:                                   # NaN
        return PUSH_DOWN_WEIGHT_DEFAULT
    return max(0.0, min(w, PUSH_DOWN_WEIGHT_MAX))


def search_by_text(user_id, bank_id, query, n=60, *, push_down=None,
                   push_down_weight=None, filters=None):
    """Rank the (filtered) pool by CLIP similarity to a written QUERY — "brunette
    outdoors, wide shot" instead of a reference picture.

    Mechanically this is ``select_similar`` with the reference vector produced by
    CLIP's TEXT tower rather than read from the image cache: same embeddings, same
    cosine, same deterministic stable-argsort ordering. Ranking costs no GPU and no
    re-scan; only encoding the phrase leaves the Flask process (see
    clip_text_encoder, which caches every phrase on disk).

    It REFINES the current filter rather than replacing it — the candidate pool is
    exactly what the grid is showing, so "wide shot, inside this subfolder, among
    the undecided" composes without a second search grammar.

    TOP-N ONLY — there is deliberately no similarity threshold, and adding one
    would be a mistake rather than a feature. Measured on a real bank (48 images,
    8 unrelated datasets, this exact model): verified-correct top-1 hits scored
    0.177–0.233, while guaranteed-unrelated pairs reached up to 0.197 (median
    0.112). The two distributions OVERLAP — the unrelated ceiling outranks two
    genuinely correct answers. No cut exists that separates "relevant" from
    "unrelated": below ~0.20 it admits false positives, above ~0.18 it discards
    true ones. A threshold control would therefore offer the illusion of a
    boundary that does not exist, so the ranking is the whole product.

    ``push_down`` (or ``-term`` inside the query) names what to push DOWN. It is
    NOT a filter and the UI must never call it one: the excluded phrase is
    encoded like the positive one and SUBTRACTED, weighted, from the score, so
    an image that matches it falls in the ranking instead of disappearing. See
    PUSH_DOWN_WEIGHT_DEFAULT above for the calibration and for the measured case
    where it cannot work at all.

    Returns {'results': [{id, score}], 'image_ids', 'pool', 'filtered', 'unscored',
    'query', 'cached', 'score_range', 'pool_median', 'push_down', 'push_down_weight',
    'push_down_moved', 'push_down_median'}.
      * ``unscored`` — an image with no ✨ Score embedding CANNOT be found by text;
        saying "0 results" without saying that would let the user conclude the
        image is gone.
      * ``pool_median`` — the median cosine over the WHOLE candidate pool for this
        query. It is the empirical "what a typical image here scores" baseline,
        measured per bank and per query, and it is what lets the UI judge whether
        a ranking discriminates at all without hard-coding any constant. On a
        single-subject bank (image-to-image cosine 0.60–0.89) the discriminating
        gap compresses by 30–70%, and that is the app's MAIN use case, not an
        edge case — so the baseline has to be measured, never assumed.
      * ``push_down_median`` — {pool, results}: how strongly a TYPICAL image of
        this bank matches the excluded phrase, against how strongly the returned
        set does. Same reasoning as ``pool_median``, applied to the push-down:
        results well below pool means it worked here, results level with pool
        means it did not, and neither claim needs a universal constant. This is
        the only honest way to report an exclusion whose strength depends
        entirely on how entangled the two phrases are in this corpus.
      * ``push_down_moved`` — how many places in the returned ranking hold a
        different image than they would have without the exclusion. 0 is the
        signal that the push-down changed nothing at all, which the UI has to
        say out loud.

    Raises ValueError (→400) for an empty query or an unscored bank, and
    clip_text_encoder.TextEncodeError (→503) when no interpreter can run CLIP."""
    import numpy as np
    from . import clip_text_encoder
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    # `-term` inside the query means the same thing as the panel's second field,
    # so both are folded into one excluded phrase before anything is encoded.
    positive, from_query = clip_text_encoder.split_query(query)
    text = clip_text_encoder.normalize_query(positive)
    excl = ', '.join(t for t in (clip_text_encoder.normalize_query(push_down),
                                 clip_text_encoder.normalize_query(from_query)) if t)
    if not text:
        # A bare "-hat" is not a search. Ranking by "least like a hat" would
        # return whatever is least like ANYTHING, which is noise wearing the
        # costume of an answer — so it is refused rather than served.
        raise ValueError('a search query is required — an excluded term alone '
                         'cannot rank anything')
    weight = _push_down_weight(push_down_weight if push_down_weight is not None
                               else PUSH_DOWN_WEIGHT_DEFAULT)
    emb_by_path = _load_score_embeddings(bank)
    if not emb_by_path:
        raise ValueError('run ✨ Score first — text search ranks the embeddings '
                         'it computes')
    filters = filters or {}
    # How many rows the current filter holds AT ALL — the denominator that makes
    # "searched 120 of 400" (and therefore the unscored warning) truthful.
    filtered = _pool_query(bank_id, thresholds(), **filters).count()
    ids, E = _pool_embeddings(bank, emb_by_path, filters)
    # Encode AFTER the cheap refusals: never make someone wait on a CLIP load to
    # then be told their bank was never scored.
    qv, cached = clip_text_encoder.encode_query(text)
    nv = None
    if excl:
        # A second encode, and a second phrase in the same persistent cache — so
        # a repeated exclusion is as free as a repeated query. `cached` stays
        # true only when BOTH halves were already known, because it is shown to
        # promise instant, and half a cache hit is not instant.
        nv, ncached = clip_text_encoder.encode_query(excl)
        cached = bool(cached) and bool(ncached)
    base = {'query': text, 'cached': bool(cached), 'filtered': int(filtered),
            'pool': len(ids), 'unscored': max(0, int(filtered) - len(ids)),
            'push_down': excl or None,
            'push_down_weight': round(weight, 3) if excl else None}
    if not ids:
        return {**base, 'results': [], 'image_ids': [], 'score_range': None,
                'pool_median': None, 'push_down_moved': None,
                'push_down_median': None}
    qv = np.asarray(qv, dtype='float32')
    qv /= (float(np.linalg.norm(qv)) + 1e-8)
    sims = E @ qv                                # cosine similarity, (m,)
    n = max(1, min(int(n), _CURATION_MAX_N))
    excl_sims = None
    scores = sims
    if nv is not None:
        nv = np.asarray(nv, dtype='float32')
        nv /= (float(np.linalg.norm(nv)) + 1e-8)
        excl_sims = E @ nv
        scores = sims - weight * excl_sims
    order = np.argsort(-scores, kind='stable')   # desc; stable ⇒ id tie-break
    keep = [int(k) for k in order[:n]]
    # The RANKING score is what ordered the list, so it is what the list reports:
    # showing the raw positive cosine here would make the order look arbitrary
    # (a lower-cosine image legitimately outranks a higher one once its excluded
    # match is paid for). Both halves are kept alongside so nothing is hidden.
    results = [{'id': ids[k], 'score': round(float(scores[k]), 4)} for k in keep]
    if excl_sims is not None:
        for r, k in zip(results, keep):
            r['match'] = round(float(sims[k]), 4)
            r['excluded_match'] = round(float(excl_sims[k]), 4)
    # The span of what came back, plus the pool's own median — together they let
    # the UI say whether this ranking discriminates, using only numbers measured
    # on THIS bank for THIS query. An absolute band would be wrong everywhere:
    # the same model's "good" ceiling barely moves between corpora while its
    # floor climbs sharply on real photographs of people.
    # The range is always in POSITIVE-match units, never in composite ones: it is
    # read against ``pool_median`` to decide whether the ranking discriminates,
    # and a composite score (which can even go negative) is not on that scale.
    # Without an exclusion this is exactly the old first/last pair; with one it
    # is the best and worst MATCH among what came back, which is the thing the
    # sentence above the grid actually claims.
    match_of = [float(sims[k]) for k in keep]
    score_range = ({'top': round(max(match_of), 4),
                    'bottom': round(min(match_of), 4)} if results else None)
    moved = excl_median = None
    if excl_sims is not None:
        # What the SAME query would have returned unexcluded — the only way to
        # tell the user whether the push-down did anything, rather than leaving
        # them to compare two screens from memory.
        #
        # POSITIONS changed, not membership. Membership alone is silently wrong
        # whenever n reaches the whole pool: asking for 60 out of 22 images
        # returns the same 22 however hard the push, so a membership count reads
        # 0 and the UI announces "changed nothing" over a grid the user can SEE
        # was reordered. Comparing the two orderings slot by slot is right in
        # both regimes — it counts newcomers when the list is a cut of a larger
        # pool, and re-ranking when it is not.
        plain = [int(k) for k in np.argsort(-sims, kind='stable')[:n]]
        moved = int(sum(1 for a, b in zip(keep, plain) if a != b))
        if len(keep) < len(ids):
            excl_median = {'pool': round(float(np.median(excl_sims)), 4),
                           'results': round(float(np.median(excl_sims[keep])), 4)}
        # else: the returned set IS the pool, so its median and the pool's are
        # the same number BY CONSTRUCTION. Reporting them would let the UI read
        # "level with a typical image — too tangled to separate" off an identity,
        # which is how it once declared a visibly-reordered grid a failure. When
        # a comparison cannot carry information, the honest output is none: the
        # places-changed count already says what happened.
    return {**base, 'results': results,
            'image_ids': [ids[k] for k in keep], 'score_range': score_range,
            'pool_median': round(float(np.median(sims)), 4),
            'push_down_moved': moved, 'push_down_median': excl_median}


def _trash_or_remove(path: str) -> str:
    """Get a rejected source file out of the user's folder, keeping it
    recoverable (OS trash → app trash → permanent unlink). The policy itself is
    app-wide and lives in ``services.trash``; this is the bank's entry point into
    it, kept as a name because the tests and the delete sweep both address it."""
    return trash.dispose(path, context='bank-rejected')


def _bank_folders(user_id, exclude_id=None) -> list:
    """[(bank, normalised realpath)] for the user's banks with a usable folder."""
    out = []
    for b in ImageBank.query.filter_by(user_id=user_id).all():
        if exclude_id is not None and b.id == exclude_id:
            continue
        if not b.source_path:
            continue
        try:
            out.append((b, os.path.normcase(os.path.realpath(b.source_path))))
        except (OSError, ValueError):
            continue
    return out


def overlapping_banks(user_id, bank_id) -> list:
    """The user's OTHER banks whose folder contains, or sits inside, this one's.

    Two banks over nested folders see the same files, and a bank never owns its
    source folder — so a delete run from one silently amputates the other. The
    UI has to be able to say so BEFORE the click. Returns
    [{'id', 'name', 'source_path', 'relation'}] with relation 'parent' (it
    contains us) or 'child' (it sits inside us)."""
    bank = get_bank(user_id, bank_id)
    if not bank or not bank.source_path:
        return []
    try:
        mine = os.path.normcase(os.path.realpath(bank.source_path))
    except (OSError, ValueError):
        return []
    out = []
    for other, theirs in _bank_folders(user_id, exclude_id=bank_id):
        if theirs == mine:
            relation = 'same'
        elif mine.startswith(theirs + os.sep):
            relation = 'parent'
        elif theirs.startswith(mine + os.sep):
            relation = 'child'
        else:
            continue
        out.append({'id': other.id, 'name': other.name,
                    'source_path': other.source_path, 'relation': relation})
    return sorted(out, key=lambda o: o['id'])


class BankSharesDataset(ValueError):
    """A destructive action was asked of a bank whose folder IS a dataset's.

    A subclass of ValueError so nothing that already catches ValueError starts
    500-ing, but a distinct type so the one route that answers 404 to "bank not
    found" can tell this apart and answer 400 with the explanation instead."""


def bank_dataset_conflict(user_id, bank_id) -> dict | None:
    """Does THIS bank already sit on a dataset's storage folder? None when it
    does not — which is every bank the guard in create_bank/_relocate_target has
    ever seen.

    The guard alone protects nobody who already has such a bank: it was created
    before the guard existed, it is in their database right now, and the click
    that hurts is 🗑 Delete rejected. So the conflict is DETECTED at open time
    (it rides in the workspace payload, which is also the 2 s poll — one
    realpath, no walk) and the destructive action refuses. Deliberately nothing
    else: the bank stays fully readable and fully triageable, and NOTHING is
    ever removed on the app's own initiative. Only the user can decide whether
    that bank should be relocated or dropped."""
    bank = get_bank(user_id, bank_id)
    if not bank or not bank.source_path:
        return None
    return path_guard.dataset_folder_conflict(bank.source_path)


def rejected_delete_preview(user_id, bank_id) -> dict | None:
    """What a 🗑 Delete rejected would actually destroy — the honest warning the
    confirmation needs. Counts the rejected files of this bank that ANOTHER bank
    also lists, per bank, by matching absolute paths against that bank's own
    inventory. None when the bank is gone.

    Returns {'rejected', 'mode', 'shared': [{'id','name','relation','files'}]}.
    ``mode`` is where the files would go, resolved the same way the deletion
    resolves it, so the dialog never promises the wrong thing."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    rows = BankImage.query.filter_by(bank_id=bank_id, status='reject').all()
    mine = {}
    for r in rows:
        p = abs_image_path(bank, r)
        if p:
            mine[os.path.normcase(p)] = True
    shared = []
    for other in overlapping_banks(user_id, bank_id):
        ob = db.session.get(ImageBank, other['id'])
        if ob is None:
            continue
        n = 0
        for (rel,) in db.session.query(BankImage.relpath).filter_by(bank_id=ob.id):
            try:
                full = os.path.normcase(os.path.realpath(
                    os.path.join(os.path.realpath(ob.source_path), rel)))
            except (OSError, ValueError):
                continue
            if full in mine:
                n += 1
        if n:
            shared.append({'id': other['id'], 'name': other['name'],
                           'relation': other['relation'], 'files': n})
    return {'rejected': len(rows), 'mode': _delete_mode(), 'shared': shared,
            # The hard stop, next to the soft warnings: another BANK losing files
            # is a warning the user may accept, a DATASET losing them is not.
            'dataset_conflict': bank_dataset_conflict(user_id, bank_id)}


def _delete_mode() -> str:
    """Where a deleted source file WOULD go, without deleting anything, so the
    confirmation can say it. Same probe as ``services.trash.disposal_mode``."""
    return trash.disposal_mode()


def _delete_rejected_guard(user_id, bank_id, check_busy=True):
    """The three refusals 🗑 Delete rejected owes the caller BEFORE anything is
    touched — unknown bank, occupied bank, folder shared with a dataset. Split
    out so the route can answer 404/409/400 synchronously while the deletion
    itself runs in the background. ``check_busy`` is off for the job's own body:
    by then the registry holds OUR job and would refuse us."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    if check_busy and bank_jobs.running(bank_id):
        raise RuntimeError('a job is running on this bank — stop it first')
    # An install that predates the create-time guard can still hold a bank whose
    # folder IS a dataset's. Here, and only here, that stops being cosmetic: these
    # "rejects" are the dataset's images. Refuse — never silently delete, never
    # silently clean up on the user's behalf.
    conflict = bank_dataset_conflict(user_id, bank_id)
    if conflict:
        raise BankSharesDataset(
            'This bank points at a dataset\'s own image folder, so deleting its '
            'rejected files would delete images out of the dataset. Nothing was '
            f'deleted. {conflict["message"]}')
    return bank


_DELETE_DETAIL = {
    'trash': 'moving files to the Recycle Bin',
    'app_trash': 'moving files to the app Trash',
    'delete': 'deleting files permanently',
}


def delete_rejected_summary(out: dict) -> str:
    """One plain sentence for the progress bar / completion toast. The workspace
    already toasts a finished job's ``detail``, so this IS the outcome the user
    reads — it must carry the numbers, not the word "done"."""
    gone = out['deleted'] + out['trashed'] + out['already_absent']
    where = ('permanently deleted' if out['mode'] == 'delete'
             else 'moved to the app Trash' if out['mode'] == 'app_trash'
             else 'moved to the Recycle Bin')
    text = f'{gone} rejected file(s) {where}'
    if out['skipped']:
        text += f' · {len(out["skipped"])} could not be removed and kept their row'
    return text


def start_delete_rejected(app, user_id, bank_id) -> dict:
    """Start 🗑 Delete rejected as a background bank job and return immediately.

    THE WAIT THIS REPLACES: the deletion ran inside the POST. On a bank with
    thousands of rejects — every file individually handed to the OS Recycle Bin,
    which is not fast — the dialog sat on "Deleting…" for minutes with no count,
    no way to stop, and no way to tell a slow run from a crashed one. It is now
    an ordinary bank job: the same one-per-bank registry, the same progress bar,
    the same Stop button, the same completion toast as every other pass.

    Cancelling is safe by construction — each file is removed then its row
    dropped, so a stopped run leaves a consistent bank and simply has rejects
    left over. Returns {'total', 'job'}; ``job['result']`` holds the full
    outcome once it has finished (immediately so under TESTING, where bank_jobs
    runs inline)."""
    _delete_rejected_guard(user_id, bank_id)
    total = BankImage.query.filter_by(bank_id=bank_id, status='reject').count()

    def _run(job):
        out = delete_rejected(user_id, bank_id, job=job)
        job['result'] = out
        bank_jobs.progress(job, detail=delete_rejected_summary(out))

    job = bank_jobs.start(app, bank_id, 'delete_rejected', _run, total=total)
    return {'total': total, 'job': job}


def delete_rejected(user_id, bank_id, job=None) -> dict:
    """Delete the SOURCE files of every status='reject' image from disk, then
    drop their bank_image rows.

    This is the ONLY bank action that writes to the user's source folder. Where
    the files land is _trash_or_remove's decision (OS trash, else the app's own
    trash, else a permanent unlink) and rides back in 'mode' — the confirmation
    dialog says it BEFORE the click, via rejected_delete_preview().

    ⚠️ A bank does not own its folder. When another bank sits over the same tree,
    these files are ITS files too and it will find them gone; the preview names
    those banks so the warning can.

    Non-rejected images are never touched. Per-file failures (permission, a path
    that escapes the bank folder) are collected and reported; they never abort
    the batch. A row is dropped only when its file is gone afterwards (deleted,
    trashed, or already absent) — a file we failed to remove keeps its row so the
    user can see and retry it. Returns
    {'mode', 'deleted', 'trashed', 'already_absent', 'rows_removed', 'skipped',
    'cancelled'} where 'trashed' counts everything that stayed recoverable.

    ``job`` is the bank_jobs snapshot when this runs as a background pass (the
    normal path — see start_delete_rejected): progress is reported per file and
    Stop is honoured between files.
    """
    bank = _delete_rejected_guard(user_id, bank_id, check_busy=job is None)

    # (id, relpath) tuples, not ORM rows, and ONE realpath for the whole batch:
    # the loop commits as it goes, which expires live ORM objects and would make
    # every later row pay a re-SELECT (and abs_image_path a realpath) per file.
    rows = (db.session.query(BankImage.id, BankImage.relpath)
            .filter_by(bank_id=bank_id, status='reject').all())
    root = os.path.realpath(bank.source_path)
    out = {'mode': 'trash', 'deleted': 0, 'trashed': 0, 'already_absent': 0,
           'rows_removed': 0, 'skipped': [], 'cancelled': False}
    if job is not None:
        # The bar already prints "done / total"; a detail repeating it would just
        # say the same numbers twice. Spend the width on where the files GO.
        bank_jobs.progress(job, done=0, total=len(rows),
                           detail=_DELETE_DETAIL.get(_delete_mode(),
                                                     'removing files'))
    pending_ids, removed = [], 0
    modes_used = set()

    def _drop(ids):
        """Commit one chunk of row removals. Done as we go, not at the end: a
        Stop (or a crash) must not leave files gone from disk with their rows
        still claiming they are there."""
        for i0 in range(0, len(ids), _SQL_IN_CHUNK):
            BankImage.query.filter(
                BankImage.id.in_(ids[i0:i0 + _SQL_IN_CHUNK])
            ).delete(synchronize_session=False)
        db.session.commit()

    for i, (row_id, relpath) in enumerate(rows, 1):
        if job is not None and bank_jobs.cancelled(job):
            out['cancelled'] = True
            break
        path = _abs_under(root, relpath)
        if path is None:
            # relpath escapes the bank folder — refuse to touch it, keep the row.
            out['skipped'].append({'relpath': relpath, 'reason': 'unsafe_path'})
        elif not os.path.exists(path):
            out['already_absent'] += 1
            pending_ids.append(row_id)
        else:
            try:
                mode = _trash_or_remove(path)
            except OSError as e:
                out['skipped'].append({'relpath': relpath, 'reason': str(e)})
            else:
                modes_used.add(mode)
                if mode == 'delete':
                    out['deleted'] += 1
                else:
                    out['trashed'] += 1   # OS trash or app trash — recoverable
                pending_ids.append(row_id)
        if job is not None:
            bank_jobs.progress(job, done=i)
        if len(pending_ids) >= _SQL_IN_CHUNK:
            _drop(pending_ids)
            removed += len(pending_ids)
            pending_ids = []

    _drop(pending_ids)
    out['rows_removed'] = removed + len(pending_ids)
    # The pending ↩ offer points at rows this run just dropped — restoring them
    # would find nothing. Withdraw it rather than advertise a restore we cannot
    # perform (the files themselves went to a trash only the user can reach).
    bank_undo.clear(bank_id)
    # Report the WORST outcome that happened: one permanently removed file makes
    # the run 'delete', whatever the rest did. The UI wording follows this.
    for mode in ('delete', 'app_trash', 'trash'):
        if mode in modes_used:
            out['mode'] = mode
            break
    return out


# --- cooperative-cancel subprocess driver (shared by the face + score passes) --
# A bank inference pass runs for minutes over thousands of images. Its embeddings
# are cached incrementally, but a brutal proc.kill on Stop still throws away the
# in-flight slice AND leaves the UI mute. Instead we ask the child to stop CLEANLY:
# drop a sentinel file it polls between images so it flushes its cache and reports
# how much it kept; a watchdog timer hard-kills it only if it doesn't stop within
# the grace period. The child also writes a plain-text ``<cache>.count`` sidecar we
# read back here (the Flask venv has no numpy to open the .npz), so a stopped pass
# always shows an honest count — even in the rare hard-kill case.
_INFER_CANCEL_GRACE = 15.0   # seconds a cleanly-cancelled child gets before a kill
_CACHED_RE = re.compile(r'(\d+) image\(s\), (\d+) cached')


def _safe_kill(proc):
    try:
        proc.kill()
    except Exception:  # noqa: BLE001 — already gone is fine
        pass


def _read_cache_count(cache_path):
    """The count the child last flushed to ``<cache>.count``, or None."""
    try:
        with open(str(cache_path) + '.count', encoding='utf-8') as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def _stopped_detail(noun, data, cache_path, total, suffix=''):
    """The honest end-of-pass line when the user Stopped it. Prefers the child's
    own cancel counts, falls back to the flushed sidecar count, and never invents
    a number it can't back up. ``suffix`` states what reached the DATABASE, which
    is a different claim from what reached the cache and must not be implied."""
    n = data.get('cached')
    if n is None:
        n = _read_cache_count(cache_path)
    if n is None:
        return ('Stopped — progress saved to cache'
                f'{suffix}; relaunch to finish and cluster')
    n = int(n)
    remaining = data.get('remaining')
    remaining = int(remaining) if remaining is not None else max(0, int(total) - n)
    return (f'Stopped — {n} {noun} ({remaining} remaining)'
            f'{suffix}; relaunch to finish and cluster')


# --- rows that can vanish under a long pass ---------------------------------
# A pass reads its rows, then spends minutes to hours walking them, committing as
# it goes. `expire_on_commit` is on, so every row it has not reached yet becomes
# a lazy re-SELECT — and that re-SELECT can come back empty, because a bank's
# rows CAN disappear mid-pass: `delete_bank` cancels the live job cooperatively
# and then drops every row and the bank itself immediately, so the still-running
# thread keeps iterating over rows that are already gone (`delete_rejected` can
# do the same if the job registry has aged the pass out as stale).
#
# What SQLAlchemy does then is the trap: plain attribute access on an expired
# row whose database row is gone raises ObjectDeletedError, and so does a commit
# carrying a write staged on one. Either killed the WHOLE pass — one deleted
# image and thousands of analysed ones never got written. `Session.get(...,
# populate_existing=True)` is the one access that answers None instead of
# raising, so every long pass re-reads through the helper below immediately
# before it touches a row, and skips (and counts) what is no longer there.
def _live_image(image_id):
    """The bank row as the database has it RIGHT NOW, or None when it is gone.

    Always re-reads (``populate_existing``): a row the session still holds
    unexpired would otherwise be returned from the identity map, and the whole
    point here is to ask the database whether the image still exists."""
    if image_id is None:
        return None
    return db.session.get(BankImage, image_id, populate_existing=True)


def _detach_bank(bank):
    """Take the ImageBank row OUT of the session so a pass can keep reading it.

    Passes read the bank (its source folder) once per image, for hours. Left in
    the session, it is expired by each commit exactly like the images are — and
    it is deleted by the very same `delete_bank` that removes them, so it turns
    into an ObjectDeletedError of its own. Detaching a fully loaded instance
    keeps every column readable and immune to expiry; the passes doing this only
    ever READ the bank, so nothing is lost by leaving the session's copy behind.
    """
    if bank is not None:
        db.session.expunge(bank)
    return bank


def _release_db_before_inference():
    """End the session's transaction before an inference subprocess we may sit
    in for an HOUR (bank scoring on CPU is measured near that on a big bank).

    The pass reads its rows, hands a path list to a child process, waits, then
    writes the results back. Reading first is fine; keeping the SAME session
    transaction open across the wait is not. WAL (app/__init__.py) buys concurrent
    READERS, never concurrent writers: one stray write joining the transaction
    ahead of the child — a status stamp, a counter, a `flush()` inherited from the
    caller — takes the single write lock and holds it for the whole inference, so
    every other writer in the app dies on `database is locked` after the 5 s
    busy_timeout. That is the exact failure that abandoned two paid cloud runs on
    2026-07-26 (see cloud_training._COMMIT_RETRIES), for a five-second holder;
    this one would hold it for an hour.

    Committing here costs nothing on the nominal path (nothing is pending) and
    removes the trap for good. Callers must not hold ORM objects across it:
    `expire_on_commit` is on, so rows are re-fetched after the child returns."""
    db.session.commit()


def _drive_infer_subprocess(job, python, script, payload, cache_path,
                            progress_re, window):
    """Run an infer subprocess, streaming its stderr progress into ``job`` and
    honouring Stop cooperatively. Returns (data, stderr_tail, returncode) where
    ``data`` is the child's last JSON line (``cancelled: true`` when it stopped
    cleanly). On the first "N cached" line it sets a "resuming" hint, so relaunching
    over a partly-cached bank doesn't look like a full recompute."""
    import json
    import threading
    cancel_file = str(cache_path) + '.cancel'
    try:
        os.remove(cancel_file)   # never inherit a stale sentinel from a past run
    except OSError:
        pass
    hint = {'shown': False}
    with window:
        proc = subprocess.Popen(
            [python, script], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        killer = {'timer': None}

        def _cancel():
            # Ask for a clean stop (the child flushes + exits), and arm a watchdog
            # that hard-kills ONLY if it doesn't stop within the grace period.
            try:
                with open(cancel_file, 'w', encoding='utf-8') as f:
                    f.write('1')
            except OSError:
                pass
            t = threading.Timer(_INFER_CANCEL_GRACE, _safe_kill, args=(proc,))
            t.daemon = True
            t.start()
            killer['timer'] = t

        bank_jobs.set_cancel_hook(job, _cancel)
        stderr_tail = deque(maxlen=5)

        def _drain_stderr():
            for line in proc.stderr:
                line = line.strip()
                if line:
                    stderr_tail.append(line)
                m = progress_re.search(line)
                if m:
                    bank_jobs.progress(job, done=int(m.group(1)), total=int(m.group(2)))
                if not hint['shown']:
                    mc = _CACHED_RE.search(line)
                    if mc:
                        hint['shown'] = True
                        total, cached = int(mc.group(1)), int(mc.group(2))
                        if 0 < cached < total:
                            bank_jobs.progress(
                                job,
                                detail=f'resuming — {cached} of {total} already cached')

        t = threading.Thread(target=_drain_stderr, daemon=True)
        t.start()
        try:
            proc.stdin.write(payload)
            proc.stdin.close()
        except OSError:
            pass  # process died early — surfaced through the exit path below
        stdout = proc.stdout.read()
        proc.wait()
        t.join(timeout=5)
        if killer['timer']:
            killer['timer'].cancel()
    try:
        os.remove(cancel_file)
    except OSError:
        pass
    line = next((ln for ln in reversed(stdout.splitlines())
                 if ln.strip().startswith('{')), '')
    try:
        data = json.loads(line) if line else {}
    except json.JSONDecodeError:
        data = {}
    return data, stderr_tail, proc.returncode


# --- subject (face) pass ----------------------------------------------------
_EMBED_SCRIPT = str(cfg.BACKEND_DIR / 'infer' / 'face_embed_infer.py')
_PROGRESS_RE = re.compile(r'\[embed\] (\d+)/(\d+)')


def _resolve_face_device():
    """(device, use_gpu) for the face pass. 'cpu' is the safe default and never
    touches the GPU; GPU is used ONLY when the face interpreter truly exposes
    CUDA (onnxruntime-gpu installed) and the config allows it. Config
    face_scoring.device: 'auto' (default — GPU if available) | 'cpu' | 'cuda'.
    A 'cuda' request without CUDA available still degrades to CPU here, so the
    parent never opens the GPU-exclusive window for a pass that will run on CPU."""
    from .. import capabilities
    pref = str(cfg.get('face_scoring.device') or 'auto').lower()
    use_gpu = pref in ('auto', 'cuda') and capabilities.face_gpu_available()
    return ('cuda' if use_gpu else 'cpu'), use_gpu


def start_faces(app, user_id, bank_id, angles_only=False):
    """Launch the face embedding + person clustering pass over the bank's
    non-rejected images. Needs the face-scoring extra (Setup ▸ Quality tools).

    ``angles_only`` is the ⤢ BACKFILL, and it is a different job on purpose. The
    face pass has always computed a head yaw and thrown it away (it used it once
    to decide 'extreme_pose'), so every bank scanned before this release has
    faces with no angle and its cache cannot answer for them — the number is not
    in the .npz to be read back. Re-measuring them means re-running the detector,
    which on a big bank is hours: far too much to slip into a pass somebody
    started for something else. So it is its OWN action, offered on the ⤢ row
    with its own count and its own estimate, never automatic and never at boot.
    It touches ONLY `face_yaw`: person clusters are computed over the whole bank
    at once, and re-deriving them from a partial re-run would renumber a
    clustering the user has already worked with."""
    from .face_similarity import is_available
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    q = BankImage.query.filter_by(bank_id=bank_id)
    if angles_only:
        q = q.filter(BankImage.face_state.isnot(None), BankImage.face_yaw.is_(None))
        # BEFORE the install probe, and the order is the point: sending someone
        # to install a 300 MB extra so they can do work that does not exist is a
        # true sentence that answers the wrong question. (Same reasoning as the
        # framing pass, which checks occupancy before it probes Ollama.)
        if not q.count():
            raise ValueError('every face-scanned image already has an angle')
    else:
        q = q.filter(BankImage.status != 'reject')
    if not is_available():
        raise RuntimeError(
            'face scoring is not installed (Quality tools step in Setup)')
    # Images the user has DECLARED to be one person (their subfolder is asserted)
    # are not embedded at all — that skip is the whole point of the assertion, and
    # counting them in the total would promise work this pass will not do. The ⤢
    # angle lane is NOT affected: measuring where a head points is not identifying
    # who it is, and its pool is already restricted to rows a face pass measured.
    total = q.count() if angles_only \
        else max(q.count() - _asserted_image_count(bank_id), 0)
    return bank_jobs.start(app, bank_id, 'angles' if angles_only else 'faces',
                           _faces_job(bank_id, angles_only), total=total)


def _asserted_image_count(bank_id) -> int:
    return (BankImage.query.filter_by(bank_id=bank_id)
            .filter(BankImage.status != 'reject',
                    BankImage.face_cluster_origin == 'asserted').count())


def _faces_job(bank_id, angles_only=False):
    def run(job):
        import json as _json
        import sys
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        q = BankImage.query.filter_by(bank_id=bank_id)
        if angles_only:
            q = q.filter(BankImage.face_state.isnot(None),
                         BankImage.face_yaw.is_(None))
        else:
            # Asserted rows are EXCLUDED from the identity lane, not merely
            # preserved: the user already told us who is in them, so paying an
            # embedding to re-derive it is exactly the cost "Single person here"
            # exists to avoid (services/folder_person.py).
            q = q.filter(BankImage.status != 'reject',
                         or_(BankImage.face_cluster_origin.is_(None),
                             BankImage.face_cluster_origin != 'asserted'))
        rows = q.order_by(BankImage.id.asc()).all()
        by_path = {}
        for r in rows:
            p = abs_image_path(bank, r)
            if _is_safe_bank_source(p, label='bank face pass'):
                by_path[p] = r.id
        paths = list(by_path)
        skipped_asserted = 0 if angles_only else _asserted_image_count(bank_id)
        bank_jobs.progress(job, done=0, total=len(paths),
                           detail='measuring angles' if angles_only else 'face pass')
        if not paths:
            return
        _bank_dir(bank_id).mkdir(parents=True, exist_ok=True)
        th = thresholds()
        # Device: 'cpu' (default, never touches the GPU/ComfyUI) or 'cuda'.
        # 'auto' = GPU when the face interpreter actually exposes CUDA
        # (onnxruntime-gpu installed), else CPU. The GPU path is used ONLY when
        # CUDA is truly available AND must run inside the GPU-exclusive window so
        # it never competes with a training / scoring pass; a CPU pass stays out
        # of the window (it can run alongside GPU work).
        from ..gpu_window import gpu_exclusive_vision_window
        from contextlib import nullcontext
        device, use_gpu = _resolve_face_device()
        cache_path = _face_cache_path(bank_id)
        payload = _json.dumps({
            'images': paths,
            'models_root': cfg.get('face_scoring.models_root') or None,
            'cache': str(cache_path),
            'cancel_file': str(cache_path) + '.cancel',
            'threshold': th['face_threshold'],
            'device': device,
            # Only the ⤢ backfill overrides the cache. A normal pass must stay
            # exactly as cheap as it was: it writes the yaw for every image it
            # actually looks at, and leaves the already-cached ones alone rather
            # than silently turning a resume into hours of re-detection.
            'require_yaw': bool(angles_only),
        })
        python = cfg.get('face_scoring.python') or sys.executable
        window = gpu_exclusive_vision_window(flag_ttl=1800) if use_gpu else nullcontext()
        _release_db_before_inference()
        data, stderr_tail, returncode = _drive_infer_subprocess(
            job, python, _EMBED_SCRIPT, payload, cache_path, _PROGRESS_RE, window)
        # Stopped by the user — say exactly what's kept, never a mute ✗ (the cached
        # embeddings are safe; relaunching skips them and only finishes the rest).
        if data.get('cancelled') or (bank_jobs.cancelled(job) and not data.get('ok')):
            bank_jobs.progress(job, detail=_stopped_detail(
                'face embeddings cached', data, cache_path, len(paths)))
            return
        if not data.get('ok'):
            tail = data.get('error') or (stderr_tail[-1] if stderr_tail else '')
            raise RuntimeError(tail or f'face pass produced no output '
                                       f'(rc={returncode})')
        results = data.get('results') or {}
        clusters = data.get('clusters') or {}
        # The child numbers its clusters 1..n, unaware of the asserted groups that
        # already own ids in this bank. Push them above the highest asserted id so
        # a computed cluster can never land ON a folder the user declared — the two
        # kinds share one id space (that is what lets them be merged later), and
        # sharing it means allocating in it.
        from . import folder_person
        offset = folder_person.asserted_offset(bank_id)
        done = vanished = 0
        for p, image_id in by_path.items():
            row = _live_image(image_id)
            if row is None:      # deleted while the pass ran — see _live_image
                vanished += 1
                continue
            res = results.get(p) or {}
            # A yaw is written whenever the child measured one. It is never
            # written back as NULL over a value we already have: the ⤢ backfill
            # re-runs on rows that HAVE no angle, and a face that fails detection
            # this time must leave the row "not measured", not blank a number
            # that was right.
            yaw = res.get('yaw')
            if yaw is not None:
                row.face_yaw = float(yaw)
            if not angles_only:
                row.face_state = res.get('state')
                row.face_det = res.get('det')
                cid = clusters.get(p)
                row.face_cluster = None if cid is None else int(cid) + offset
            done += 1
            if done % 200 == 0:
                db.session.commit()
        db.session.commit()
        if vanished:
            logger.info('bank face pass: %s image(s) were deleted while it ran', vanished)
        sizes = {}
        for cid in clusters.values():
            sizes[cid] = sizes.get(cid, 0) + 1
        multi = sum(1 for n in sizes.values() if n >= 2)
        detail = (f'done — {sum(1 for r in results.values() if r.get("yaw") is not None)}'
                  ' angle(s) measured' if angles_only
                  else f'done — {multi} person cluster(s) of 2+ images')
        if skipped_asserted:
            # Never mute: an image the pass did not look at must be reported as
            # such, or "0 clusters" would read as "no one in this bank".
            detail += (f', {skipped_asserted} image(s) skipped '
                       f'(subfolder asserted as one person)')
        # The embeddings are cached NOW, so asking "which folders look like one
        # person?" costs nothing here and would cost a pass of its own later.
        # It only ever produces a suggestion the user confirms (folder_person).
        if not angles_only and not bank_jobs.cancelled(job):
            detail += folder_person.probe_after_faces(job, bank_id)
        if vanished:
            detail += f', {vanished} skipped (deleted while the pass ran)'
        bank_jobs.progress(job, detail=detail)
    return run


# --- scoring pass (aesthetic · NSFW · style) --------------------------------
_SCORE_SCRIPT = str(cfg.BACKEND_DIR / 'infer' / 'bank_score_infer.py')
_SCORE_PROGRESS_RE = re.compile(r'\[score\] (\d+)/(\d+)')


def _gpu_busy_reason() -> str | None:
    """A human reason the GPU is unavailable right now, or None. Same system
    flags training and the vision window use, so a bank GPU pass never races a
    training run or a captioning pass (the 'never concurrent with a training'
    guarantee). Checked up-front for an immediate 503 rather than a doomed 202."""
    from ..job_queue import queue_manager
    if queue_manager._get_system_state('training_in_progress'):
        return 'training is running on the GPU — try again once it finishes'
    if queue_manager._get_system_state('vision_in_progress'):
        return 'a vision/GPU pass is already running — try again in a moment'
    return None


def _resolve_score_device() -> tuple:
    """(device, use_gpu) for the scoring pass — what the CHILD will actually do.

    bank_score_infer.py picks `cuda if torch.cuda.is_available() else cpu` on its
    own, so the parent asks the same interpreter the same question. It matters
    beyond a label: use_gpu decides whether we take the GPU-exclusive window,
    which unloads ComfyUI and blocks any training start for the whole pass. The
    extra ships CPU-only torch, so the honest answer is usually 'cpu' — and an
    hour of CPU work must not hold a GPU it never touches."""
    from ..capabilities import bank_scoring_gpu_available
    use_gpu = bank_scoring_gpu_available()
    return ('cuda' if use_gpu else 'cpu'), use_gpu


# CLIP ViT-L/14 measured at ~336 ms/image on CPU against ~15 ms on a recent
# card. Used only to warn, never to refuse — a slow pass is still a pass.
SCORE_CPU_MS_PER_IMAGE = 336


def score_device_info(bank_id=None) -> dict:
    """What ✨ Score will run on, and — when that is the CPU — how long the bank
    would take and whether this machine even has a card to switch to.

    The pass is not slow by accident: the scoring extra installs CPU-only torch
    on purpose (Setup builds it a small venv rather than pushing a ~2.5 GB CUDA
    download on people with no GPU). That is a defensible default, but it has to
    be VISIBLE — an unexplained hour looks like a hang, and the user cannot fix
    what nobody told them about."""
    from ..capabilities import gpu_vram_gb
    device, use_gpu = _resolve_score_device()
    out = {'device': device, 'gpu': use_gpu, 'gpu_present': False,
           'eta_minutes': None}
    if use_gpu:
        return out
    out['gpu_present'] = gpu_vram_gb() is not None
    if bank_id is not None:
        pending = (BankImage.query.filter_by(bank_id=bank_id)
                   .filter(BankImage.status != 'reject')
                   .filter(BankImage.aesthetic_score.is_(None)).count())
        # Rounded UP to a whole minute while there is anything left: "0 minutes"
        # for work that is about to start reads as "instant" and is a lie.
        out['eta_minutes'] = (max(1, round(pending * SCORE_CPU_MS_PER_IMAGE / 60000))
                              if pending else None)
    return out


def start_score(app, user_id, bank_id, rescore=False):
    """Launch the scoring pass (LAION aesthetic + NSFW + style clustering) over
    the bank's non-rejected images. Needs the bank-scoring extra (Setup ▸ Quality
    tools). Serialized against training/vision ONLY when it will really run on
    the GPU: refusing a CPU pass because 'the GPU is busy' would block an hour of
    work that never wanted the card.

    The pool is ALWAYS the whole bank, and deliberately so — "already scored" is
    not a reason to leave an image out. The style ids are a partition computed
    from every embedding at once, so a pass handed only the unscored rows would
    number a sub-population from 1 and land those ids on top of unrelated groups
    already in the database; the semantic-dedup pass, which blocks by
    style_cluster, would then stop comparing across the seam and miss crops
    without saying anything. Skipping work is the CHILD's job and it already does
    it: a cached, unchanged image is never embedded again, and a fully cached
    bank does not even load CLIP.

    ``rescore=True`` is the explicit "throw the cache away and recompute" lane
    (same shape as the quality pass's ``rescan``) — for a new model, or scores
    you no longer trust. The plain ✨ Score button keeps meaning exactly what it
    always meant: a complete pass that resumes."""
    from ..capabilities import probe_bank_scoring
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    if not probe_bank_scoring().get('ok'):
        raise RuntimeError('bank scoring is not installed '
                           '(Quality tools step in Setup)')
    _device, use_gpu = _resolve_score_device()
    reason = _gpu_busy_reason() if use_gpu else None
    if reason:
        raise RuntimeError(reason)
    total = (BankImage.query.filter_by(bank_id=bank_id)
             .filter(BankImage.status != 'reject').count())
    return bank_jobs.start(app, bank_id, 'score', _score_job(bank_id, rescore),
                           total=total)


# Rows written between two commits in the score write-back. Small enough that a
# Stop (or a crash) never costs more than a few seconds of re-run, large enough
# that we are not committing per row — same trade-off as the duplicate regrouping
# budget above, and for the same reason: long single transactions hold SQLite's
# one write lock and everything else in the app dies on "database is locked".
_SCORE_COMMIT_EVERY = 200


def _apply_score_results(job, by_path, results, interruptible):
    """Write the PER-IMAGE scores (aesthetic, nsfw) back. Returns
    (written, scored, vanished, stopped).

    Two rules earn their place here:

    * a head's value is written only when the child produced one. It used to be
      assigned unconditionally from ``res.get(...)``, so a run where the
      aesthetic weights failed to download did not merely skip that column — it
      wrote NULL over every aesthetic score the bank already had. Same rule as
      the face pass and its yaw: never blank a good value because this run had
      nothing to say.
    * ``interruptible`` is False on the salvage path (the child was stopped and
      handed us what it had computed). There, the job flag is ALREADY set, so
      honouring it would mean discarding the exact GPU work we came to save.

    Whatever it wrote is committed either way: the job registry is in-memory, so
    a pass that only wrote at the very end lost everything to a restart."""
    written = scored = vanished = 0
    stopped = False
    for p, image_id in by_path.items():
        res = results.get(p)
        if res is None:
            continue          # never reached by this run — leave the row alone
        row = _live_image(image_id)
        if row is None:      # deleted while the pass ran — see _live_image
            vanished += 1
            continue
        if 'aesthetic' in res:
            row.aesthetic_score = res['aesthetic']
        if 'nsfw' in res:
            row.nsfw_score = res['nsfw']
        # Counted HERE, on the row we actually wrote — not from the child's
        # report. The child scores a PATH; this loop is the only place that
        # knows whether the image behind it still exists. Counting the report
        # made the pass announce "scored 3 image(s), 1 skipped" over a bank of
        # three, which is two claims that cannot both be true.
        if res.get('state') == 'ok':
            scored += 1
        written += 1
        if written % _SCORE_COMMIT_EVERY == 0:
            db.session.commit()
            # Stop is honoured HERE and not per row, on purpose: the rows in
            # hand are already computed, so abandoning them buys nothing except
            # a relaunch. A bank smaller than one commit therefore always
            # finishes rather than reporting "stopped after 1 image".
            if interruptible and bank_jobs.cancelled(job):
                stopped = True
                break
    db.session.commit()
    return written, scored, vanished, stopped


def _write_style_clusters(by_path, clusters):
    """Write the style partition — all of it or none of it.

    ``style_cluster`` is not a per-image measurement, it is one numbering of the
    whole bank, recomputed (and renumbered) every pass. Half of a new partition
    next to half of the old one is not "partial progress", it is two different
    meanings sharing an id space: the 🎨 chip would mix unrelated groups and the
    semantic-dedup pass, which only compares inside a cluster, would silently
    stop looking across the seam. So this is deliberately NOT interruptible, and
    the child hands us ``None`` (not a half-clustering) whenever it was stopped.

    Grouped bulk UPDATEs rather than a write per row: same number of rows, a few
    hundred statements instead of tens of thousands."""
    by_cid: dict = {}
    for p, image_id in by_path.items():
        by_cid.setdefault(clusters.get(p), []).append(image_id)
    since_commit = 0
    for cid, ids in by_cid.items():
        for i0 in range(0, len(ids), _SQL_IN_CHUNK):
            chunk = ids[i0:i0 + _SQL_IN_CHUNK]
            BankImage.query.filter(BankImage.id.in_(chunk)).update(
                {'style_cluster': cid}, synchronize_session=False)
            since_commit += len(chunk)
            if since_commit >= _DUP_WRITE_ROWS:
                db.session.commit()
                # Same yield the duplicate regrouping needs: without it the next
                # batch re-takes SQLite's single write lock in the microsecond
                # after the commit, inside another writer's busy-handler sleep,
                # and that writer dies on "database is locked".
                time.sleep(_DUP_WRITE_YIELD)
                since_commit = 0
    db.session.commit()


def _score_job(bank_id, rescore=False):
    def run(job):
        import json as _json
        import sys
        from contextlib import nullcontext

        from ..gpu_window import gpu_exclusive_vision_window
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        rows = (BankImage.query.filter_by(bank_id=bank_id)
                .filter(BankImage.status != 'reject')
                .order_by(BankImage.id.asc()).all())
        by_path = {}
        for r in rows:
            p = abs_image_path(bank, r)
            if _is_safe_bank_source(p, label='bank scoring pass'):
                by_path[p] = r.id
        paths = list(by_path)
        device, use_gpu = _resolve_score_device()
        # Say WHICH device, every time. On CPU this pass is ~20× slower (CLIP
        # ViT-L is the whole cost), and a progress bar crawling for an hour with
        # no explanation reads as a hang.
        bank_jobs.progress(job, done=0, total=len(paths),
                           detail=f'scoring pass ({device.upper()})')
        if not paths:
            # Never leave the label of a pass that did not run: the one-click
            # tunnel falls back to a count read from the DATABASE when a step
            # says nothing, so a mute return here reported "scored N image(s)"
            # over a run that scored none of them.
            bank_jobs.progress(job, detail=(
                'done — nothing to score: every image in this bank is either '
                'rejected or unreadable'))
            return
        _bank_dir(bank_id).mkdir(parents=True, exist_ok=True)
        th = thresholds()
        cache_path = _score_cache_path(bank_id)
        payload = _json.dumps({
            'images': paths,
            'models_root': cfg.get('bank_scoring.models_root') or None,
            'cache': str(cache_path),
            'cancel_file': str(cache_path) + '.cancel',
            'style_threshold': th['style_threshold'],
            'rescore': bool(rescore),
        })
        python = cfg.get('bank_scoring.python') or sys.executable
        # The GPU-exclusive window frees ComfyUI's VRAM and blocks any training
        # start for the whole pass — so it is taken ONLY when the child really
        # runs on the card, exactly like the face pass. Holding it through an
        # hour of CPU inference was the worst of both worlds: the GPU idle and
        # unusable, the work slow anyway.
        window = (gpu_exclusive_vision_window(flag_ttl=1800) if use_gpu
                  else nullcontext())
        _release_db_before_inference()
        data, stderr_tail, returncode = _drive_infer_subprocess(
            job, python, _SCORE_SCRIPT, payload, cache_path, _SCORE_PROGRESS_RE,
            window)
        # Stopped by the user. The scores the child DID compute are paid GPU work
        # and land in the database here — the pass used to return empty-handed, so
        # an hour of inference reached the disk cache and never reached a single
        # row. The style partition is the one thing that cannot come back with it:
        # it is global by construction and takes minutes (measured 181 s over
        # 23 000 images), which is why the child hands us None for it instead of
        # half of one. Relaunching finishes from the cache and clusters then.
        if data.get('cancelled') or (bank_jobs.cancelled(job) and not data.get('ok')):
            saved = 0
            if data.get('results'):
                _, saved, _v, _s = _apply_score_results(
                    job, by_path, data['results'], interruptible=False)
            suffix = (f'; {saved} score(s) saved, style groups need a full pass'
                      if saved else '')
            bank_jobs.progress(job, detail=_stopped_detail(
                'images scored', data, cache_path, len(paths), suffix=suffix))
            return
        if not data.get('ok'):
            tail = data.get('error') or (stderr_tail[-1] if stderr_tail else '')
            raise RuntimeError(tail or f'scoring pass produced no output '
                                       f'(rc={returncode})')
        results = data.get('results') or {}
        clusters = data.get('clusters') or {}
        computed = data.get('computed')
        reused = data.get('reused')
        written, scored, vanished, stopped = _apply_score_results(
            job, by_path, results, interruptible=True)
        if vanished:
            logger.info('bank scoring pass: %s image(s) were deleted while it ran',
                        vanished)
        if stopped:
            # Stopped while saving. What landed is committed; the partition is
            # left alone precisely because only part of the bank got its scores.
            bank_jobs.progress(job, detail=(
                f'Stopped while saving — {written} image(s) written '
                # Rows that vanished under the pass are neither written nor
                # left: counting them here would inflate the only number the
                # user has to judge how much is still pending.
                f'({len(paths) - written - vanished} left); nothing was '
                'recomputed, relaunch finishes from the cache'))
            return
        _write_style_clusters(by_path, clusters)
        sizes = {}
        for cid in clusters.values():
            sizes[cid] = sizes.get(cid, 0) + 1
        multi = sum(1 for n in sizes.values() if n >= 2)
        # The child's own report — used ONLY to name a head that produced nothing
        # (below). It counts PATHS it was handed, so it is the wrong thing to
        # report as "scored": see the counter in the write-back loop.
        ok = [r for r in results.values() if r.get('state') == 'ok']
        # Name any head that produced nothing, so a degraded pass says so out loud
        # (graceful degradation must be visible, never a silent gap).
        missing = []
        if ok and not any('aesthetic' in r for r in ok):
            missing.append('aesthetic')
        if ok and not any('nsfw' in r for r in ok):
            missing.append('NSFW')
        detail = (f'done — scored {scored} image(s), '
                  f'{multi} style group(s) of 2+')
        # Where the work went. Both numbers count images HANDED to the pass, so
        # they add up to the pool and never stand in for `scored`, which counts
        # rows actually written. Saying "scored N" over a bank that recomputed
        # nothing would be the auto-reject mistake again: a true-looking total
        # covering an action that did not happen.
        if reused:
            detail += (f' · {computed} newly computed, '
                       f'{reused} reused from cache')
        if vanished:
            detail += f', {vanished} skipped (deleted while the pass ran)'
        if missing:
            detail += f' ({" + ".join(missing)} head unavailable)'
        if not bank_jobs.cancelled(job):
            detail += _chain_medium_after_score(job, bank_id)
        bank_jobs.progress(job, detail=detail)
    return run


def _chain_medium_after_score(job, bank_id) -> str:
    """Run 🎨 Medium immediately after ✨ Score, inside the SAME job.

    Why automatically: Medium computes NO image inference of its own — it reads
    the embeddings Score just cached and multiplies them by a handful of text
    vectors (0.16 s for 23 000 images, no GPU). Leaving it behind a second button
    meant the bank sat there with the data for the answer and not the answer,
    and most users never learned the pass existed. Chaining it here is the only
    moment it is genuinely free: the embeddings are on disk and warm.

    The manual 🎨 Medium button stays exactly as it was — it is how you re-run
    the pass alone, and how ``rescan`` re-classifies rows that already have a
    verdict, which this chain deliberately never does.

    NEVER raises: Score has already succeeded by the time this runs, and a
    classification that could not run must not turn a finished pass red. It
    returns a suffix for the pass's detail line, so what happened is visible
    either way — including "skipped", with the reason."""
    reason = medium_prereq(bank_id)
    if reason:
        # The common one is "the text encoder is not installed" — a Setup step,
        # not a failure of this bank. Said once, in passing, never as an alarm.
        return f' · 🎨 Medium skipped ({reason})'
    before = (BankImage.query.filter_by(bank_id=bank_id)
              .filter(BankImage.medium.isnot(None)).count())
    try:
        _medium_job(bank_id, False)(job)
    except Exception as e:  # noqa: BLE001 — see the docstring
        logger.warning('bank %s: chained medium pass failed', bank_id,
                       exc_info=True)
        return (f' · 🎨 Medium could not run ({type(e).__name__}) — '
                'the 🎨 Medium button re-runs it')
    after = (BankImage.query.filter_by(bank_id=bank_id)
             .filter(BankImage.medium.isnot(None)).count())
    return f' · 🎨 Medium: {after - before} classified'


# --- watermark pass (reuses the dataset Qwen3-VL overlaid-mark detector) -----
def _watermark_scan_query(bank_id, rescan):
    """The rows the detection pass should look at.

    Not a rescan = "finish the job": rows never scanned, PLUS rows flagged
    'detected' with no bbox. The latter exist because the pass used to parse the
    box and keep only the boolean — they would be invisible to both cleaning
    levels forever, so a plain re-run adopts them instead of asking the user to
    guess. 'dismissed' rows are never re-examined (the user already ruled), even
    on a rescan — same anti-frustration rule as the dataset detector."""
    q = (BankImage.query.filter_by(bank_id=bank_id)
         .filter(BankImage.status != 'reject')
         .filter(or_(BankImage.watermark_state.is_(None),
                     BankImage.watermark_state != 'dismissed')))
    if not rescan:
        q = q.filter(or_(BankImage.watermark_state.is_(None),
                         and_(BankImage.watermark_state == 'detected',
                              BankImage.watermark_bbox.is_(None))))
    return q


def start_watermark(app, user_id, bank_id, rescan=False):
    """Launch the overlaid-watermark scan over the bank's non-rejected images.

    TWO routes, and which one runs is decided here, once:

      * the dedicated DETECTOR extra when it is installed — a SigLIP2 classifier
        that answers the binary question in ~0.14 s per image against the vision
        model's ~1.7 s, plus a second model that locates the mark. It does not
        need Ollama at all, so a machine with no vision model can still scan.
      * otherwise the vision model, exactly as before. That is the fail-open
        contract: the extra can only ever ADD a faster route, never remove the
        one that has always worked.

    Serialized against training/vision (503 when the GPU is held)."""
    from ..capabilities import probe_ollama_model
    from . import watermark_detector
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    # Occupancy BEFORE the model probe, and the order is the whole point: a bank
    # that is already busy is busy whether or not Ollama answers. Probing first
    # made a busy bank report "the vision model is not available" whenever the
    # model happened to be unreachable -- the wrong reason, sending the user to
    # fix an unrelated thing while the real answer was "wait, a pass is running".
    # It also made the refusal depend on an EXTERNAL SERVICE, which is why CI
    # (no Ollama) failed a release on it while two agents read it as a flake.
    if bank_jobs.running(bank_id):
        raise bank_jobs.BankJobBusy((bank_jobs.get(bank_id) or {}).get('kind') or 'background')
    # WHICH route, resolved once, from the setting both surfaces read. 'auto' —
    # the default — resolves exactly the way this line used to read the probe
    # directly, so an untouched install behaves identically. A pinned 'detector'
    # with no extra installed does not refuse: it runs the vision route and
    # carries the reason into the job's own progress line (`note`), because a
    # silent fallback is how a user changes a detector and sees nothing change.
    resolution = watermark_detector.resolve_backend()
    use_detector = resolution['backend'] == 'detector'
    if not use_detector and not probe_ollama_model().get('ok'):
        raise RuntimeError('the vision model is not available '
                           '(Settings ▸ Local tools)')
    reason = _gpu_busy_reason()
    if reason:
        raise RuntimeError(reason)
    return bank_jobs.start(app, bank_id, 'watermark',
                           _watermark_job(bank_id, rescan, use_detector=use_detector,
                                          note=resolution['detail'] if resolution['fell_back'] else ''),
                           total=_watermark_scan_query(bank_id, rescan).count())


def _watermark_job(bank_id, rescan, use_detector=False, note=''):
    if use_detector:
        return _watermark_detector_job(bank_id, rescan)

    def run(job):
        import json as _json
        from .face_dataset_service import WATERMARK_BBOX_PROMPT, _parse_watermark_bbox
        from .vision_ollama import describe_image_ollama, unload_vision_model
        from .vision_pool import map_vision
        from ..gpu_window import gpu_exclusive_vision_window
        bank = _detach_bank(db.session.get(ImageBank, bank_id))
        if not bank:
            return
        rows = _watermark_scan_query(bank_id, rescan).order_by(BankImage.id.asc()).all()
        # `note` is set only when the user PINNED the detector and it could not
        # run. Said at the start (so it is visible while the pass runs) and again
        # in the final sentence (so it survives the pass).
        bank_jobs.progress(job, done=0, total=len(rows),
                           detail=(f'watermark scan — ℹ {note}' if note else 'watermark scan'))
        if not rows:
            return
        row_ids = [r.id for r in rows]
        detected = clean = errors = unanswered = vanished = 0

        def prepared():
            """Yielded on the JOB's thread, one image per free slot in the pool.
            Everything that reads the database or has a side effect lives here,
            so it stays off the workers, keeps its original order, and is only
            paid for by images the pass actually reaches (which matters: the
            discard below is destructive)."""
            nonlocal vanished
            for rid in row_ids:
                row = _live_image(rid)
                if row is None:      # deleted since the pass started — see _live_image
                    logger.info('bank watermark scan: image %s was deleted mid-pass, '
                                'skipping it', rid)
                    vanished += 1
                    bank_jobs.bump(job)
                    continue
                # Always detect on the SOURCE pixels: a re-scan of an already
                # cleaned image drops its cleaned version first (otherwise we
                # would be asking "is there a watermark?" about our own edit).
                if row.watermark_clean_method:
                    _discard_clean_blob(bank_id, row)
                yield rid, abs_image_path(bank, row)

        def ask(item):
            """WORKER thread: read the file, ask Ollama. Touches no session — the
            path was resolved above, on the owning thread. Returns None (not '')
            for a file that is gone, so the caller can tell "nothing to analyse"
            from "the model answered nothing"."""
            _rid, path = item
            if not path or not os.path.isfile(path):
                return None
            return describe_image_ollama(
                _read_safe_bank_source_bytes(path, label='bank watermark scan'),
                WATERMARK_BBOX_PROMPT, num_predict=400,
                prefer_json=True, fmt='json', keep_alive='5m')

        with gpu_exclusive_vision_window(flag_ttl=1800):
            try:
                # The calls overlap (see vision_pool); the loop body — every
                # database write below — still runs here, on this one thread.
                for (rid, _path), raw, error in map_vision(
                        prepared(), ask,
                        should_cancel=lambda: bank_jobs.cancelled(job)):
                    # Re-read: the answer we are about to store took ~1.7 s to
                    # arrive, and the image can have been deleted in that time.
                    row = _live_image(rid)
                    if row is None:
                        logger.info('bank watermark scan: image %s was deleted while '
                                    'it was being analysed, skipping it', rid)
                        vanished += 1
                        bank_jobs.bump(job)
                        continue
                    if error is not None:  # one bad file never sinks the pass
                        row.watermark_state = 'error'
                        errors += 1
                    elif raw is None:      # file gone: leave the row as it was
                        pass
                    # Empty output = Ollama unreachable, NOT "clean": leave the
                    # state untouched so a retry can finish it (same reasoning as
                    # the dataset detector), never falsely mark everything clean.
                    elif not raw.strip():
                        # COUNTED, not merely skipped: a pass where every image
                        # came back empty reported "done — 0 with a watermark,
                        # 0 clean", which reads as "looked at them all, found
                        # nothing" when in truth nothing could be looked at. The
                        # rows stay unscanned on purpose — the report must say so.
                        unanswered += 1
                    else:
                        bbox = _parse_watermark_bbox(raw)
                        # Stamp WHICH detector ruled, on every row this pass
                        # touches. A bank scanned over weeks can hold verdicts
                        # from both routes, and they disagree at the margins —
                        # so "why is this one flagged?" has to stay answerable
                        # per image rather than per bank.
                        row.watermark_source = 'vision'
                        row.watermark_score = None      # this route has no score
                        if bbox:
                            row.watermark_state = 'detected'
                            # Keep the box — the crop/inpaint levels route on it.
                            row.watermark_bbox = _json.dumps([round(v, 4) for v in bbox])
                            detected += 1
                        else:
                            row.watermark_state = 'none'
                            row.watermark_bbox = None
                            clean += 1
                    bank_jobs.bump(job)
                    # Never sit in an Ollama call with a transaction open. This
                    # loop WRITES — the 'error' stamp above, the states, and the
                    # destructive discard in prepared() — and the next iteration
                    # waits on a call measured at ~1.7 s, tens of thousands of
                    # times over a big bank. The rhythm used to be "commit every
                    # 25 PARSED answers", which is not a rhythm at all: a pass
                    # whose files erroured, or whose model answered nothing,
                    # never incremented that counter, so the single write lock
                    # was held across an UNBOUNDED number of calls and every
                    # other writer in the app died on `database is locked` past
                    # the 5 s busy_timeout (the failure that abandoned two paid
                    # cloud runs on 2026-07-26 — see
                    # _release_db_before_inference). Committing once per image
                    # bounds the hold by the work traversed whatever the answers
                    # look like, and costs a millisecond against a 1.7 s call.
                    db.session.commit()
            finally:
                db.session.commit()
                unload_vision_model()  # hand the VRAM back to ComfyUI
        if bank_jobs.cancelled(job):
            bank_jobs.progress(job, detail=f'cancelled — {detected} with a watermark '
                                           f'so far' + (f' · ℹ {note}' if note else ''))
            return
        detail = f'done — {detected} with a watermark, {clean} clean'
        if note:
            detail += f' · ℹ {note}'
        if vanished:
            detail += f', {vanished} skipped (deleted while the pass ran)'
        if unanswered:
            detail += (f', {unanswered} not analysed (the vision model returned '
                       'nothing — check Ollama in Settings, then run it again)')
        if errors:
            detail += f', {errors} unreadable'
        bank_jobs.progress(job, detail=detail)
    return run


def _watermark_detector_job(bank_id, rescan):
    """The same pass, run by the dedicated detector extra instead of the vision
    model. Deliberately the same SHAPE as the vision job above, because the two
    have to be interchangeable: same resume semantics, same per-image commit,
    same survives-a-deletion discipline, same honest final sentence.

    The one structural difference is where the work happens. The vision route
    overlaps network calls through a thread pool; here a single child process
    holds both models (loading them costs ~10 s, so it must be paid once) and
    streams one verdict per image back. Cancellation therefore travels as a
    sentinel FILE the child polls between images — killing a process that holds
    two loaded models mid-forward is how a stop turns into a corrupted half-write.
    """
    def run(job):
        import contextlib
        import json as _json
        import tempfile
        from . import watermark_detector
        from ..gpu_window import gpu_exclusive_vision_window
        bank = _detach_bank(db.session.get(ImageBank, bank_id))
        if not bank:
            return
        rows = _watermark_scan_query(bank_id, rescan).order_by(BankImage.id.asc()).all()
        bank_jobs.progress(job, done=0, total=len(rows), detail='watermark scan')
        if not rows:
            return
        detected = clean = errors = vanished = 0
        threshold = watermark_detector.threshold()

        # Paths are resolved HERE, on the owning thread, exactly like the vision
        # route: everything that reads the database or has a side effect (the
        # destructive discard below included) stays off the worker.
        planned = []
        for row_id in [r.id for r in rows]:
            row = _live_image(row_id)
            if row is None:      # deleted since the pass started — see _live_image
                logger.info('bank watermark scan: image %s was deleted mid-pass, '
                            'skipping it', row_id)
                vanished += 1
                bank_jobs.bump(job)
                continue
            # Always detect on the SOURCE pixels: a re-scan of an already cleaned
            # image drops its cleaned version first, or we would be asking "is
            # there a watermark?" about our own edit.
            if row.watermark_clean_method:
                _discard_clean_blob(bank_id, row)
            path = abs_image_path(bank, row)
            if not path:
                # No resolvable file. Counted and bumped rather than quietly
                # dropped: a pass that says "done — 12 with a watermark" over a
                # bank of 20 while 8 were never looked at is the kind of silent
                # arithmetic this pass has already been fixed for once.
                vanished += 1
                bank_jobs.bump(job)
                continue
            planned.append((row_id, path))
        db.session.commit()
        if not planned:
            bank_jobs.progress(
                job, detail='done — nothing left to scan'
                + (f' ({vanished} skipped: gone while the pass ran)' if vanished else ''))
            return
        by_path = {}
        for row_id, path in planned:
            by_path.setdefault(path, []).append(row_id)

        cancel_dir = tempfile.mkdtemp(prefix='lds-wmdet-')
        cancel_file = os.path.join(cancel_dir, 'cancel')

        def should_cancel():
            if not bank_jobs.cancelled(job):
                return False
            try:                            # the child polls for this file
                open(cancel_file, 'wb').close()
            except OSError:
                pass
            return True

        # The GPU window is taken only when this extra would actually USE the
        # card. The stock install is CPU-only torch, and a pass that never
        # touches the GPU must never unload ComfyUI or block a training start —
        # the exact rule the scoring pass already follows.
        from ..capabilities import watermark_detect_gpu_available
        on_gpu = watermark_detect_gpu_available()
        window = (gpu_exclusive_vision_window(flag_ttl=1800) if on_gpu
                  else contextlib.nullcontext())
        located = 0
        try:
            with window:
                for path, state, score, regions, error in watermark_detector.scan(
                        [p for _rid, p in planned],
                        should_cancel=should_cancel, cancel_file=cancel_file):
                    # Match on the path the child echoed, popping it so a bank
                    # that holds the same file twice gets one verdict each
                    # rather than both landing on the first row.
                    waiting = by_path.get(path) or []
                    row_id = waiting.pop(0) if waiting else None
                    row = _live_image(row_id) if row_id is not None else None
                    if row is None:
                        logger.info('bank watermark scan: image %s was deleted while '
                                    'it was being analysed, skipping it', row_id)
                        vanished += 1
                        bank_jobs.bump(job)
                        continue
                    row.watermark_source = 'detector'
                    row.watermark_score = (round(float(score), 4)
                                           if score is not None else None)
                    if state == 'error':
                        # One bad file never sinks the pass, same as the vision route.
                        row.watermark_state = 'error'
                        errors += 1
                    elif state == 'detected':
                        row.watermark_state = 'detected'
                        # Only ONE box is persisted: the child's FIRST, which it
                        # orders most-peripheral-first precisely because this
                        # line only takes one (see _merge_boxes — "biggest" put
                        # a crop on the subject). watermark_bbox holds
                        # one rectangle (it is what both cleaning levels route
                        # on), and the multi-zone column next to it means
                        # something else entirely — it is the HAND-DRAWN
                        # override, and writing machine output there would make
                        # every flagged image look hand-corrected and silently
                        # exclude it from ✂ Auto-crop. Losing the smaller boxes
                        # is the honest cost; the mask editor still lets the user
                        # add them back.
                        if regions:
                            row.watermark_bbox = _json.dumps(
                                [round(float(v), 4) for v in regions[0][:4]])
                            located += 1
                        else:
                            # Flagged with no box: known to be marked, position
                            # unknown. Exactly the state the pre-box builds
                            # produced, and _watermark_scan_query already adopts
                            # those rows on a plain re-run.
                            row.watermark_bbox = None
                        detected += 1
                    else:
                        row.watermark_state = 'none'
                        row.watermark_bbox = None
                        clean += 1
                    bank_jobs.bump(job)
                    # Per image, for the same reason the vision route commits per
                    # image: never hold the single SQLite write lock across an
                    # unbounded number of inferences.
                    db.session.commit()
        except watermark_detector.DetectorUnavailable as e:
            # The extra probed OK but could not actually run (weights half
            # downloaded, a torch that no longer imports in that env). Say so and
            # leave every unscanned row untouched — a retry, or an uninstall back
            # to the vision model, both finish the job.
            db.session.commit()
            logger.warning('bank watermark scan: detector unavailable (%s)', e)
            bank_jobs.progress(
                job, detail=f'stopped — the watermark detector could not run ({e}). '
                            'Nothing was mis-flagged; the images it had not reached '
                            'are still unscanned.')
            return
        finally:
            db.session.commit()
            shutil.rmtree(cancel_dir, ignore_errors=True)
        if bank_jobs.cancelled(job):
            bank_jobs.progress(job, detail=f'cancelled — {detected} with a watermark '
                                           f'so far')
            return
        detail = (f'done — {detected} with a watermark, {clean} clean '
                  f'(detector, score ≥ {threshold:g})')
        if detected and located < detected:
            detail += (f', {detected - located} flagged without a position '
                       '(they cannot be cropped or repainted until you draw a zone '
                       'in ▶ Review)')
        if vanished:
            detail += f', {vanished} skipped (deleted while the pass ran)'
        if errors:
            detail += f', {errors} unreadable'
        bank_jobs.progress(job, detail=detail)
    return run


# --- watermark cleaning: two MANUAL levels ----------------------------------
# The bank's folder belongs to the user and is never written to, so "cleaning a
# watermark" here means writing a SEPARATE cleaned blob under the bank's own
# working directory (clean/<image_id>.webp) and pointing the readers at it
# (resolved_image_path). The original therefore stays untouched by construction,
# which is what makes undo trivial and both levels risk-free.
#
# The escalation is deliberate and each level is launched BY HAND:
#   level 1 — ✂ auto-crop: CPU/PIL, invents no pixel. Only touches marks the
#             dataset router calls croppable (inside a border band, and the crop
#             still leaves a usable image). Everything else is left flagged.
#   level 2 — 🧽 inpaint: LaMa (fast, non-generative) or Klein (ComfyUI, handles
#             on-subject marks) over what is STILL flagged. allow_crop=False, so
#             a border mark that level 1 skipped (or that the user never cropped)
#             is repainted rather than cropped — level 2 is the "repaint what's
#             left" lane, not a second router.
# Both reuse the dataset routing/engines verbatim; nothing about the decision
# logic is re-implemented here.
def _clean_pool_query(bank_id):
    """Images a cleaning level can act on: still flagged, with SOMETHING to act
    on, not rejected. 'cleaned'/'dismissed'/'none' rows are out by construction.

    "Something to act on" is the stored bbox OR a hand-drawn mask: a row the
    detector left without a box (an older build) becomes cleanable the moment
    the user draws the zones themselves — that drawing IS the missing box."""
    return (BankImage.query.filter_by(bank_id=bank_id,
                                      watermark_state='detected')
            .filter(BankImage.status != 'reject')
            .filter(or_(BankImage.watermark_bbox.isnot(None),
                        BankImage.watermark_regions.isnot(None))))


def _needs_rescan_count(bank_id) -> int:
    """Rows flagged by an older build that kept no bbox — nothing can route them
    until a scan re-adopts them (see _watermark_scan_query). A row the user has
    masked by hand is NOT one of them: it no longer needs the detector."""
    return (BankImage.query.filter_by(bank_id=bank_id, watermark_state='detected')
            .filter(BankImage.status != 'reject')
            .filter(BankImage.watermark_bbox.is_(None))
            .filter(BankImage.watermark_regions.is_(None)).count())


def _drop_clean_blob_by_id(bank_id, image_id) -> None:
    """_discard_clean_blob for an image whose ROW is gone (deleted mid-pass).

    Only the blob and the derived thumbnails are left to clean up — there is no
    `watermark_clean_method` to clear, because there is no row. Without this a
    cancelled or interrupted cleaning level would leave the staged copy behind
    with nothing pointing at it."""
    try:
        clean_image_path(bank_id, image_id).unlink()
    except OSError:
        pass
    drop_derived(bank_id, image_id)


def _discard_clean_blob(bank_id, row) -> None:
    """Forget a cleaned version: delete the blob, drop the stale thumbnail and
    clear the method so the readers fall back to the source. No commit (the
    caller owns the transaction)."""
    _drop_clean_blob_by_id(bank_id, row.id)
    row.watermark_clean_method = None


def _clean_bbox(row):
    """The stored bbox as a 4-float tuple, or None when it's unusable."""
    try:
        import json as _json
        box = _json.loads(row.watermark_bbox or '')
    except (ValueError, TypeError):
        return None
    if not (isinstance(box, list) and len(box) == 4):
        return None
    try:
        return tuple(float(v) for v in box)
    except (TypeError, ValueError):
        return None


def _clean_regions(row):
    """THE mask both cleaning levels must act on — ``(boxes, manual, problem)``.

    A hand-drawn mask WINS over the detector's bbox. That is the entire point of
    letting the user edit it: a correction the cleaning pass then ignores is
    worse than no editor at all, because the user believes the fix landed.

    ``manual`` says the boxes came from the user (drives the routing: a hand mask
    is a REPAINT instruction — it can hold several zones and zones on the subject,
    neither of which a border crop can express, exactly like the dataset lane).
    An EMPTY manual mask returns ``([], True, None)``: an explicit "nothing to
    repaint here", never a silent fall back to the box. ``problem`` is set only
    when the stored JSON cannot be read as a mask (a genuine failure)."""
    if row.watermark_regions is not None:
        import json as _json
        try:
            stored = _json.loads(row.watermark_regions or '')
        except (ValueError, TypeError):
            return [], True, 'unreadable watermark regions'
        try:
            regions = normalize_watermark_regions(stored, allow_null=False)
        except ValueError as e:
            return [], True, f'invalid watermark regions: {e}'
        return [tuple(box) for box in regions], True, None
    bbox = _clean_bbox(row)
    return ([bbox] if bbox else []), False, None


def _source_size(bank, row):
    """(path, W, H) in the browser/VLM's visual orientation.

    Watermark boxes come from the EXIF-oriented vision payload. Returning raw
    camera dimensions here would route/crop a 90° JPEG in a different coordinate
    system than both the user and the model saw.
    """
    path = abs_image_path(bank, row)
    if not path or not os.path.isfile(path):
        return None, 0, 0
    try:
        with safe_bank_source(path, label='bank watermark') as im:
            # Header-only: level badges poll this for potentially thousands
            # of files, so do not materialise an EXIF transpose just to know
            # whether browser/VLM geometry swaps axes.
            return path, *image_encoding.visual_size_from_header(im)
    except (OSError, ValueError, MemoryError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        return None, 0, 0


def _stage_clean_copy(bank_id, row, src_path) -> Path:
    """Create an upright, metadata-free working image for Bank cleaning.

    Crop, LaMa and Klein all consume visual/VLM boxes. They therefore edit a
    freshly rebuilt WebP in the Bank's ``clean/`` directory, never a byte copy of
    a raw EXIF-tagged source. The source remains read-only and recoverable; the
    clean blob is atomically published only once its staging write succeeded.
    """
    dst = clean_image_path(bank_id, row.id)
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f'.{dst.name}.part-{uuid.uuid4().hex[:8]}')
    try:
        with safe_bank_source(src_path, label='bank watermark clean') as source:
            source.load()
            oriented = ImageOps.exif_transpose(source)
            mode = ('RGBA' if ('A' in oriented.getbands()
                               or 'transparency' in getattr(oriented, 'info', {}))
                    else 'RGB')
            clean = Image.new(mode, oriented.size)
            clean.paste(oriented.convert(mode))
        image_encoding.save_edit(clean, str(tmp), 'WEBP', image_encoding.LOSSLESS)
        os.replace(tmp, dst)
    except (OSError, ValueError, MemoryError, Image.DecompressionBombError,
            Image.DecompressionBombWarning):
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    return dst


def start_watermark_crop(app, user_id, bank_id):
    """Level 1 — crop away every watermark that sits in a border band. Pure
    CPU/PIL, no model, no GPU: this level is always available. ValueError when
    there is nothing to crop (the UI disables the button, this is the race)."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    # Hand-masked rows are level 2's, so they don't count as work for this level:
    # launching a crop that can only skip them would report "0 cropped" and read
    # as a broken button.
    total = (_clean_pool_query(bank_id)
             .filter(BankImage.watermark_regions.is_(None)).count())
    if not total:
        if _clean_pool_query(bank_id).count():
            raise ValueError('the flagged images all carry a hand-edited mask — '
                             'use 🧽 Inpaint, which repaints the zones you drew')
        raise ValueError('no flagged image to clean — run the watermark scan first')
    return bank_jobs.start(app, bank_id, 'watermark_crop',
                           _watermark_crop_job(bank_id), total=total)


def _watermark_crop_job(bank_id):
    def run(job):
        from .face_dataset_service import _apply_watermark_crop, _route_watermark
        bank = _detach_bank(db.session.get(ImageBank, bank_id))
        if not bank:
            return
        rows = _clean_pool_query(bank_id).order_by(BankImage.id.asc()).all()
        bank_jobs.progress(job, done=0, total=len(rows), detail='auto-crop')
        row_ids = [r.id for r in rows]
        cropped = left = failed = vanished = 0
        try:
            for rid in row_ids:
                if bank_jobs.cancelled(job):
                    break
                row = _live_image(rid)
                if row is None:      # deleted since the pass started — see _live_image
                    logger.info('bank auto-crop: image %s was deleted mid-pass, '
                                'skipping it', rid)
                    vanished += 1
                    bank_jobs.bump(job)
                    continue
                boxes, manual, _problem = _clean_regions(row)
                if manual:
                    # A hand mask is level 2's material, mask emptied or not. It
                    # can carry several zones and zones on the subject; cropping
                    # cannot express either, and quietly cropping the detector's
                    # old box would clean pixels the user did NOT point at.
                    left += 1
                    bank_jobs.bump(job)
                    continue
                bbox = boxes[0] if boxes else None
                src, width, height = _source_size(bank, row)
                if not bbox or not src:
                    failed += 1
                    bank_jobs.bump(job)
                    continue
                route, box = _route_watermark(bbox, width, height, allow_crop=True)
                if route != 'crop':
                    left += 1              # level 2's job — stays 'detected'
                    bank_jobs.bump(job)
                    continue
                try:
                    dst = _stage_clean_copy(bank_id, row, src)
                except (OSError, ValueError, MemoryError, Image.DecompressionBombError,
                        Image.DecompressionBombWarning):
                    _discard_clean_blob(bank_id, row)
                    failed += 1
                    bank_jobs.bump(job)
                    continue
                if _apply_watermark_crop(str(dst), box):
                    row.watermark_state = 'cleaned'
                    row.watermark_clean_method = 'crop'
                    drop_derived(bank_id, row.id)
                    cropped += 1
                else:
                    _discard_clean_blob(bank_id, row)
                    failed += 1
                if (cropped + failed) % 25 == 0:
                    db.session.commit()
                bank_jobs.bump(job)
        finally:
            db.session.commit()
        if bank_jobs.cancelled(job):
            bank_jobs.progress(job, detail=f'cancelled — {cropped} cropped so far')
            return
        detail = f'done — {cropped} cropped, {left} left for inpainting'
        if vanished:
            detail += f', {vanished} skipped (deleted while the pass ran)'
        if failed:
            detail += f', {failed} unreadable'
        bank_jobs.progress(job, detail=detail)
    return run


def _watermark_inpaint_prereq(method) -> str | None:
    """Why level 2 can't run right now, or None. Actionable text — an unavailable
    engine must say what to install, never fail silently mid-pass."""
    from . import watermark_klein, watermark_lama
    if method == 'klein':
        if not watermark_klein.is_available():
            return ('Klein inpainting needs ComfyUI running and the Klein weights '
                    '(Setup ▸ Generation models)')
        return None
    if not watermark_lama.is_available():
        return 'LaMa inpainting is not installed (Setup ▸ Quality tools)'
    return None


def start_watermark_inpaint(app, user_id, bank_id, method='auto'):
    """Level 2 — repaint what is STILL flagged after the crop level.
    ``method``: 'auto'/'lama' (LaMa, non-generative, small off-centre marks; marks
    on the subject stay flagged for manual review) or 'klein' (masked Flux.2 Klein
    through ComfyUI, which also handles on-subject marks). RuntimeError (→ 503) on
    a missing engine or a busy GPU, ValueError (→ 400) on a bad method / empty pool."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    method = (method or 'auto').lower()
    if method not in ('auto', 'lama', 'klein'):
        raise ValueError("method must be 'auto', 'lama' or 'klein'")
    total = _clean_pool_query(bank_id).count()
    if not total:
        raise ValueError('nothing left to inpaint — every flagged image is handled')
    problem = _watermark_inpaint_prereq(method)
    if problem:
        raise RuntimeError(problem)
    reason = _gpu_busy_reason()
    if reason:
        raise RuntimeError(reason)
    return bank_jobs.start(app, bank_id, 'watermark_inpaint',
                           _watermark_inpaint_job(bank_id, method), total=total)


def _watermark_inpaint_job(bank_id, method):
    def run(job):
        from contextlib import nullcontext
        from . import watermark_klein, watermark_lama
        from .face_dataset_service import _clean_inpaint_engine, _route_watermark
        from ..gpu_window import gpu_exclusive_vision_window
        bank = _detach_bank(db.session.get(ImageBank, bank_id))
        if not bank:
            return
        rows = _clean_pool_query(bank_id).order_by(BankImage.id.asc()).all()
        bank_jobs.progress(job, done=0, total=len(rows), detail='inpainting')
        row_ids = [r.id for r in rows]
        counts = {'inpainted': 0, 'klein': 0, 'review': 0, 'failed': 0,
                  'skipped': 0, 'empty': 0, 'vanished': 0}
        error = None
        lama_ok = watermark_lama.is_available()
        klein_ok = method == 'klein' and watermark_klein.is_available()
        # LaMa on the GPU pauses ComfyUI through the exclusive vision window;
        # Klein must NOT take that window — ComfyUI owns the GPU there and
        # holding it would deadlock its worker (same split as the dataset route).
        device = 'cpu' if method == 'klein' else watermark_lama.resolve_device()
        # (image_id, dst_path, [bbox]) for the single LaMa batch — ids, not ORM
        # rows: this list is held across a batch that can run for minutes, and a
        # row deleted in that window must be skippable rather than fatal.
        pending = []
        window = (gpu_exclusive_vision_window(flag_ttl=1800)
                  if device == 'cuda' else nullcontext())
        try:
            with window:
                for rid in row_ids:
                    if bank_jobs.cancelled(job):
                        break
                    row = _live_image(rid)
                    if row is None:  # deleted since the pass started — _live_image
                        logger.info('bank inpaint: image %s was deleted mid-pass, '
                                    'skipping it', rid)
                        counts['vanished'] += 1
                        bank_jobs.bump(job)
                        continue
                    boxes, manual, problem = _clean_regions(row)
                    src, width, height = _source_size(bank, row)
                    if problem or not src:
                        counts['failed'] += 1
                        error = error or (
                            {'kind': 'failed', 'detail': problem} if problem else None)
                        bank_jobs.bump(job)
                        continue
                    if manual and not boxes:
                        # The user deleted every zone. That is an ANSWER, not a
                        # missing value: repaint nothing, and never fall back to
                        # the detector's box. The row stays flagged (and visible)
                        # so it can be masked again or dismissed.
                        counts['empty'] += 1
                        bank_jobs.bump(job)
                        continue
                    if not boxes:
                        counts['failed'] += 1
                        bank_jobs.bump(job)
                        continue
                    if manual:
                        # Hand-drawn zones bypass the router entirely — same rule
                        # as the dataset: what the user drew IS the decision, and
                        # every zone is repainted with the selected engine.
                        engine = 'klein' if method == 'klein' else 'lama'
                    else:
                        # allow_crop=False: level 2 REPAINTS what is left, including a
                        # border mark the user chose not to crop.
                        route, _box = _route_watermark(boxes[0], width, height,
                                                       allow_crop=False)
                        engine = _clean_inpaint_engine(route, method)
                    if engine == 'review':
                        counts['review'] += 1       # stays flagged, needs Klein or a human
                        bank_jobs.bump(job)
                        continue
                    if (engine == 'klein' and not klein_ok) or \
                       (engine == 'lama' and not lama_ok):
                        counts['skipped'] += 1      # engine gone since launch
                        bank_jobs.bump(job)
                        continue
                    try:
                        dst = _stage_clean_copy(bank_id, row, src)
                    except (OSError, ValueError, MemoryError,
                            Image.DecompressionBombError, Image.DecompressionBombWarning):
                        _discard_clean_blob(bank_id, row)
                        counts['failed'] += 1
                        bank_jobs.bump(job)
                        continue
                    if engine == 'klein':
                        # No klein_model on purpose. The Klein model choice lives on
                        # the DATASET (it describes what a dataset is made of) and a
                        # bank has none to inherit — so this pass keeps the auto
                        # resolution it has always used. Deliberately NOT a global
                        # setting and NOT a third picker on the bank: that would be a
                        # second authority for the same UNETLoader. What the bank DOES
                        # owe the user is the name of the model that will run, which
                        # the panel now states (BankWatermarkPanel → /api/klein-model).
                        ok, err = watermark_klein.inpaint_watermark_klein(
                            bank.user_id, str(dst), [list(b) for b in boxes])
                        if ok:
                            row.watermark_state = 'cleaned'
                            row.watermark_clean_method = 'klein'
                            drop_derived(bank_id, row.id)
                            counts['klein'] += 1
                        else:
                            _discard_clean_blob(bank_id, row)
                            counts['skipped' if (err or {}).get('kind') == 'unavailable'
                                   else 'failed'] += 1
                            error = err or error
                        db.session.commit()
                        bank_jobs.bump(job)
                        continue
                    pending.append((rid, dst, [list(b) for b in boxes]))
                    bank_jobs.bump(job)
                if pending and bank_jobs.cancelled(job):
                    # Stop means stop: the staged copies of rows we never got to
                    # repaint are thrown away rather than running a long batch
                    # after the user asked out (they stay 'detected', retryable).
                    for pid, _dst, _boxes in pending:
                        _drop_clean_blob_by_id(bank_id, pid)
                    pending = []
                if pending:
                    results = watermark_lama.inpaint_batch(
                        [{'image_path': str(dst), 'bboxes': boxes}
                         for _rid, dst, boxes in pending], device=device)
                    for pid, dst, _boxes in pending:
                        row = _live_image(pid)
                        if row is None:
                            # Deleted while the batch ran: no row is left to point
                            # at the repainted copy, so throw the copy away too.
                            logger.info('bank inpaint: image %s was deleted while the '
                                        'batch ran, skipping it', pid)
                            _drop_clean_blob_by_id(bank_id, pid)
                            counts['vanished'] += 1
                            continue
                        ok, err = results.get(str(dst), (
                            False, {'kind': 'failed', 'detail': 'missing inpaint result'}))
                        if ok:
                            row.watermark_state = 'cleaned'
                            row.watermark_clean_method = 'lama'
                            drop_derived(bank_id, row.id)
                            counts['inpainted'] += 1
                        else:
                            _discard_clean_blob(bank_id, row)
                            counts['skipped' if (err or {}).get('kind') == 'unavailable'
                                   else 'failed'] += 1
                            error = err or error
        finally:
            db.session.commit()
        done = counts['inpainted'] + counts['klein']
        if bank_jobs.cancelled(job):
            bank_jobs.progress(job, detail=f'cancelled — {done} inpainted so far')
            return
        detail = f'done — {done} inpainted'
        if counts['review']:
            detail += (f", {counts['review']} on the subject "
                       '(switch the engine to Klein to repaint those)')
        if counts['empty']:
            # NOT lumped in with 'review': "on the subject" would send the user to
            # Klein for images where the honest answer is "your mask is empty".
            detail += (f", {counts['empty']} with an empty mask (draw a zone in "
                       '▶ Review, or dismiss them)')
        if counts['vanished']:
            detail += (f", {counts['vanished']} skipped "
                       '(deleted while the pass ran)')
        if counts['skipped']:
            detail += f", {counts['skipped']} skipped (engine unavailable)"
        if counts['failed']:
            detail += f", {counts['failed']} failed"
            if error and error.get('detail'):
                detail += f" — {error['detail']}"
        bank_jobs.progress(job, detail=detail)
    return run


def set_watermark_regions(user_id, bank_id, image_id, regions) -> dict | None:
    """Replace one flagged image's hand-drawn watermark mask (reported missing in
    the Bank by Qeeyana on Reddit — the Dataset had it, the Bank did not).

    ``regions`` is None (drop the override, go back to the detected box) or a list
    of normalized boxes — validated by the DATASET's validator, deliberately: one
    definition of a legal mask means the two lanes cannot drift apart. Returns the
    same payload shape the dataset route returns, None when the bank/image is
    unknown, ValueError on an illegal mask and RuntimeError when the image is no
    longer flagged (already cleaned/dismissed — an edit there would be a no-op).

    The mask is NOT cleared when a clean succeeds, unlike the dataset: the Bank's
    ↩ Undo is a first-class action (it only deletes our own blob), and handing an
    image back with its hand-drawn zones erased would mean redrawing them."""
    if not get_bank(user_id, bank_id):
        return None
    owned = BankImage.query.filter_by(id=image_id, bank_id=bank_id)
    row = owned.one_or_none()
    if not row:
        return None
    if row.watermark_state != 'detected':
        raise RuntimeError('this image is no longer flagged — nothing to mask')
    normalized = normalize_watermark_regions(regions)
    import json as _json
    stored = _json.dumps(normalized) if normalized is not None else None
    updated = (BankImage.query
               .filter_by(id=row.id, bank_id=bank_id, watermark_state='detected')
               .update({'watermark_regions': stored}, synchronize_session=False))
    if updated != 1:
        db.session.rollback()
        if owned.one_or_none() is None:
            return None
        raise RuntimeError('this image is no longer flagged — nothing to mask')
    db.session.commit()
    return _watermark_regions_payload(row)


def undo_watermark_clean(user_id, bank_id, image_ids=None) -> int:
    """Throw away cleaned versions and re-flag the images. The source was never
    modified, so undoing is just deleting our own blob — which is exactly what
    makes running both levels risk-free. ``image_ids`` empty = every cleaned
    image of the bank. Returns how many rows were restored."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    q = BankImage.query.filter_by(bank_id=bank_id, watermark_state='cleaned')
    if image_ids:
        ids = [int(i) for i in image_ids]
        q = q.filter(BankImage.id.in_(ids[:_SQL_IN_CHUNK]))
    rows = q.all()
    for row in rows:
        _discard_clean_blob(bank_id, row)
        # Back to 'detected' with its bbox intact, so it re-enters both levels
        # (e.g. to retry with the other engine).
        row.watermark_state = 'detected'
    if rows:
        db.session.commit()
    return len(rows)


def dismiss_watermarks(user_id, bank_id, image_ids) -> int:
    """Rule a flag a FALSE positive: 'detected' → 'dismissed'. Those images leave
    both cleaning levels and are never re-flagged by a later scan — without this,
    level 2 would happily repaint a legitimate logo on a T-shirt. Mirrors the
    dataset's dismiss_watermarks. Returns how many rows changed."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    ids = [int(i) for i in (image_ids or [])]
    if not ids:
        return 0
    rows = (BankImage.query
            .filter_by(bank_id=bank_id, watermark_state='detected')
            .filter(BankImage.id.in_(ids[:_SQL_IN_CHUNK])).all())
    for row in rows:
        row.watermark_state = 'dismissed'
    if rows:
        db.session.commit()
    return len(rows)


def _watermark_source_counts(bank_id) -> dict:
    """How many SCANNED rows each detection route produced. A row with a state but
    no source predates the column — counted as 'unknown', never attributed."""
    scanned = BankImage.query.filter_by(bank_id=bank_id).filter(
        BankImage.watermark_state.isnot(None))
    detector = scanned.filter(BankImage.watermark_source == 'detector').count()
    vision = scanned.filter(BankImage.watermark_source == 'vision').count()
    return {'detector': detector, 'vision': vision,
            'unknown': scanned.count() - detector - vision}


def _detector_ready() -> bool:
    """Whether the NEXT run will use the detector — which is now the resolved
    SETTING, not merely "is the extra installed". The panel's sentence says "a new
    run uses …", so reading availability alone would make it lie the moment a user
    pinned the vision model on a machine that has the extra.

    Never raises: a probe that explodes must not 500 the whole panel — it just
    means the next run is the vision model, which is the shipped behaviour."""
    try:
        from . import watermark_detector
        return watermark_detector.resolve_backend()['backend'] == 'detector'
    except Exception:      # noqa: BLE001
        return False


def _detector_threshold() -> float:
    try:
        from . import watermark_detector
        return watermark_detector.threshold()
    except Exception:      # noqa: BLE001
        return 0.94


def watermark_levels(user_id, bank_id) -> dict | None:
    """Where each cleaning level stands — the numbers the UI shows per level.
    None when the bank is gone."""
    if not get_bank(user_id, bank_id):
        return None
    from .face_dataset_service import _route_watermark
    bank = db.session.get(ImageBank, bank_id)
    base = BankImage.query.filter_by(bank_id=bank_id)
    flagged = croppable = hand_masked = empty_masks = 0
    for row in _clean_pool_query(bank_id).all():
        flagged += 1
        boxes, manual, _problem = _clean_regions(row)
        if manual:
            # A hand mask never routes to the crop level (see _watermark_crop_job),
            # so it must not be counted as croppable — the ✂ button would offer
            # work it will then skip.
            hand_masked += 1
            if not boxes:
                empty_masks += 1
            continue
        # Stored scan dimensions are raw camera-raster dimensions. Watermark
        # boxes instead come from the upright vision/browser frame, so this
        # tally intentionally re-reads the inexpensive header through
        # `_source_size` rather than incorrectly trusting row.width/height.
        _path, width, height = _source_size(bank, row)
        if boxes and width and _route_watermark(boxes[0], width, height,
                                                allow_crop=True)[0] == 'crop':
            croppable += 1
    return {
        'scanned': base.filter(BankImage.watermark_state.isnot(None)).count(),
        # What a plain re-run would still look at. Detection resumes where it
        # stopped (the pass commits every 25 rows), but nothing said so: a
        # progress bar that restarts at 0 each run reads as "it started over
        # and is re-analysing what I already did". This is the number that
        # answers that, so the panel can say "N left to scan" out loud.
        'unscanned': _watermark_scan_query(bank_id, rescan=False).count(),
        'flagged': flagged,
        'croppable': croppable,
        'inpaintable': flagged - croppable,
        # Flagged images whose mask the user drew by hand, and how many of those
        # were deliberately emptied. Both are surfaced: an empty mask repaints
        # nothing, and a level that silently skips images is how a user ends up
        # believing a watermark was removed when it was not.
        'hand_masked': hand_masked,
        'empty_masks': empty_masks,
        'cropped': base.filter_by(watermark_clean_method='crop').count(),
        'inpainted': base.filter(
            BankImage.watermark_clean_method.in_(('lama', 'klein'))).count(),
        'dismissed': base.filter_by(watermark_state='dismissed').count(),
        'needs_rescan': _needs_rescan_count(bank_id),
        # WHO ruled on the images already scanned. Surfaced because the two
        # routes are not the same instrument and a bank scanned over weeks can
        # hold both: 'detector' rows carry a score and a threshold you can
        # change, 'vision' rows carry a sentence a model wrote. 'unknown' is
        # every row scanned before this was recorded — named rather than
        # attributed, because guessing which one produced them would be a lie.
        'sources': _watermark_source_counts(bank_id),
        # Which route the NEXT run would take, and (when it is the detector) the
        # score it will flag at. The panel quotes these instead of keeping its own
        # copy of the default.
        'next_source': ('detector' if _detector_ready() else 'vision'),
        'threshold': _detector_threshold(),
        # A few already-cleaned ids so the panel can offer a before/after strip
        # (each image is served cleaned, or original with ?original=1) without a
        # second endpoint just to list them.
        'cleaned_sample': [r.id for r in
                           base.filter(BankImage.watermark_clean_method.isnot(None))
                           .order_by(BankImage.id.asc()).limit(8).all()],
    }


# --- framing pass (reuses the dataset face/bust/body/back classifier) -------
def start_framing(app, user_id, bank_id, rescan=False):
    """Classify every non-rejected image by SHOT TYPE (face / bust / body / back),
    reusing the SAME Qwen3-VL classifier the datasets use (CLASSIFY_PROMPT). Feeds
    the 📐 Framing filter chips and the coverage advice. Needs the vision model
    pulled; serialized against training/vision like the watermark pass (503 when
    the GPU is held). ``rescan`` re-classifies rows that already have a framing."""
    from ..capabilities import probe_ollama_model
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    # Occupancy BEFORE the model probe, and the order is the whole point: a bank
    # that is already busy is busy whether or not Ollama answers. Probing first
    # made a busy bank report "the vision model is not available" whenever the
    # model happened to be unreachable -- the wrong reason, sending the user to
    # fix an unrelated thing while the real answer was "wait, a pass is running".
    # It also made the refusal depend on an EXTERNAL SERVICE, which is why CI
    # (no Ollama) failed a release on it while two agents read it as a flake.
    if bank_jobs.running(bank_id):
        raise bank_jobs.BankJobBusy((bank_jobs.get(bank_id) or {}).get('kind') or 'background')
    if not probe_ollama_model().get('ok'):
        raise RuntimeError('the vision model is not available '
                           '(Settings ▸ Local tools)')
    reason = _gpu_busy_reason()
    if reason:
        raise RuntimeError(reason)
    q = BankImage.query.filter_by(bank_id=bank_id).filter(BankImage.status != 'reject')
    if not rescan:
        q = q.filter(BankImage.framing.is_(None))
    return bank_jobs.start(app, bank_id, 'framing',
                           _framing_job(bank_id, rescan), total=q.count())


def _framing_job(bank_id, rescan):
    def run(job):
        from .face_dataset_service import CLASSIFY_PROMPT, _parse_classify
        from .vision_ollama import describe_image_ollama, unload_vision_model
        from .vision_pool import map_vision
        from ..gpu_window import gpu_exclusive_vision_window
        bank = _detach_bank(db.session.get(ImageBank, bank_id))
        if not bank:
            return
        q = (BankImage.query.filter_by(bank_id=bank_id)
             .filter(BankImage.status != 'reject'))
        if not rescan:
            q = q.filter(BankImage.framing.is_(None))
        rows = q.order_by(BankImage.id.asc()).all()
        bank_jobs.progress(job, done=0, total=len(rows), detail='framing')
        if not rows:
            return
        row_ids = [r.id for r in rows]
        classified = errors = vanished = 0

        def prepared():
            """Path resolution reads the row, so it belongs on the job's own
            thread — pulled one image per free slot in the pool."""
            nonlocal vanished
            for rid in row_ids:
                row = _live_image(rid)
                if row is None:      # deleted since the pass started — see _live_image
                    logger.info('bank framing pass: image %s was deleted mid-pass, '
                                'skipping it', rid)
                    vanished += 1
                    bank_jobs.bump(job)
                    continue
                yield rid, abs_image_path(bank, row)

        def ask(item):
            """WORKER thread: file + network only, no session. None means the
            file is gone, as opposed to '' meaning the model said nothing."""
            _rid, path = item
            if not path or not os.path.isfile(path):
                return None
            return describe_image_ollama(
                _read_safe_bank_source_bytes(path, label='bank framing scan'),
                CLASSIFY_PROMPT, num_predict=400,
                prefer_json=True, fmt='json', keep_alive='5m')

        with gpu_exclusive_vision_window(flag_ttl=1800):
            try:
                # The calls overlap (see vision_pool); every write below still
                # happens here, on this one thread.
                for (rid, _path), raw, error in map_vision(
                        prepared(), ask,
                        should_cancel=lambda: bank_jobs.cancelled(job)):
                    # Re-read: the classification we are about to store took a
                    # model call to arrive, and the image can be gone by now.
                    row = _live_image(rid)
                    if row is None:
                        logger.info('bank framing pass: image %s was deleted while it '
                                    'was being classified, skipping it', rid)
                        vanished += 1
                        bank_jobs.bump(job)
                        continue
                    if error is not None:  # one bad file never sinks the pass
                        errors += 1
                    elif raw is None:      # file gone: leave the row as it was
                        pass
                    # Empty output = Ollama unreachable, NOT "unknown": leave the
                    # framing NULL so a retry can finish it (same reasoning as the
                    # watermark/dataset classifier), never mislabel everything.
                    elif not raw.strip():
                        pass
                    else:
                        framing, _label = _parse_classify(raw)
                        row.framing = framing        # face|bust|body|back|unknown
                        classified += 1
                        if classified % 25 == 0:
                            db.session.commit()
                    bank_jobs.bump(job)
            finally:
                db.session.commit()
                unload_vision_model()  # hand the VRAM back to ComfyUI
        if bank_jobs.cancelled(job):
            bank_jobs.progress(job, detail=f'cancelled — {classified} classified so far')
            return
        detail = f'done — {classified} classified'
        if vanished:
            detail += f', {vanished} skipped (deleted while the pass ran)'
        if errors:
            detail += f', {errors} unreadable'
        bank_jobs.progress(job, detail=detail)
    return run


# --- 🎨 medium pass (zero-shot CLIP over the ✨ Score embeddings) ------------
def medium_prereq(bank_id=None) -> str | None:
    """Why 🎨 Medium cannot run here, or None. Two distinct refusals, and telling
    them apart is the point: a bank with no ✨ Score embeddings needs a pass run,
    while a machine that cannot encode text needs a Setup step. Answering either
    with the other sends the user to fix the wrong thing."""
    from . import clip_text_encoder
    if bank_id is not None:
        scored = (BankImage.query.filter_by(bank_id=bank_id)
                  .filter(or_(BankImage.aesthetic_score.isnot(None),
                              BankImage.nsfw_score.isnot(None))).count())
        if not scored:
            return ('run ✨ Score first — 🎨 Medium reads the embeddings it '
                    'computes, and computes none of its own')
    return clip_text_encoder.unavailable_reason()


def start_medium(app, user_id, bank_id, rescan=False):
    """Classify every SCORED image by MEDIUM (photograph / anime / 3D render /
    illustration, or an honest 'unsure') from the CLIP embedding the ✨ Score pass
    already cached.

    NO NEW IMAGE INFERENCE, by construction: the only model call this pass makes
    is encoding ~30 short phrases through CLIP's text tower, once per install
    (clip_text_encoder caches every phrase on disk, forever, across restarts), on
    the CPU. Everything after that is a (n × 768) @ (768 × 6) matrix product in
    the Flask process. An image the ✨ Score pass never reached has no embedding
    and stays NULL — "not scored yet", which is neither a medium nor an 'unsure'.

    ``rescan`` re-classifies rows that already carry a verdict; without it the
    pass finishes the job (rows with medium IS NULL), so it can be re-run after a
    ✨ Score that added images without redoing the whole bank.

    Never takes the GPU window and is not refused when the GPU is busy: it does
    not touch the card, and blocking it behind a training run would be a refusal
    with no cause."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    if bank_jobs.running(bank_id):
        raise bank_jobs.BankJobBusy((bank_jobs.get(bank_id) or {}).get('kind') or 'background')
    reason = medium_prereq(bank_id)
    if reason:
        raise RuntimeError(reason)
    q = BankImage.query.filter_by(bank_id=bank_id).filter(BankImage.status != 'reject')
    if not rescan:
        q = q.filter(BankImage.medium.is_(None))
    return bank_jobs.start(app, bank_id, 'medium', _medium_job(bank_id, rescan),
                           total=q.count())


def _medium_prototype_matrix():
    """(bucket_names, P) — one L2-normed row per bucket, each the MEAN of its
    phrases' text vectors (prompt ensembling). Raises clip_text_encoder's
    TextEncodeError, which the route turns into an announced 503."""
    import numpy as np
    from . import clip_text_encoder
    names, rows = [], []
    for name, phrases in MEDIUM_PROTOTYPES.items():
        vecs = [clip_text_encoder.encode_query(p)[0] for p in phrases]
        m = np.mean(np.stack(vecs).astype('float32'), axis=0)
        rows.append(m / (float(np.linalg.norm(m)) + 1e-8))
        names.append(name)
    return names, np.stack(rows).astype('float32')


def _medium_job(bank_id, rescan):
    def run(job):
        import numpy as np
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        bank_jobs.progress(job, done=0, detail='medium pass — encoding prototypes')
        names, P = _medium_prototype_matrix()
        emb_by_path = _load_score_embeddings(bank)
        q = BankImage.query.filter_by(bank_id=bank_id).filter(BankImage.status != 'reject')
        if not rescan:
            q = q.filter(BankImage.medium.is_(None))
        rows = q.order_by(BankImage.id.asc()).all()
        bank_jobs.progress(job, done=0, total=len(rows), detail='medium pass')
        base = os.path.realpath(bank.source_path)
        prefix = os.path.normcase(base + os.sep)
        done = classified = unscored = 0
        for r in rows:
            if bank_jobs.cancelled(job):
                break
            # Same two-step path resolution as _pool_embeddings: a lexical
            # normpath that HITS the cache is provably what realpath would have
            # returned, and realpath is a syscall this loop cannot afford once
            # per row on a 20 000-image bank.
            p = os.path.normpath(os.path.join(base, r.relpath))
            emb = emb_by_path.get(p) if os.path.normcase(p).startswith(prefix) else None
            if emb is None:
                p2 = _abs_under(base, r.relpath)
                emb = emb_by_path.get(p2) if p2 else None
            if emb is None:
                unscored += 1          # no embedding → stays NULL, honestly
            else:
                e = np.asarray(emb, dtype='float32')
                e = e / (float(np.linalg.norm(e)) + 1e-8)
                sims = P @ e
                verdict, margin = medium_verdict(dict(zip(names, sims)))
                r.medium = verdict
                r.medium_margin = round(float(margin), 5) if margin is not None else None
                classified += 1
            done += 1
            bank_jobs.bump(job)
            if done % 500 == 0:
                db.session.commit()
        db.session.commit()
        detail = f'done — {classified} classified'
        if unscored:
            # Never silent: an image with no ✨ Score embedding CANNOT get a
            # medium, and "0 results" without that sentence reads as a bug.
            detail += f', {unscored} skipped (not scored yet)'
        if bank_jobs.cancelled(job):
            detail = (f'stopped — {classified} classified, '
                      f'{len(rows) - done} left (re-run to finish)')
        bank_jobs.progress(job, detail=detail)
    return run


# --- caption pass (reuses the dataset caption engines) ----------------------
# The statuses a caption pass may be AIMED at. 'reject' is absent on purpose and
# it is not an oversight: you curate from what you might keep, never from the bin
# — the same rule every other pass on this page follows. Values are the ones
# stored in the column ('keep' / 'pending'); the UI says "Kept" and "Undecided".
# Renaming either would break stored queries, so the wire keeps the column's
# vocabulary and the translation happens in the label.
CAPTION_SCOPES = ('keep', 'pending')


def _normalize_caption_statuses(statuses):
    """Validate a per-run caption scope, or None for the historical set.

    None / [] → None, which means the pass keeps its original
    ``status != 'reject'`` filter: a client that sends no scope is
    byte-identical to before this option existed. Anything outside
    CAPTION_SCOPES — 'reject' first among them — raises ValueError → 400,
    exactly like a bad vocabulary or length."""
    if statuses is None:
        return None
    if isinstance(statuses, str):       # a lone 'keep' is a scope of one
        statuses = [statuses]
    if not isinstance(statuses, (list, tuple, set)):
        raise ValueError('invalid caption statuses: expected a list of statuses')
    want = []
    for s in statuses:
        if not isinstance(s, str):
            raise ValueError('invalid caption status: expected status names')
        v = s.strip().lower()
        if not v:
            continue
        if v not in CAPTION_SCOPES:
            raise ValueError(f'invalid caption status: {v}')
        want.append(v)
    if not want:
        return None
    # Canonical order + dedup, so ['pending','keep'] and ['keep','pending'] are
    # one value and never two code paths.
    return [s for s in CAPTION_SCOPES if s in want]


def _caption_name_option(name, value):
    """Normalize one free-text caption option, or raise ValueError → 400.

    Every one of these options is a NAME out of a closed list. A non-string reached
    ``.strip()`` and answered 500 — a bad request rendered as a broken server, while
    ``statuses`` next door already answered 400 for exactly the same mistake. The
    validation now matches the promise the route's docstring makes ("invalid → 400")."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'invalid caption {name}: expected a name, not '
                         f'{type(value).__name__}')
    return value.strip().lower() or None


def _caption_scope_q(bank_id, statuses):
    """The rows a caption pass may touch, for this bank and this scope.

    ONE definition, called by the launch (to price the run) and by the job (to do
    it). Two copies of this filter is precisely how a button comes to announce a
    number it does not act on."""
    q = BankImage.query.filter_by(bank_id=bank_id)
    if statuses is None:
        return q.filter(BankImage.status != 'reject')
    return q.filter(BankImage.status.in_(statuses))


def start_caption(app, user_id, bank_id, ids=None, force=False, vocabulary=None,
                  length=None, backend=None, ollama_model=None, statuses=None,
                  include_asserted=False):
    """Launch the caption pass over a selection (``ids``) or, when empty, every
    non-rejected readable image. Reuses the dataset caption engines (JoyCaption /
    Ollama per Settings) through a dataset-free descriptive brick; the captions
    double as the bank's search text and ride along on promotion. Serialized
    against training/vision like the score/watermark passes (503 when the GPU is
    held). BankJobBusy when a job is already live, ValueError on a bad bank/config.

    ``vocabulary`` picks a caption REGISTER (one of face_dataset_service's
    CAPTION_VOCABULARIES: 'explicit' | 'clinical' | 'safe') — the SAME lane the
    dataset caption uses, appended as an instruction. Explicit only spells sexual
    content out when the backend runs an abliterated Ollama model; the choice rides
    per-call (the UI passes it), so a call WITHOUT it is byte-identical to before
    (no instruction appended). Richer captions also mean richer 🔍 search text.

    ``length`` picks the SIZE preset (one of CAPTION_LENGTHS: 'concise' | 'detailed';
    None/'' = standard, nothing appended) — an axis orthogonal to the register, again
    the same lane and the same text as the dataset caption.

    ``backend`` overrides ``captioning.backend`` for THIS run only (one of
    CAPTION_BACKENDS) and ``ollama_model`` overrides ``ollama.vision_model`` for THIS
    run only — the global settings stay the default and are never written. Which model
    writes a caption is not a matter of taste: a captioner that describes what it sees
    in evasive terms produces captions that are about something slightly other than the
    images, and a LoRA trained on them learns to look away too, with nothing in the
    output to reveal it (measured on the video lane, commit "the model that writes the
    captions stops being a decision we made"). Both empty → the global settings, so a
    call without them is byte-identical to before. 'auto' is left alone deliberately:
    it CHAINS JoyCaption then Ollama on what JoyCaption missed, so forcing 'joycaption'
    removes the Ollama half rather than "picking one of two".

    ``statuses`` picks the SCOPE of the run: ['keep'], ['pending'] or ['keep','pending']
    (CAPTION_SCOPES). None = the historical non-rejected set, byte-identical to before.
    'reject' is refused — the bin is never captioned. When ``ids`` are also given the
    two INTERSECT (the selection is narrowed by the scope, never widened).

    ``force`` rewrites captions that already exist — and, since captions carry an
    origin (services/caption_origin.py), it now SPARES the ones a human wrote or
    corrected, the way the embeddings pass spares an asserted face cluster. Rows
    whose origin was never recorded (every row that predates the column) are
    rewritten: their authorship cannot be recovered, and sparing them would make
    this button inert on every bank that exists today. ``include_asserted`` is the
    explicit way OUT of that protection — a separate opt-in, never a default,
    for the person who does want their own captions redone by a better model.
    It means nothing without ``force`` and is ignored there (an unforced pass
    only ever touches rows with no caption at all)."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    from .face_dataset_service import (CAPTION_BACKENDS, CAPTION_LENGTHS,
                                       CAPTION_VOCABULARIES)
    vocab = _caption_name_option('vocabulary', vocabulary)
    if vocab and vocab not in CAPTION_VOCABULARIES:
        raise ValueError(f'invalid caption vocabulary: {vocab}')
    size = _caption_name_option('length', length)
    if size and size not in CAPTION_LENGTHS:
        raise ValueError(f'invalid caption length: {size}')
    want = _normalize_caption_statuses(statuses)
    engine = _caption_name_option('backend', backend)
    if engine and engine not in CAPTION_BACKENDS:
        raise ValueError(f'invalid captioning backend: {engine}')
    # Same charset check the Caption Lab uses (never shelled out — it is a JSON
    # field to the local Ollama server), and the same allow_empty contract.
    from .ollama_control import normalize_ollama_model_ref
    model = normalize_ollama_model_ref(ollama_model or '', allow_empty=True) or None
    # The RESOLVED engine decides whether there is anything to run at all — a
    # per-run 'none' is refused exactly like the global one, and a per-run engine
    # rescues a run on an install whose global setting is 'none'.
    resolved = engine or (cfg.get('captioning.backend') or 'auto').lower()
    if resolved == 'none':
        raise ValueError('no captioning backend configured (Settings ▸ Captioning & quality)')
    reason = _gpu_busy_reason()
    if reason:
        raise RuntimeError(reason)
    ids = [int(i) for i in ids] if ids else None
    q = _caption_scope_q(bank_id, want)
    if ids is not None:
        q = q.filter(BankImage.id.in_(ids[:_SQL_IN_CHUNK]))
    keep_asserted = bool(force) and not include_asserted
    if not force:
        q = q.filter(or_(BankImage.caption.is_(None), BankImage.caption == ''))
    elif keep_asserted:
        # The protection, in the SAME query that prices the run — so the number
        # the button quotes is the number the job walks. Two definitions of this
        # filter is exactly how a button comes to announce work it does not do.
        q = q.filter(caption_origin.unprotected_clause(BankImage))
    total = q.count()
    return bank_jobs.start(app, bank_id, 'caption',
                           _caption_job(bank_id, ids, force, vocab, size,
                                        backend=engine, ollama_model=model,
                                        statuses=want,
                                        keep_asserted=keep_asserted),
                           total=total)


def _caption_job(bank_id, ids, force, vocabulary=None, length=None, *,
                 backend=None, ollama_model=None, statuses=None,
                 keep_asserted=False):
    def run(job):
        from .face_dataset_service import caption_paths, caption_preset_instructions
        from ..gpu_window import gpu_exclusive_vision_window
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        q = _caption_scope_q(bank_id, statuses)
        if ids is not None:
            rows = []
            for i0 in range(0, len(ids), _SQL_IN_CHUNK):
                rows.extend(q.filter(BankImage.id.in_(ids[i0:i0 + _SQL_IN_CHUNK])).all())
            rows.sort(key=lambda r: r.id)
        else:
            rows = q.order_by(BankImage.id.asc()).all()
        skipped_asserted = 0
        if not force:
            rows = [r for r in rows if not (r.caption or '').strip()]
        elif keep_asserted:
            # Same rule as the launch filter, re-applied on the rows the job
            # actually loaded: a caption can be typed in the seconds between
            # pricing the run and starting it, and the newer word wins.
            spared = [r for r in rows if caption_origin.is_protected(r)]
            skipped_asserted = len(spared)
            rows = [r for r in rows if not caption_origin.is_protected(r)]
        by_path = {}
        for r in rows:
            p = abs_image_path(bank, r)
            if _is_safe_bank_source(p, label='bank caption pass'):
                by_path[p] = r.id
        paths = list(by_path)
        bank_jobs.progress(job, done=0, total=len(paths), detail='captioning')
        if not paths:
            return
        captioned = vanished = 0

        def _on_caption(path, caption, engine=None):
            nonlocal captioned, vanished
            image_id = by_path.get(path)
            if image_id is None:
                return           # a path this pass never asked about — not ours
            row = _live_image(image_id)
            if row is None:      # deleted while it was being captioned — _live_image
                logger.info('bank caption pass: image %s was deleted mid-pass, '
                            'skipping its caption', image_id)
                vanished += 1
                return
            # WHICH engine wrote this row, reported by the engine that wrote it —
            # not the backend that was asked for. 'auto' chains both, so the
            # requested value would mislabel roughly half the bank.
            caption_origin.stamp(row, caption, caption_origin.engine_origin(engine))
            db.session.commit()
            captioned += 1

        # GPU-exclusive for the whole pass, exactly like the score/watermark passes:
        # frees ComfyUI VRAM and blocks a training start for the duration.
        # The vocabulary register and the length preset ride in as the SAME appended
        # instructions the dataset pass uses, in the same order (None when neither is
        # set → byte-identical to the plain pass).
        # The engine and the Ollama model ride the SAME per-call seam the Caption
        # Lab uses (caption_paths already takes both); None on either means "the
        # global setting", so a run that picks nothing is byte-identical.
        extra = caption_preset_instructions(vocabulary, length)
        with gpu_exclusive_vision_window(flag_ttl=1800):
            caption_paths(
                paths,
                backend=backend,
                ollama_model=ollama_model,
                extra_instructions=extra,
                should_cancel=lambda: bank_jobs.cancelled(job),
                on_caption=_on_caption,
                progress=lambda d, t: bank_jobs.progress(job, done=d, total=t))
        if bank_jobs.cancelled(job):
            bank_jobs.progress(job, detail=f'cancelled — {captioned} captioned so far')
            return
        detail = f'done — {captioned} captioned'
        if skipped_asserted:
            # Named in the RESULT, not only in the warning before the click: the
            # user has to be able to see afterwards that the protection did
            # something, otherwise it is a promise with no evidence.
            detail += f', {skipped_asserted} kept (written by you)'
        if vanished:
            detail += f', {vanished} skipped (deleted while the pass ran)'
        bank_jobs.progress(job, detail=detail)
    return run


# --- "Launch all" pipeline --------------------------------------------------
# The overnight funnel: the user configures it once, hits Launch all, and comes
# back to a triaged, optionally pre-captioned bank. It chains the EXISTING passes
# in the validated order. Each pass already filters status != 'reject', so
# running auto-reject BEFORE the heavy passes means score/watermark/person only
# ever touch the SURVIVORS — the costly work never pays for images we just
# dropped (the deliberate cost/quality trade-off: duplicate "keep best" therefore
# ranks on sharpness/size, not the aesthetic score that isn't computed yet).
PIPELINE_STEPS = ('scan', 'auto_reject', 'score', 'semantic_dedup', 'watermark',
                  'faces', 'framing', 'caption')
# Auto-reject inside the pipeline runs right after the quality scan, so it can
# only act on the CPU-scan flags (and duplicates). The score-derived flags
# (low_aesthetic/nsfw/watermark) have no data yet at that point.
#
# NOT every quality flag, though. `soft_detail` and `bars` are excluded ON
# PURPOSE — they are provenance HINTS, not verdicts, and their own documentation
# says so: a crisp watermark rescues an enlargement's detail ratio while a
# motion-blurred native shot sinks it, and `bars` fires on any dark-themed
# screenshot. The standalone 🧹 Auto-reject button still offers them, because
# there a human is looking at the flagged count, can undo on the spot, and the
# hint under the checkbox says "check before mass-rejecting". The pipeline is the
# opposite situation: unattended, and auto-reject runs FIRST, so anything it
# drops never reaches the score / watermark / caption passes at all — the mistake
# becomes invisible instead of reviewable. Offering a non-verdict as an overnight
# bulk rejection contradicts the measurement it is built on.
# The pipeline UI never offered these two; this makes the API agree with it.
_PIPELINE_EXCLUDED_REJECT_FLAGS = ('soft_detail', 'bars')
PIPELINE_REJECT_FLAGS = tuple(f for f in _QUALITY_FLAGS
                              if f not in _PIPELINE_EXCLUDED_REJECT_FLAGS)


def _sanitize_pipeline_steps(steps) -> list:
    """Keep only known steps, in the canonical pipeline order (the client can't
    reorder or invent a pass)."""
    want = set(steps or [])
    return [s for s in PIPELINE_STEPS if s in want]


def _score_prereq() -> str | None:
    from ..capabilities import probe_bank_scoring
    if not probe_bank_scoring().get('ok'):
        return 'bank scoring extra not installed (Setup ▸ Quality tools)'
    return None


def _watermark_prereq() -> str | None:
    from ..capabilities import probe_ollama_model
    if not probe_ollama_model().get('ok'):
        return 'vision model not available (Settings ▸ Local tools)'
    return None


def _faces_prereq() -> str | None:
    from .face_similarity import is_available
    if not is_available():
        return 'face scoring extra not installed (Setup ▸ Quality tools)'
    return None


def _framing_prereq() -> str | None:
    from ..capabilities import probe_ollama_model
    if not probe_ollama_model().get('ok'):
        return 'vision model not available (Settings ▸ Local tools)'
    return None


def _caption_prereq() -> str | None:
    if (cfg.get('captioning.backend') or 'auto').lower() == 'none':
        return 'no captioning backend configured (Settings ▸ Captioning & quality)'
    return None


def start_pipeline(app, user_id, bank_id, steps=None, reject_flags=None,
                   resolve_dups=False):
    """Launch the chained triage pipeline. ``steps`` selects which passes run
    (canonical order enforced); ``reject_flags`` + ``resolve_dups`` configure the
    auto-reject step. One background job like every other pass — BankJobBusy when
    one is already live, ValueError on a bad bank / empty step list."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    steps = _sanitize_pipeline_steps(steps)
    if not steps:
        raise ValueError('no pipeline steps selected')
    reject_flags = [f for f in (reject_flags or []) if f in PIPELINE_REJECT_FLAGS]
    return bank_jobs.start(
        app, bank_id, 'pipeline',
        _pipeline_job(user_id, bank_id, steps, reject_flags, bool(resolve_dups)),
        total=0)


def _bank_counts(bank_id) -> dict:
    """Live headline counts used for the per-step tallies and the final report."""
    base = BankImage.query.filter_by(bank_id=bank_id)
    dup_groups = (db.session.query(BankImage.dup_group)
                  .filter(BankImage.bank_id == bank_id,
                          BankImage.dup_group.isnot(None))
                  .distinct().count())
    style_groups = (db.session.query(BankImage.style_cluster)
                    .filter(BankImage.bank_id == bank_id,
                            BankImage.style_cluster.isnot(None))
                    .distinct().count())
    semantic_groups = (db.session.query(BankImage.semantic_dup_group)
                       .filter(BankImage.bank_id == bank_id,
                               BankImage.semantic_dup_group.isnot(None))
                       .distinct().count())
    person_groups = (db.session.query(BankImage.face_cluster)
                     .filter(BankImage.bank_id == bank_id,
                             BankImage.face_cluster.isnot(None))
                     .distinct().count())
    return {
        'total': base.count(),
        'scanned': base.filter(BankImage.quality_state.isnot(None)).count(),
        'reject': base.filter_by(status='reject').count(),
        'scored': base.filter(or_(BankImage.aesthetic_score.isnot(None),
                                  BankImage.nsfw_score.isnot(None))).count(),
        'watermark_detected': base.filter(BankImage.watermark_state == 'detected').count(),
        'framing_classified': base.filter(BankImage.framing.isnot(None)).count(),
        'captioned': base.filter(and_(BankImage.caption.isnot(None),
                                       BankImage.caption != '')).count(),
        'dup_groups': dup_groups,
        'style_groups': style_groups,
        'semantic_groups': semantic_groups,
        'person_groups': person_groups,
    }


def _pipeline_job(user_id, bank_id, steps, reject_flags, resolve_dups):
    def run(job):
        import json as _json
        import time as _time
        from ..gpu_window import GpuBusyError
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        results = []
        pipe = {'steps': list(steps), 'total_steps': len(steps),
                'index': 0, 'current': steps[0], 'results': results}

        def _sync(current=None, index=None):
            if index is not None:
                pipe['index'] = index
            if current is not None:
                pipe['current'] = current
            pipe['results'] = list(results)
            bank_jobs.set_pipeline(job, pipe)

        _sync()
        # Each entry closes with a status: 'done' | 'skipped' (reason) | 'error'.
        for i, step in enumerate(steps):
            if bank_jobs.cancelled(job):
                break
            _sync(current=step, index=i)
            bank_jobs.progress(job, done=0, total=0,
                               detail=f'step {i + 1}/{len(steps)}: {step}')
            entry = {'step': step, 'status': 'done', 'reason': None,
                     'detail': None, 'counts': {}}
            try:
                _run_pipeline_step(job, user_id, bank_id, step,
                                   reject_flags, resolve_dups, entry)
            except GpuBusyError as e:
                # A vision/training job grabbed the GPU mid-pipeline — skip this
                # pass and keep going (never wake the user for a transient clash).
                entry['status'] = 'skipped'
                entry['reason'] = f'GPU busy — {e}'
            except Exception as e:  # noqa: BLE001 — one bad pass never sinks the rest
                entry['status'] = 'error'
                entry['reason'] = f'{type(e).__name__}: {e}'
                db.session.rollback()
            # A step that executed stays 'done' even if a cancel landed at its
            # tail (its inner run already returned early); only steps we never
            # reach are recorded as cancelled, below.
            results.append(entry)
            _sync()

        cancelled = bank_jobs.cancelled(job)
        # Any step never reached (cancel, or a hard earlier break) is recorded so
        # the morning-after report has a row for every requested pass.
        reached = {e['step'] for e in results}
        for step in steps:
            if step not in reached:
                results.append({'step': step, 'status': 'cancelled' if cancelled
                                else 'skipped',
                                'reason': 'cancelled before it ran' if cancelled
                                else 'not reached', 'detail': None, 'counts': {}})
        _sync()

        report = {
            'started_at': job.get('started_at'),
            'finished_at': _time.time(),
            'cancelled': cancelled,
            'requested_steps': list(steps),
            'reject_flags': list(reject_flags),
            'resolve_dups': resolve_dups,
            'steps': results,
            'counts': _bank_counts(bank_id),
        }
        bank = db.session.get(ImageBank, bank_id)
        if bank is not None:
            bank.pipeline_report = _json.dumps(report)
            db.session.commit()
        done_n = sum(1 for e in results if e['status'] == 'done')
        skipped_n = sum(1 for e in results if e['status'] in ('skipped', 'cancelled'))
        err_n = sum(1 for e in results if e['status'] == 'error')
        tail = f'done — {done_n}/{len(steps)} steps ran'
        if skipped_n:
            tail += f', {skipped_n} skipped'
        if err_n:
            tail += f', {err_n} errored'
        if cancelled:
            tail = f'cancelled — {done_n}/{len(steps)} steps ran'
        bank_jobs.progress(job, detail=tail)
    return run


def _run_pipeline_step(job, user_id, bank_id, step, reject_flags, resolve_dups, entry):
    """Run ONE pipeline pass into ``entry``, reusing the standalone pass work.
    Prerequisite missing → entry marked 'skipped' with a reason, pipeline
    continues. Reuses each pass's inner ``run(job)`` so progress, cancellation
    and the GPU-exclusive window behave exactly as the standalone buttons."""
    if step == 'scan':
        _scan_job(bank_id, rescan=False)(job)
        c = _bank_counts(bank_id)
        entry['counts'] = {'scanned': c['scanned'], 'dup_groups': c['dup_groups']}
        entry['detail'] = (job.get('detail')
                           or f"scanned {c['scanned']}, {c['dup_groups']} duplicate group(s)")
        return
    if step == 'auto_reject':
        # ONE undo offer for the whole step, not one per sub-pass: the user fired
        # "Launch all", so the unit they would take back is the auto-reject, not
        # its second half. The later steps only ADD analysis columns, so undoing
        # this one leaves them consistent.
        snap = bank_undo.Snapshot('Launch all — auto-reject')
        rejected = (apply_flags(user_id, bank_id, reject_flags, snapshot=snap)
                    if reject_flags else {})
        dup_rejected = 0
        if resolve_dups:
            dup_rejected = resolve_dups_keep_best(user_id, bank_id, snapshot=snap)
        snap.commit(bank_id)
        n = sum(rejected.values()) + dup_rejected
        entry['counts'] = {'rejected': n, 'by_flag': rejected,
                           'duplicates': dup_rejected}
        parts = [f'{v} {k}' for k, v in rejected.items() if v]
        if dup_rejected:
            parts.append(f'{dup_rejected} duplicate')
        entry['detail'] = (f"rejected {n} image(s)"
                           + (f" ({', '.join(parts)})" if parts else '')
                           + ' — manual ✓/✕ untouched')
        return
    if step == 'score':
        reason = _score_prereq() or _gpu_busy_reason()
        if reason:
            entry['status'], entry['reason'] = 'skipped', reason
            return
        _score_job(bank_id)(job)
        c = _bank_counts(bank_id)
        entry['counts'] = {'scored': c['scored'], 'style_groups': c['style_groups']}
        entry['detail'] = job.get('detail') or f"scored {c['scored']} image(s)"
        return
    if step == 'semantic_dedup':
        # Runs right after Score, reusing its cached embeddings (no GPU). Groups
        # crops/variants for review; resolution stays a UI action (keep best/first
        # /manual) — near-dups are fuzzier than exact dHash, so the overnight run
        # surfaces them rather than auto-rejecting. Skipped-with-reason (never a
        # mute ✗) when Score produced no embeddings.
        n = rebuild_semantic_dup_groups(bank_id)
        if n is None:
            entry['status'], entry['reason'] = 'skipped', 'run ✨ Score first — no embeddings'
            return
        entry['counts'] = {'semantic_groups': n}
        entry['detail'] = f'{n} semantic near-duplicate group(s) to review'
        return
    if step == 'watermark':
        reason = _watermark_prereq() or _gpu_busy_reason()
        if reason:
            entry['status'], entry['reason'] = 'skipped', reason
            return
        _watermark_job(bank_id, rescan=False)(job)
        c = _bank_counts(bank_id)
        entry['counts'] = {'watermarks': c['watermark_detected']}
        entry['detail'] = job.get('detail') or f"{c['watermark_detected']} with a watermark"
        return
    if step == 'faces':
        reason = _faces_prereq()
        if reason:
            entry['status'], entry['reason'] = 'skipped', reason
            return
        _faces_job(bank_id)(job)
        c = _bank_counts(bank_id)
        entry['counts'] = {'person_groups': c['person_groups']}
        entry['detail'] = job.get('detail') or f"{c['person_groups']} person cluster(s)"
        return
    if step == 'framing':
        reason = _framing_prereq() or _gpu_busy_reason()
        if reason:
            entry['status'], entry['reason'] = 'skipped', reason
            return
        _framing_job(bank_id, rescan=False)(job)
        c = _bank_counts(bank_id)
        entry['counts'] = {'framing_classified': c['framing_classified']}
        entry['detail'] = job.get('detail') or f"{c['framing_classified']} classified by framing"
        return
    if step == 'caption':
        reason = _caption_prereq() or _gpu_busy_reason()
        if reason:
            entry['status'], entry['reason'] = 'skipped', reason
            return
        before = _bank_counts(bank_id)['captioned']
        _caption_job(bank_id, None, False)(job)
        after = _bank_counts(bank_id)['captioned']
        entry['counts'] = {'captioned': max(0, after - before), 'total_captioned': after}
        entry['detail'] = job.get('detail') or f"{after} captioned"
        return
    entry['status'], entry['reason'] = 'skipped', 'unknown step'


def resolve_dups_keep_best(user_id, bank_id, snapshot=None) -> int:
    """Auto-resolve every unresolved duplicate group keeping the best member,
    for the pipeline's auto-reject step. Returns the number REJECTED."""
    out = resolve_dups(user_id, bank_id, strategy='best', snapshot=snapshot)
    return out.get('rejected', 0)


# --- subfolders (scoping facet) ---------------------------------------------
def subfolders_payload(user_id, bank_id) -> dict | None:
    """Top-level subfolders of the bank's source folder with image counts, for
    the scoping picker. Computed once on open (not polled) — a Telegram export
    nests one folder per chat/date. '' = files at the bank root."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    from collections import Counter
    counts: Counter = Counter()
    for (rel,) in (db.session.query(BankImage.relpath)
                   .filter(BankImage.bank_id == bank_id).all()):
        counts[_subfolder_of(rel)] += 1
    items = [{'name': name, 'count': n}
             for name, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {'subfolders': items, 'total': sum(counts.values())}


# --- coverage advice (idea by @antonp) --------------------------------------
# A read-only ADVICE panel: from what you'd actually train on (the kept set, or
# every non-rejected image before anything is kept), it says what leans and what
# is thin for a good LoRA — purely from data the passes already computed (framing,
# person clusters, style clusters, resolution). It NEVER selects or rejects; it
# only phrases honest, non-alarmist sentences. Everything here is pure DB math,
# zero GPU — the framing part just needs the 📐 Framing pass to have run.
def _pct(n, total) -> int:
    return int(round(100 * n / total)) if total else 0


# --- visual spread, from the embeddings the ✨ Score pass already cached -------
# The framing/cluster numbers above are labels; they cannot see that two hundred
# images labelled "body" are the same body in the same pose. The CLIP embeddings
# can, and they are already on disk — so this costs one pass over vectors that
# were computed for other reasons, and nothing new runs.
#
# The statistic is the MEAN PAIRWISE COSINE SIMILARITY of the pool. For L2-normed
# vectors it has a closed form that avoids ever building the n×n matrix:
#
#     sum_{i,j} e_i . e_j  ==  || sum_i e_i ||^2
#
# so the mean over off-diagonal pairs is (||s||^2 - n) / (n^2 - n) — one pass,
# O(n·d), exact, and it does not care how big the bank is. That matters: the
# panel is read-only and opened casually, so it must not become the reason a
# 47k-image bank stalls.
#
# THRESHOLDS ARE MEASURED, NOT GUESSED. Taken on the two real banks available
# (117 and 46 775 usable embeddings — deliberately different in size and
# content):
#     whole pool                    0.645   and  0.650
#     random subsets n=20…1000      0.643 … 0.692   (i.e. NOT a function of n)
#     an image + its nearest nbrs   0.788   and  0.900   <- redundant extreme
#     a farthest-point sample       0.538   and  0.220   <- varied extreme
# So ~0.65 is what an ordinary bank looks like, a genuinely repetitive selection
# lands around 0.79-0.90, and the statistic is stable across pool size — which is
# why no n-correction is applied. The bands below sit clear of the ordinary
# reading so a normal bank is never nagged.
_SPREAD_REDUNDANT = 0.80     # at/above: measured territory of nearest-neighbour sets
_SPREAD_LEANING = 0.72       # at/above: tighter than either real bank's whole pool
_SPREAD_MIN_POOL = 10        # under this the mean is noise, so we decline to judge


def _coverage_embeddings(bank, crit):
    """The (m×d) L2-normed embedding matrix for the coverage pool.

    A sibling of ``_pool_embeddings`` rather than a call into it: that one takes
    the curation FILTER dict and goes through ``_pool_query``, which has no way to
    express the coverage pool's "everything not rejected" fallback. Same path
    resolution, same fast-path reasoning — see ``_pool_embeddings``.
    """
    import numpy as np
    emb_by_path = _load_score_embeddings(bank)
    if not emb_by_path:
        return None
    rows = (BankImage.query.filter(BankImage.bank_id == bank.id, crit)
            .order_by(BankImage.id.asc()).all())
    base = os.path.realpath(bank.source_path)
    prefix = os.path.normcase(base + os.sep)
    vecs = []
    for r in rows:
        p = os.path.normpath(os.path.join(base, r.relpath))
        emb = emb_by_path.get(p) if os.path.normcase(p).startswith(prefix) else None
        if emb is None:
            p = _abs_under(base, r.relpath)
            emb = emb_by_path.get(p) if p else None
        if emb is not None:
            vecs.append(emb)
    if not vecs:
        return None
    E = np.stack(vecs).astype('float32')
    E /= (np.linalg.norm(E, axis=1, keepdims=True) + 1e-8)
    return E


def _visual_spread(bank, crit) -> dict:
    """How alike the pool LOOKS, from the cached CLIP embeddings.

    Returns ``{'scored': m, 'similarity': float|None, 'band': str}`` where band is
    'redundant' | 'leaning' | 'varied' | 'unknown'. 'unknown' with scored 0 means
    the ✨ Score pass has not run (or its cache went stale) — the panel says so
    rather than drawing a bar it did not measure.
    """
    out = {'scored': 0, 'similarity': None, 'band': 'unknown'}
    try:
        E = _coverage_embeddings(bank, crit)
    except Exception:
        # A read-only advisory must never be the thing that breaks the panel:
        # a corrupt or half-written cache degrades to "not measured".
        return out
    if E is None or len(E) < 2:
        out['scored'] = 0 if E is None else len(E)
        return out
    n = len(E)
    out['scored'] = n
    if n < _SPREAD_MIN_POOL:
        return out
    s = E.sum(axis=0, dtype='float64')
    sim = (float(s @ s) - n) / (n * n - n)
    sim = max(-1.0, min(1.0, sim))
    out['similarity'] = round(sim, 4)
    out['band'] = ('redundant' if sim >= _SPREAD_REDUNDANT
                   else 'leaning' if sim >= _SPREAD_LEANING else 'varied')
    return out


def _coverage_pool_crit(bank_id):
    """The pool the panel describes: the KEPT images, or — before anything is
    kept — every non-rejected one (so the panel is useful from the first look).

    Extracted so the caption and embedding reads share ONE definition with the
    label counts instead of each re-deriving it and drifting. It is returned by a
    function rather than smuggled out inside the stats dict: that dict gets
    jsonify()'d, and an SQLAlchemy criterion in it is a 500 waiting for whoever
    forgets to strip it.
    """
    kept_n = BankImage.query.filter_by(bank_id=bank_id, status='keep').count()
    return ((BankImage.status == 'keep') if kept_n > 0
            else (BankImage.status != 'reject'))


def _coverage_stats(bank_id) -> dict:
    """Everything the coverage panel needs, from the pool the user would train on.
    Pure aggregate SQL, no GPU. Every value here is JSON-serialisable."""
    base = BankImage.query.filter_by(bank_id=bank_id)
    crit = _coverage_pool_crit(bank_id)
    pool_is_kept = base.filter_by(status='keep').count() > 0
    pool = base.filter(crit)
    total = pool.count()

    framing = _framing_counts(bank_id, extra_crit=crit)
    framing_known = sum(framing[k] for k in _FRAMINGS)
    framing_available = framing_known + framing['unknown'] > 0

    # Person clusters within the pool, biggest first (list of sizes).
    person_rows = (db.session.query(BankImage.face_cluster, func.count(BankImage.id))
                   .filter(BankImage.bank_id == bank_id, crit,
                           BankImage.face_cluster.isnot(None))
                   .group_by(BankImage.face_cluster)
                   .order_by(func.count(BankImage.id).desc()).all())
    person_sizes = [int(n) for _c, n in person_rows]
    style_rows = (db.session.query(BankImage.style_cluster, func.count(BankImage.id))
                  .filter(BankImage.bank_id == bank_id, crit,
                          BankImage.style_cluster.isnot(None))
                  .group_by(BankImage.style_cluster)
                  .order_by(func.count(BankImage.id).desc()).all())
    style_sizes = [int(n) for _c, n in style_rows]
    top_person_id = int(person_rows[0][0]) if person_rows else None

    # Resolution: how much of the pool is small (< 1 MP), where low-res caps detail.
    res_scanned = pool.filter(BankImage.width.isnot(None),
                              BankImage.height.isnot(None)).count()
    under_1mp = pool.filter(BankImage.width.isnot(None), BankImage.height.isnot(None),
                            BankImage.width * BankImage.height < 1_000_000).count()

    return {
        'pool': 'kept' if pool_is_kept else 'candidates',
        'total': total,
        'framing': framing, 'framing_known': framing_known,
        'framing_available': framing_available,
        'person': {'clusters': person_sizes, 'top_id': top_person_id,
                   'total': sum(person_sizes),
                   'singletons': sum(1 for n in person_sizes if n == 1)},
        'style': {'clusters': style_sizes, 'total': sum(style_sizes)},
        'resolution': {'scanned': res_scanned, 'under_1mp': under_1mp},
    }


def _coverage_advice(stats: dict) -> list:
    """Turn the coverage stats into a short list of honest, actionable sentences.
    Each is {'tone': 'warn'|'info', 'text': ...}. Pure function of ``stats`` (unit
    of the logic — deterministic on a known distribution). Never alarmist: a
    dominance reads as a QUESTION, a thin axis as a gentle 'add a few'."""
    total = stats['total']
    pool = stats['pool']
    noun = 'kept' if pool == 'kept' else 'candidate'
    out = []
    if total == 0:
        return [{'tone': 'info',
                 'text': 'Nothing to advise on yet — keep some images (or run a '
                         'pass) and the coverage read appears here.'}]

    # Size — most families want a couple dozen.
    if total < 20:
        out.append({'tone': 'warn',
                    'text': f'Only {total} {noun} — most LoRA families train more '
                            f'reliably with 20+ images.'})

    # Framing balance (needs the 📐 Framing pass).
    fr, known = stats['framing'], stats['framing_known']
    if not stats['framing_available']:
        out.append({'tone': 'info',
                    'text': 'Run the 📐 Framing pass to see how your face / bust / '
                            'body / back shots balance.'})
    elif known > 0:
        dom = max(_FRAMINGS, key=lambda k: fr[k])
        dom_share = fr[dom] / known
        thin = [k for k in _FRAMINGS if _pct(fr[k], known) < 10]
        if dom_share >= 0.55 and total >= 8:
            add = ' / '.join(k for k in ('body', 'back', 'bust', 'face')
                             if k in thin) or 'other angles'
            out.append({'tone': 'warn',
                        'text': f'{_pct(fr[dom], known)}% {dom} shots — add '
                                f'{add} for a fuller character.'})
        elif fr['back'] == 0 and known >= 10:
            out.append({'tone': 'info',
                        'text': 'No back views — a few help a character hold up '
                                'from behind (optional).'})

    # Person mix — a dominance is a question, not a verdict.
    ppl = stats['person']
    if ppl['total'] > 0 and ppl['clusters']:
        top = ppl['clusters'][0]
        if len(ppl['clusters']) >= 2 and top / ppl['total'] >= 0.5:
            out.append({'tone': 'info',
                        'text': f'Person #{ppl["top_id"]} is {_pct(top, ppl["total"])}% '
                                f'of the set — is this one subject, or a mix?'})
        if ppl['singletons'] >= 3 and total >= 10:
            out.append({'tone': 'info',
                        'text': f'{ppl["singletons"]} people appear only once — a '
                                f'character LoRA wants one consistent subject.'})

    # Style spread — only when it's genuinely mixed (no single dominant style).
    st = stats['style']
    if len(st['clusters']) >= 2 and st['total'] > 0 \
            and st['clusters'][0] / st['total'] < 0.7 and total >= 8:
        out.append({'tone': 'info',
                    'text': f'{len(st["clusters"])} visual styles in the set — '
                            f'mixing photoreal and illustration can dilute a LoRA.'})

    # Resolution — low-res caps the training resolution.
    res = stats['resolution']
    if res['scanned'] > 0:
        share = res['under_1mp'] / res['scanned']
        if share >= 0.3:
            out.append({'tone': 'info',
                        'text': f'{_pct(res["under_1mp"], res["scanned"])}% are under '
                                f'1 MP — low-res images cap the detail a LoRA can learn.'})

    if not out:
        out.append({'tone': 'info',
                    'text': 'Nothing stands out — your set looks reasonably balanced.'})
    # Warnings first so the panel reads worst-to-mildest.
    out.sort(key=lambda a: 0 if a['tone'] == 'warn' else 1)
    return out


def _spread_advice(spread, total) -> list:
    """The visual-spread sentence, or nothing. Pure function of the measurement.

    Deliberately quiet: a bank in the ordinary band says NOTHING, because a panel
    that comments on every axis every time trains people to skim it.
    """
    if total < _SPREAD_MIN_POOL:
        return []
    if not spread['scored']:
        return [{'tone': 'info',
                 'text': 'Run ✨ Score to also see how varied the set LOOKS — the '
                         'labels above cannot tell two hundred near-identical shots '
                         'from two hundred different ones.'}]
    if spread['similarity'] is None:
        return []
    pct = int(round(100 * spread['similarity']))
    if spread['band'] == 'redundant':
        return [{'tone': 'warn',
                 'text': f'The images look very alike ({pct}% average similarity) — '
                         f'a set this repetitive teaches one look. Use ⚖️ or the '
                         f'diverse pick to spread it out.'}]
    if spread['band'] == 'leaning':
        return [{'tone': 'info',
                 'text': f'The images lean alike ({pct}% average similarity) — '
                         f'workable, but more variety would generalise better.'}]
    return []


# The bank has no `kind` (character/concept/style) — that lives on datasets only.
# It is judged as a CHARACTER source rather than offered as a choice, because the
# rest of this panel already is: the framing target it phrases against is the
# character 12/6/6/1 mix, the person-cluster advice says "a character LoRA wants
# one consistent subject", and the style-cluster advice treats a style mix as
# dilution. Adding a selector here would make one axis kind-aware inside a panel
# whose every other axis assumes a character, and would introduce a stored
# preference (with the alias obligations that carry) to fix an inconsistency this
# panel does not otherwise have. The UI says which lens it is using instead of
# leaving the user to infer it.
_COVERAGE_KIND = 'character'


def coverage(user_id, bank_id) -> dict | None:
    """The read-only coverage advice for the bank (idea by @antonp). Returns the
    distributions the panel renders plus the generated advice, or None if the bank
    is gone. Never mutates.

    Three sources, all already computed by earlier passes: the labels (framing,
    person/style clusters, resolution), the CAPTIONS from the 🏷️ pass — scanned by
    the shared `caption_coverage` lexicon, the same one the dataset panel uses, so
    the two never drift — and the CLIP embeddings from ✨ Score, for whether the
    pool actually LOOKS varied. No model runs.
    """
    from . import caption_coverage

    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    stats = _coverage_stats(bank_id)
    crit = _coverage_pool_crit(bank_id)

    captions = [c for (c,) in db.session.query(BankImage.caption)
                .filter(BankImage.bank_id == bank_id, crit).all()]
    variety = caption_coverage.analyse(captions, kind=_COVERAGE_KIND)
    spread = _visual_spread(bank, crit)
    # Nested, because `analyse` returns its own `total`/`axes` and the bank payload
    # already owns `total` — flattening would silently overwrite the pool size.
    stats['variety'] = variety
    stats['visual'] = spread

    advice = _coverage_advice(stats)
    if stats['total']:
        # On an empty pool _coverage_advice already says the one true thing
        # ("nothing to advise on yet"); the other two sources would each add their
        # own phrasing of the same emptiness.
        advice += _spread_advice(spread, stats['total'])
        advice += caption_coverage.advice(variety)
    # One list, warnings first — the panel reads worst-to-mildest across all three
    # sources rather than as three separate verdicts the user has to merge.
    advice.sort(key=lambda a: 0 if a['tone'] == 'warn' else 1)
    stats['advice'] = advice
    return stats


# --- promotion --------------------------------------------------------------
def _promoted_here(dataset_id):
    """The bank_image ids the dataset STILL holds — one row per promoted image,
    written by the promotion itself (FaceDatasetImage.bank_image_id). Deleting
    the image in the dataset deletes the row, so this shrinks on its own."""
    return (db.session.query(FaceDatasetImage.bank_image_id)
            .filter(FaceDatasetImage.dataset_id == dataset_id,
                    FaceDatasetImage.bank_image_id.isnot(None)))


def _not_already_on(dataset_id):
    """The criterion 'this kept image is not already sitting on that dataset'.

    Measured, not remembered: an image counts as already there only while the
    dataset really holds a row pointing back at it. Delete that image in the
    dataset and the bank offers it again — the old one-way promoted_dataset_id
    flag never came back, so a bank could end up advertising nothing promotable
    into a dataset it had no image left in, which reads as "the bank lost my
    images".

    promoted_dataset_id survives as the LEGACY answer, for images promoted
    before the back-link existed: nothing writes it any more (a promotion clears
    it as it records the link), so it can only ever describe a pre-upgrade
    promotion, and it is dropped for good the next time that image is promoted.
    """
    return and_(BankImage.id.notin_(_promoted_here(dataset_id)),
                or_(BankImage.promoted_dataset_id.is_(None),
                    BankImage.promoted_dataset_id != dataset_id))


def _promotable_query(bank_id, dataset_id):
    """The KEPT images eligible to promote into ``dataset_id``. Per-target, not a
    global 'promoted anywhere' lock — an image promoted to dataset A stays
    promotable to B. (The dataset-side perceptual dedup on import is the real
    guard against genuine duplicates.)"""
    return (BankImage.query.filter_by(bank_id=bank_id, status='keep')
            .filter(_not_already_on(dataset_id)))


def promotable_count(user_id, bank_id, dataset_id) -> int | None:
    """How many kept images the 'promote all' path would send to ``dataset_id``
    right now — the honest number behind the modal's copy line. None = bank or
    dataset gone."""
    if not get_bank(user_id, bank_id):
        return None
    if not FaceDataset.query.filter_by(id=dataset_id, user_id=user_id).first():
        return None
    return _promotable_query(bank_id, dataset_id).count()


_IMPORT_FOLDER_SAFE = re.compile(r'[^A-Za-z0-9 _-]')


def _import_folder_for(name: str) -> str:
    """A fresh, unused folder under bank_sources_root for an imported bank.
    Suffixes -2, -3… rather than reusing a folder: two imports of the same name
    must never end up sharing (and silently merging) one set of files."""
    stem = _IMPORT_FOLDER_SAFE.sub('_', name).strip() or 'bank'
    root = cfg.bank_sources_root()
    candidate = root / stem
    i = 2
    while candidate.exists():
        candidate = root / f'{stem}-{i}'
        i += 1
    return str(candidate)


def _scrape_blob_name(raw: bytes) -> str | None:
    """The filename a downloaded blob gets in a bank folder: its own content
    hash. Two consequences, both wanted:

    * a resume that re-downloads the SAME bytes writes the same name, so it
      overwrites itself instead of piling up `photo (2).jpg` — idempotent without
      anyone having to decide what a duplicate is;
    * that is file IDENTITY, not curation. Near-duplicates (a re-encode, a crop,
      the same shot at another size) keep separate names and reach the bank, where
      the duplicate-group pass and the semantic pass are the ONE place that rules
      on them. The dataset outlet's dHash gate deliberately does not run here —
      two different definitions of "duplicate" over one pile is the failure mode
      this whole path exists to avoid.

    None when the bytes are not a raster image we store."""
    if (not isinstance(raw, (bytes, bytearray)) or not raw
            or len(raw) > BANK_SOURCE_MAX_BYTES):
        return None
    try:
        # Same static-content + frame + header + full-decode validator as Dataset
        # preserve import. A scraped blob is later scanned from the live Bank
        # folder, so accepting it here would otherwise create a new bomb ingress.
        ext = _preserved_import_extension(raw, label='bank scrape')
    except (ValueError, MemoryError):
        return None
    return f'{hashlib.sha256(raw).hexdigest()[:24]}{ext}'


def scrape_import_to_bank(user_id, items, bank_id=None, name=None) -> dict:
    """🕸 Scrape → BANK: the scraper's second destination.

    Downloads the SELECTED scanned images ({'url','title'}) into a bank's source
    FOLDER, then lets the ordinary folder walk inventory them. Two modes:
    ``bank_id`` appends to an existing bank (resume — a bank points at a live
    folder, so a second scrape simply adds to the pile it already holds), while
    ``name`` creates a new bank under ``bank_sources_root()`` exactly like
    "Import to bank" does.

    Deliberately does NOT reuse `scrape_import_urls`: that path is a DATASET
    intake and rightly refuses what cannot be trained on (side < 768 px, ratio
    > 3:1) and what it judges a perceptual duplicate. A bank is the step BEFORE
    that judgement — "too small" and "near-duplicate" are verdicts its own passes
    produce, with thresholds the user moves. Filtering at download time would
    delete the evidence before the triage tool ever sees it. What IS kept from
    that path is the download itself (`_download_scrape_item`: SSRF guard,
    content-type allow-list, image-magic check, size cap) and the per-request cap.

    Returns {'bank_id', 'name', 'created', 'saved', 'already_there', 'added',
    'skipped': {...}}. ``added`` is what the folder walk actually inventoried.
    Raises ValueError (bad input) or BankJobBusy (a pass owns the bank)."""
    items = [it for it in (items or []) if isinstance(it, dict) and it.get('url')]
    if not items:
        raise ValueError('no items')
    if len(items) > SCRAPE_IMPORT_MAX:
        raise ValueError(f'max {SCRAPE_IMPORT_MAX} images per import')

    created = False
    if bank_id is not None:
        bank = get_bank(user_id, bank_id)
        if bank is None:
            raise ValueError('bank not found')
        # A live pass works off a snapshot of this bank's rows and reports against
        # a fixed total; refresh_bank also declines to walk underneath it. Adding
        # files now would land outside both — refuse in the shape the UI knows.
        if bank_jobs.running(bank.id):
            # The snapshot can vanish between the two reads (a job that finishes
            # right here); the refusal must still name something.
            snap = bank_jobs.get(bank.id) or {}
            raise bank_jobs.BankJobBusy(snap.get('kind') or 'background')
        folder = bank.source_path
        if not folder or not os.path.isdir(folder):
            raise ValueError('this bank\'s folder is unavailable — relocate it first')
        # Appending here WRITES into the bank's folder. On a legacy bank sitting
        # on a dataset that means downloading scraped files straight into the
        # dataset's training images — not destructive, but exactly the sharing
        # this guard exists to end.
        conflict = path_guard.dataset_folder_conflict(folder)
        if conflict:
            raise ValueError(
                'This bank points at a dataset\'s own image folder, so scraping '
                f'into it would drop files inside the dataset. {conflict["message"]}')
    else:
        name = (name or '').strip()
        if not name:
            raise ValueError('name is required')
        folder = _import_folder_for(name)
        os.makedirs(folder, exist_ok=True)
        bank = ImageBank(user_id=user_id, name=name, source_path=folder)
        db.session.add(bank)
        db.session.commit()
        created = True

    with ThreadPoolExecutor(max_workers=_SCRAPE_DL_WORKERS) as pool:
        downloaded = list(pool.map(_download_scrape_item, items))

    skipped: dict[str, int] = {}
    saved = already_there = 0
    for reason, raw in downloaded:
        if reason != 'ok' or not raw:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        blob_name = _scrape_blob_name(raw)
        if blob_name is None:
            skipped['not_image'] = skipped.get('not_image', 0) + 1
            continue
        dest = os.path.join(folder, blob_name)
        if os.path.exists(dest):
            already_there += 1
            continue
        try:
            with open(dest, 'wb') as fh:
                fh.write(raw)
        except OSError:
            logger.warning('bank scrape: could not write %s', blob_name, exc_info=True)
            skipped['errors'] = skipped.get('errors', 0) + 1
            continue
        saved += 1

    # ONE inventory path for every bank: the same walk that picks up files the
    # user drops in the folder by hand picks these up too. No third insert path.
    sync = refresh_bank(user_id, bank.id, force=True) or {}
    return {'bank_id': bank.id, 'name': bank.name, 'created': created,
            'saved': saved, 'already_there': already_there,
            'added': sync.get('added', 0), 'skipped': skipped}


_BANK_TRANSFER_WATERMARK_STATES = frozenset(
    ('none', 'detected', 'dismissed', 'cleaned', 'failed', 'error'))
_BANK_TRANSFER_FRAMINGS = frozenset(('face', 'bust', 'body', 'back', 'unknown'))
_BANK_TRANSFER_STATUSES = frozenset(('pending', 'keep', 'reject'))


def _copied_image_dimensions(path) -> tuple[int | None, int | None]:
    """Read destination dimensions without letting a Pillow bomb sink promotion."""
    try:
        with safe_bank_source(path, label='bank import') as im:
            return im.size
    except (Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, TypeError, ValueError, MemoryError):
        return None, None


def _dataset_row_bank_values(row: FaceDatasetImage, copied_path, preserve_analysis: bool) -> dict:
    """The current user-facing Dataset data, plus a compatible old Bank analysis.

    The snapshot never gets to overwrite caption/framing/watermark/provenance or
    curation: those fields are the user's present Dataset choices.  It only adds
    final-WebP measurements when the just-copied bytes still equal the promotion
    fingerprint.  This is deliberately checked against ``copied_path`` after the
    copy, closing the tiny edit-during-copy race as well.
    """
    values = {
        'caption': row.caption,
        # WHO wrote that caption travels with it. This is THE path that used to
        # destroy hand-written work: a caption typed in the Dataset editor landed
        # in the Bank as an anonymous string, and the Bank's forced pass had no
        # way left to tell it from one of its own.
        'caption_origin': row.caption_origin,
        'framing': row.framing if row.framing in _BANK_TRANSFER_FRAMINGS else None,
        'watermark_state': (row.watermark_state
                            if row.watermark_state in _BANK_TRANSFER_WATERMARK_STATES
                            else None),
        'watermark_bbox': row.watermark_bbox if isinstance(row.watermark_bbox, str) else None,
        'watermark_regions': (row.watermark_regions
                              if isinstance(row.watermark_regions, str) else None),
        'source_metadata': _source_metadata_storage(row.source_metadata),
        # Dataset-to-Bank only starts from kept rows.  Keep the current explicit
        # decision should it change while the background copy is waiting, but do
        # not invent a Bank-only 'failed' status for a Dataset failure row.
        'status': (row.status if row.status in _BANK_TRANSFER_STATUSES else 'keep'),
        'watermark_clean_method': None,
        # A Bank rotation has already been materialised into the Dataset pixels
        # during promotion.  Restoring it here would turn the copied file twice.
        'rotation': None,
    }
    values['width'], values['height'] = _copied_image_dimensions(copied_path)
    if preserve_analysis:
        analysis = bank_transfer_metadata.compatible_analysis(
            row.bank_analysis_snapshot, copied_path)
        if analysis:
            values.update(analysis)
        elif row.bank_analysis_snapshot is not None:
            # A Dataset byte edit (or a rejected legacy payload) must not keep
            # looking transferable forever.  The compatibility check above is
            # against the just-copied bytes, so clearing here is race-safe.
            row.bank_analysis_snapshot = None
    return values


def start_dataset_import(app, user_id, dataset_id, name, preserve_analysis=True):
    """The REVERSE of promote: turn a dataset back into a bank. Copies the
    dataset's KEPT images into a folder of their own and registers it as a bank
    under `name`, so the dataset's material can be re-triaged with the bank tools
    (perceptual + semantic dedup, framing, scores) without disturbing it.  By
    default the compatible Bank analysis saved on each Dataset image is restored;
    ``preserve_analysis=False`` instead starts a fresh unanalysed Bank while
    still carrying the Dataset's current captions, framing, watermark metadata,
    source attribution and curation decision.

    COPIES rather than pointing the bank at the dataset's live folder: the two
    would otherwise share files, and curating one would mutate the other. That
    mirrors promote, which copies in the other direction — each side owns its
    images. Kept images only, again mirroring promote (which only ever carries
    kept ones across).

    Background job: hundreds of files is a slow copy, and the bank page already
    renders bank_jobs progress. The bank row is created FIRST (empty) so the job
    has a bank_id to report against; a job that dies part-way leaves a bank
    holding exactly the images it managed to copy, never a phantom row.
    Raises ValueError (-> 400) on a missing dataset, a blank name, invalid
    preservation mode, or nothing kept."""
    from .dataset_storage import dataset_path
    if not isinstance(preserve_analysis, bool):
        raise ValueError('preserve_analysis must be a boolean')
    name = (name or '').strip()
    if not name:
        raise ValueError('name is required')
    ds = FaceDataset.query.filter_by(id=dataset_id, user_id=user_id).first()
    if not ds:
        raise ValueError('dataset not found')
    rows = (FaceDatasetImage.query
            .filter_by(dataset_id=dataset_id, status='keep')
            .filter(FaceDatasetImage.filename.isnot(None))
            .order_by(FaceDatasetImage.id.asc()).all())
    if not rows:
        raise ValueError('nothing to import — keep some images first')
    if len(rows) > BANK_MAX_FILES:
        raise ValueError(f'too many images (max {BANK_MAX_FILES})')
    folder = _import_folder_for(name)
    os.makedirs(folder, exist_ok=True)
    bank = ImageBank(user_id=user_id, name=name, source_path=folder)
    db.session.add(bank)
    db.session.commit()
    src_dir = str(dataset_path(dataset_id))
    bank_jobs.start(
        app, bank.id, 'dataset_import',
        _dataset_import_job(bank.id, src_dir,
                            [(r.id, r.filename) for r in rows], preserve_analysis),
        total=len(rows))
    return bank.id


def _dataset_import_job(bank_id, src_dir, image_rows, preserve_analysis=True):
    def run(job):
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        copied = missing = failed = 0
        for i, (image_id, fallback_fn) in enumerate(image_rows, 1):
            if bank_jobs.cancelled(job):
                break
            # Re-read the row for its latest user-authored choices.  The list of
            # ids still fixes the *selection* at click time, matching the old
            # filename-only job; a deleted legacy row degrades to a plain copy.
            row = db.session.get(FaceDatasetImage, image_id)
            fn = row.filename if row and row.filename else fallback_fn
            src = os.path.join(src_dir, fn)
            if not os.path.isfile(src):
                missing += 1
                bank_jobs.bump(job)
                continue
            dest = os.path.join(bank.source_path, fn)
            try:
                # Dataset folders can contain legacy/manual files outside the
                # current import path. Revalidate the exact bytes before they
                # become a live Bank source instead of trusting an old row.
                payload = _read_safe_bank_source_bytes(
                    src, label='dataset-to-bank import')
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest, 'wb') as destination:
                    destination.write(payload)
                size = os.path.getsize(dest)
            except (OSError, TypeError, ValueError, MemoryError,
                    Image.DecompressionBombError, Image.DecompressionBombWarning):
                # One unreadable/locked file never sinks the whole import — the
                # bank just ends up with the rest, and the detail line says so.
                logger.warning('dataset import: copy %s failed', fn, exc_info=True)
                failed += 1
                bank_jobs.bump(job)
                continue
            values = (_dataset_row_bank_values(row, dest, preserve_analysis)
                      if row is not None else {'status': 'keep'})
            db.session.add(BankImage(bank_id=bank_id, relpath=fn, file_size=size,
                                     **values))
            copied += 1
            if i % 200 == 0:
                db.session.commit()
            bank_jobs.bump(job)
        db.session.commit()
        detail = f'{copied} image(s) imported'
        if missing:
            detail += f', {missing} missing on disk'
        if failed:
            detail += f', {failed} failed'
        bank_jobs.progress(job, detail=detail)
    return run


# --- ⬆ Promote, second destination: a NEW BANK -------------------------------
# Promotion used to lead exactly one place: a dataset. A dataset is the strict,
# training-bound container — isolating 200 candidates out of a 9 000-image dump
# to keep working on them is a different intent, and forcing it through a dataset
# commits material the user has not decided on yet.
#
# Built on the SAME machinery as "Import to bank" (start_dataset_import): a name,
# a folder of its own under bank_sources_root, a background job, and the new
# bank's id back so the UI can jump to it. What is deliberately NOT reused is
# hardlinking: run_archive.py already settled that question for this app — the
# app rewrites images IN PLACE (re-crop, "Reset to auto", watermark cleaning) and
# an in-place rewrite reuses the inode, so two "independent" banks would become
# one at the first edit. Banks never share their files. It costs the bytes.
def _promote_source_rows(bank_id, ids) -> list:
    """The rows a promotion would carry: the explicit selection, or every KEPT
    image when the selection is empty (same rule as promoting to a dataset).

    Ordered by relpath so the copy, the count and the size preview all describe
    the same set in the same order."""
    if ids:
        wanted = [int(i) for i in ids]
        rows = []
        for i0 in range(0, len(wanted), _SQL_IN_CHUNK):
            rows.extend(BankImage.query.filter(
                BankImage.bank_id == bank_id,
                BankImage.id.in_(wanted[i0:i0 + _SQL_IN_CHUNK])).all())
    else:
        rows = BankImage.query.filter_by(bank_id=bank_id, status='keep').all()
    rows.sort(key=lambda r: r.relpath)
    return rows


def selection_size(user_id, bank_id, ids) -> dict | None:
    """{'count', 'bytes'} for what a promotion would COPY — the honest weight the
    confirmation shows BEFORE the click.

    Real bytes, not an order of magnitude: today's images average ~300 KB, so
    200 of them are ~60 MB and nobody needs warning; a video bank is three orders
    of magnitude above that and the same dialog must not lie about it. Reads the
    size the scan already recorded (one column, no disk hit), and only stats the
    watermark-CLEANED blobs, which are what a promotion actually copies for those
    rows and whose size the column does not describe. None = bank gone."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        return None
    rows = _promote_source_rows(bank_id, ids)
    total = 0
    for r in rows:
        if r.watermark_clean_method:
            try:
                total += os.path.getsize(resolved_image_path(bank, r))
                continue
            except (OSError, TypeError):
                pass            # fall back to the recorded source size
        total += int(r.file_size or 0)
    return {'count': len(rows), 'bytes': total}


def start_bank_promote(app, user_id, bank_id, ids, name):
    """Copy a selection into a BRAND NEW bank named ``name``. 202 + background
    job, like every other pass; returns the new bank's id so the UI can jump to
    the bank being filled.

    The job is registered against the SOURCE bank — that is the bank the user is
    looking at, the one whose rows get marked, and the one a concurrent scan
    would race. So an already-busy source bank is the established 409, and the
    progress bar appears where the user clicked.

    Raises ValueError (-> 400) on a missing bank, a blank name or an empty
    selection, BankJobBusy (-> 409) while another pass runs on the source."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    name = (name or '').strip()
    if not name:
        raise ValueError('name is required')
    rows = _promote_source_rows(bank_id, ids)
    if not rows:
        raise ValueError('nothing to promote — keep or select some images first')
    if len(rows) > BANK_MAX_FILES:
        raise ValueError(f'too many images (max {BANK_MAX_FILES})')
    # Checked BEFORE anything is created: bank_jobs.start would raise the same
    # 409 a moment later, having already left a folder and a row behind.
    if bank_jobs.running(bank_id):
        # ``running()`` gets a snapshot internally; a finished job can expire
        # between that read and this one.  Preserve the established 409 instead
        # of turning a harmless TTL race into a server error.
        snap = bank_jobs.get(bank_id) or {}
        raise bank_jobs.BankJobBusy(snap.get('kind') or 'background')
    folder = _import_folder_for(name)
    os.makedirs(folder, exist_ok=True)
    dest = ImageBank(user_id=user_id, name=name, source_path=folder)
    db.session.add(dest)
    db.session.commit()
    try:
        bank_jobs.start(app, bank_id, 'bank_promote',
                        _bank_promote_job(user_id, bank_id, dest.id,
                                          [r.id for r in rows]),
                        total=len(rows))
    except bank_jobs.BankJobBusy:
        _discard_promoted_bank(user_id, dest.id)   # lost the race: leave nothing
        raise
    return dest.id


def _discard_promoted_bank(user_id, dest_bank_id):
    """Unmake a destination bank that never became one. Uncommitted rows are
    rolled back first, then delete_bank takes the row, the working data and the
    copy folder (it is under bank_sources_root, so it is OURS to remove)."""
    try:
        db.session.rollback()
    except Exception:  # noqa: BLE001 — teardown must not mask the real failure
        logger.warning('bank promote: rollback failed', exc_info=True)
    try:
        delete_bank(user_id, dest_bank_id)
    except Exception:  # noqa: BLE001
        logger.warning('bank promote: could not discard the partial bank',
                       exc_info=True)


def _bank_copy_values(row: BankImage, copied_path) -> dict:
    """Metadata a Bank -> Bank copy can keep without inheriting false links.

    The copied image has its own physical size and no derived-clean/rotation
    artifact yet.  Every copy is remeasured from its destination bytes: a source
    path can be replaced after its original Bank scan, so even an unchanged
    resolved path proves nothing about stale technical or ML results.  Caption
    and source attribution are safe user metadata; framing and watermark review
    describe pixels, so a new Bank must review them again.  Cluster and
    duplicate-group ids are container-local, so they are intentionally left
    blank for the destination to rebuild.  Curation deliberately does not: a
    copied Bank has always begun as a fresh triage queue.
    """
    values = {name: None
              for name in bank_transfer_metadata.DETERMINISTIC_ANALYSIS_FIELDS}
    values.update(bank_deterministic_analysis(copied_path) or {})
    values.update({name: None
                   for name in bank_transfer_metadata.MODEL_ANALYSIS_FIELDS})
    values.update({
        'caption': row.caption,
        # Beside 'caption', deliberately NOT among the fields blanked above: the
        # analysis results are about pixels this Bank has not looked at, but the
        # authorship of a sentence is a fact about the sentence and copying it
        # without its author is what turns a protected caption into a rewritable one.
        'caption_origin': row.caption_origin,
        'source_metadata': _source_metadata_storage(row.source_metadata),
        # Both are image-specific review outputs.  The copied image may have
        # been cleaned, rotated, or replaced after the source verdict, so no
        # watermark/framing conclusion is portable to another Bank.
        'framing': None,
        'watermark_state': None,
        'watermark_bbox': None,
        'watermark_regions': None,
        # The target file IS already cleaned/rotated when the source was resolved.
        # Replaying either pointer would look for a non-existent derived blob or
        # rotate the image a second time.
        'watermark_clean_method': None,
        'rotation': None,
        # Preserve the historical Bank -> Bank contract: a copy is a fresh
        # candidate set, never an inherited keep/reject decision.
        'status': 'pending',
        'reject_reason': None,
        # New Bank-local relationships are rebuilt by the normal passes.
        'dup_group': None,
        'semantic_dup_group': None,
        'face_cluster': None,
        'style_cluster': None,
    })
    values['width'], values['height'] = _copied_image_dimensions(copied_path)
    return values


def _bank_promote_job(user_id, src_bank_id, dest_bank_id, ids):
    def run(job):
        src = db.session.get(ImageBank, src_bank_id)
        dest = db.session.get(ImageBank, dest_bank_id)
        if not src or not dest:
            return
        rows = _promote_source_rows(src_bank_id, ids)
        bank_jobs.progress(job, done=0, total=len(rows), detail='copying')
        copied, unreadable = [], 0
        for r in rows:
            if bank_jobs.cancelled(job):
                break
            # RESOLVED path: a watermark-cleaned image must land cleaned, same
            # rule as promoting to a dataset.
            p = resolved_image_path(src, r)
            try:
                # Read + validate the exact bounded bytes before writing. A
                # `copy2` after a header-only check could race a live folder
                # replacement and carry a different (unsafe) file into the new
                # Bank.
                payload = _read_safe_bank_source_bytes(
                    p, label='bank-to-bank promotion')
            except (OSError, TypeError, ValueError, MemoryError,
                    Image.DecompressionBombError, Image.DecompressionBombWarning):
                # One unreadable/locked source costs one image, never the run.
                unreadable += 1
                bank_jobs.bump(job)
                continue
            target = os.path.join(dest.source_path, r.relpath)
            try:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as target_file:
                    target_file.write(payload)
                size = os.path.getsize(target)
            except OSError as e:
                # The source opened, so this is the DESTINATION refusing: disk
                # full, read-only, drive unplugged. Carrying on would leave a
                # bank holding half the selection and presenting as finished —
                # the one outcome worse than failing. Unmake it and say so.
                logger.warning('bank promote: writing the copy failed',
                               exc_info=True)
                _discard_promoted_bank(user_id, dest_bank_id)
                bank_jobs.fail(job, 'Could not write the copies — the new bank '
                                    'was discarded and nothing was changed. '
                                    'Check the free space on the drive holding '
                                    "the app's data, then try again. "
                                    f'({e.strerror or "write failed"})')
                return
            db.session.add(BankImage(
                bank_id=dest_bank_id, relpath=r.relpath, file_size=size,
                **_bank_copy_values(r, target)))
            copied.append(r.id)
            if len(copied) % 200 == 0:
                db.session.commit()
            bank_jobs.bump(job)
        if not copied:
            _discard_promoted_bank(user_id, dest_bank_id)
            bank_jobs.fail(job, 'Nothing could be copied — the new bank was '
                                'discarded. The selected files could not be read.')
            return
        db.session.commit()
        # Marked LAST, and only for what really landed: the source keeps its rows
        # (a promotion never removes anything from the bank it came from) and now
        # says where they went, exactly like a promotion to a dataset.
        for i0 in range(0, len(copied), _SQL_IN_CHUNK):
            (BankImage.query
             .filter(BankImage.bank_id == src_bank_id,
                     BankImage.id.in_(copied[i0:i0 + _SQL_IN_CHUNK]))
             .update({'promoted_bank_id': dest_bank_id},
                     synchronize_session=False))
        db.session.commit()
        detail = f'{len(copied)} image(s) copied into "{dest.name}"'
        if unreadable:
            detail += f', {unreadable} unreadable'
        bank_jobs.progress(job, detail=detail)
    return run


def start_promote(app, user_id, bank_id, ids, dataset_id):
    """Copy a selection into a dataset through the normal import path
    (normalize + perceptual dedup vs the dataset). ``ids`` empty = every KEPT
    image not already on THIS dataset. Background job (a big promotion decodes
    hundreds of files)."""
    bank = get_bank(user_id, bank_id)
    if not bank:
        raise ValueError('bank not found')
    ds = FaceDataset.query.filter_by(id=dataset_id, user_id=user_id).first()
    if not ds:
        raise ValueError('dataset not found')
    if ids:
        ids = [int(i) for i in ids]
    else:
        ids = [r.id for r in
               _promotable_query(bank_id, dataset_id)
               .order_by(BankImage.id.asc()).all()]
    if not ids:
        raise ValueError('nothing to promote — keep some images first')
    return bank_jobs.start(app, bank_id, 'promote',
                           _promote_job(user_id, bank_id, ids, dataset_id),
                           total=len(ids))


def _promote_job(user_id, bank_id, ids, dataset_id):
    def run(job):
        bank = db.session.get(ImageBank, bank_id)
        if not bank:
            return
        rows = []
        for i0 in range(0, len(ids), _SQL_IN_CHUNK):
            rows.extend(BankImage.query.filter(
                BankImage.bank_id == bank_id,
                BankImage.id.in_(ids[i0:i0 + _SQL_IN_CHUNK])).all())
        rows.sort(key=lambda r: r.id)
        bank_jobs.progress(job, done=0, total=len(rows), detail='promoting')
        stats: dict = {}
        imported = failed = 0
        dedupe_seen = _existing_dhash_rows(dataset_id)
        for c0 in range(0, len(rows), _PROMOTE_CHUNK):
            if bank_jobs.cancelled(job):
                break
            chunk = rows[c0:c0 + _PROMOTE_CHUNK]
            blobs, chunk_rows = [], []
            caps, cap_origins, frms, source_meta, snapshots = [], [], [], [], []
            watermark_states, watermark_bboxes, watermark_regions = [], [], []
            for r in chunk:
                # RESOLVED path: a watermark-cleaned image must reach the dataset
                # cleaned, otherwise the two cleaning levels were run for nothing.
                p = resolved_image_path(bank, r)
                try:
                    blobs.append(_read_safe_bank_source_bytes(
                        p, label='bank dataset promotion'))
                    chunk_rows.append(r)
                    # Carry the bank caption onto the dataset image (parallel to blobs),
                    # so a captioned selection lands already captioned.
                    caps.append(r.caption)
                    # ...and WHO wrote it, in the list parallel to it. A caption
                    # the user corrected in the Bank must come back to a Dataset
                    # still marked as theirs, or the round-trip launders it into
                    # something the next forced pass overwrites.
                    cap_origins.append(r.caption_origin)
                    # Carry the framing the bank's classify pass already wrote, so
                    # the dataset's Composition counter is right the moment the
                    # promotion lands (it only tallies rows that HAVE a framing).
                    frms.append(r.framing)
                    # Preserve compatible source attribution and the current
                    # watermark review state/mask alongside the normal caption
                    # fields.  The Dataset importer validates provenance before
                    # it reaches storage.
                    source_meta.append(r.source_metadata)
                    watermark_states.append(r.watermark_state)
                    watermark_bboxes.append(r.watermark_bbox)
                    watermark_regions.append(r.watermark_regions)
                    # The importer recomputes the strict deterministic snapshot
                    # from the final normalized Dataset WebP; no source score or
                    # ML verdict is carried through this marker.
                    snapshots.append(True)
                except (OSError, TypeError, ValueError, MemoryError,
                        Image.DecompressionBombError, Image.DecompressionBombWarning):
                    failed += 1
            if blobs:
                new_ids, bad = import_images(
                    user_id, dataset_id, blobs, dedupe=True, stats=stats,
                    captions=caps, caption_origins=cap_origins,
                    bank_image_ids=[r.id for r in chunk_rows],
                    framings=frms, source_metadata=source_meta,
                    bank_analysis_snapshots=snapshots,
                    watermark_states=watermark_states,
                    watermark_bboxes=watermark_bboxes,
                    watermark_regions=watermark_regions,
                    dedupe_seen=dedupe_seen)
                imported += len(new_ids)
                failed += bad
                # The dataset row now carries the link back (import_images writes
                # it, and hands it to the matched row when a dedupe skips the
                # blob), so 'already promoted here' is a fact we can re-check.
                # Clear the legacy one-way flag as we go: it would otherwise keep
                # excluding this image from the target long after the user
                # deleted it there.
                #
                # The exception is an image whose row in the dataset is already
                # credited to ANOTHER bank (both banks hold the same photo). There
                # is one column for one owner, so this bank gets no verifiable
                # trace and keeps the old flag — the alternative is offering the
                # image on every promotion, forever.
                unlinked = set(stats.get('bank_unlinked') or ())
                stats.pop('bank_unlinked', None)
                for r in chunk_rows:
                    r.promoted_dataset_id = dataset_id if r.id in unlinked else None
                db.session.commit()
            bank_jobs.bump(job, len(chunk))
        dups = stats.get('duplicates', 0)
        small = stats.get('small', 0)
        detail = f'done — {imported} imported'
        if dups:
            detail += f', {dups} already in the dataset'
        if failed:
            detail += f', {failed} failed'
        if small:
            detail += f', {small} under the recommended size'
        bank_jobs.progress(job, detail=detail)

    def run_locked(job):
        with _dataset_ingest_lock(user_id, dataset_id):
            return run(job)

    return run_locked
