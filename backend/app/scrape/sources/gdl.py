# app/scrape/sources/gdl.py
"""Reusable gallery-dl engine: enumeration (--simulate -j) and exit-code
classification with a configurable platform tag. Extracted from the
Erome wrapper, fixing type -1 sentinels that hid auth/429/DDoS-Guard
errors as empty results.

Security: --ignore-config, shell=False, list arguments, never --exec."""
from ...timeout_settings import network_timeout
import json
import os
import subprocess
import sys
import time
import logging
from urllib.parse import urlparse

from .base import ResultList

logger = logging.getLogger(__name__)

GDL_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 300
DEFAULT_MAX_ITEMS = 120
DEFAULT_MAX_ALBUMS = 8
_VIDEO_EXTS = ('mp4', 'webm', 'mov', 'm4v')

# Default scan deadline budget, derived from GDL_TIMEOUT. A top-level
# subprocess can consume GDL_TIMEOUT before the album loop checks the
# deadline; an album already started also runs to completion. The true
# worst case is about 2*GDL_TIMEOUT, not this constant. A 30-second margin
# allows small album listings without blocking Flask for many minutes.
#
# This is a default, not opt-in. Every gallery-dl source can launch
# 1+max_albums subprocesses per synchronous request. Previously only
# universal.py passed a deadline; new callers must inherit the protection
# without remembering to request it.
DEFAULT_SCAN_BUDGET_SECONDS = GDL_TIMEOUT + 30

# gallery-dl exit-code bitmask (gallery_dl/exception.py), checked on 1.32.3.
EXIT_HTTP = 4
EXIT_NOTFOUND = 8
EXIT_AUTH = 16
EXIT_UNSUPPORTED = 64


def classify_exit(returncode):
    """Map gallery-dl exit code to unsupported/auth/network/toolerror, or None
    for zero. Test OR-combined bitmask flags from most specific to generic.

    Success means equality to zero, not Python falsiness: subprocess.run
    never returns None, but a poor test double can. None must remain an
    unclassified toolerror rather than success followed by an empty result."""
    if returncode == 0:
        return None
    if returncode is None:
        return 'toolerror'
    if returncode & EXIT_UNSUPPORTED:
        return 'unsupported'
    if returncode & EXIT_AUTH:
        return 'auth'
    if returncode & (EXIT_NOTFOUND | EXIT_HTTP):
        return 'network'
    return 'toolerror'


class GdlError(str):
    """A gallery-dl error string carrying its classified kind.

    Subclassing str preserves message consumers. Branch on kind; wording
    serves users only. This avoids the old universal.py comparison against
    a message with an extra space, which made yt-dlp fallback unreachable.

    Kinds: unsupported/auth/network/toolerror come from classify_exit.
    enumerate assigns empty when gallery-dl succeeds without media. Keeping
    empty separate from toolerror lets callers distinguish a valid empty
    result from an actual tool failure."""

    def __new__(cls, message, kind=None):
        obj = super().__new__(cls, message)
        obj.kind = kind
        return obj


def _media_item(entry, platform):
    """Map gallery-dl type-3 entry [3, media_url, meta] to the common schema, or None."""
    if not isinstance(entry, (list, tuple)) or len(entry) < 3:
        return None
    media_url = entry[1]
    meta = entry[2] if isinstance(entry[2], dict) else {}
    if not isinstance(media_url, str) or not media_url:
        return None
    ext = str(meta.get('extension', '')).lower()
    if not ext:
        ext = os.path.splitext(urlparse(media_url).path)[1].lstrip('.').lower()
    media_type = 'video' if ext in _VIDEO_EXTS else 'image'
    return {
        'url': media_url,
        'title': meta.get('title') or '',
        'thumbnail': meta.get('thumbnail') or (media_url if media_type == 'image' else None),
        'type': media_type,
        'platform': platform,
    }


def _run_simulate(url, max_items, cookies, extra_opts, image_range=None):
    """Run gallery-dl --ignore-config --simulate -j; return (entries|None, error|None).
    Never raises. image_range (e.g. 101-200) bounds the listing image window,
    defaulting to 1-max_items. Direct-image sources such as Civitai use it
    for Load more; gallery queues such as PornPics use --chapter-range
    through extra_opts instead."""
    cmd = [sys.executable, '-m', 'gallery_dl', '--ignore-config',
           '--simulate', '-j', '--range', image_range or f'1-{max_items}']
    if cookies:
        cmd += ['--cookies', cookies]
    if extra_opts:
        cmd += list(extra_opts)
    cmd += ['--', url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=network_timeout(GDL_TIMEOUT), shell=False)
    except subprocess.TimeoutExpired:
        return None, GdlError(f"gallery-dl: timed out ({GDL_TIMEOUT}s).", 'network')
    except Exception as e:
        logger.warning("gallery-dl: failed %s: %s", url, e)
        return None, GdlError(f"gallery-dl: failed ({e}).", 'toolerror')

    stdout = (proc.stdout or '').strip()
    if not stdout:
        kind = classify_exit(proc.returncode)
        if kind is None:
            # Exit zero with no stdout is a valid empty scan, not an unclassified
            # tool failure. GdlError kind=empty preserves that distinction.
            # classify_exit returns None only for returncode=0.
            kind = 'empty'
        last = ((proc.stderr or '').strip().splitlines() or ['no data'])[-1]
        return None, GdlError(f"gallery-dl: {kind} ({last[:200]}).", kind)
    try:
        data = json.loads(stdout)
    except (ValueError, TypeError) as e:
        return None, GdlError(f"gallery-dl: unreadable response ({e}).", 'toolerror')
    if not isinstance(data, list):
        return None, GdlError("gallery-dl: unexpected format.", 'toolerror')
    return data, None


# Exception classes gallery-dl reports when its OWN extractor code broke, as
# opposed to a site refusing us (auth, 429, DDoS-Guard). Their messages are
# Python internals -- "string indices must be integers, not 'str'" reached a
# user as a bare red toast on a Civitai listing: it names nothing, blames
# nobody, and reads as if THIS app crashed. It means the site changed shape
# under the scraping tool.
_UPSTREAM_BUG_ERRORS = frozenset({
    'TypeError', 'KeyError', 'IndexError', 'AttributeError', 'ValueError',
})


def _error_sentinel(entries):
    """Return the message of a type -1 extractor-error entry, if present.

    Reword extractor crashes rather than forwarding raw Python exceptions.
    Naming gallery-dl and explaining that site support needs an update gives
    users an actionable diagnosis instead of suggesting the app itself broke."""
    for entry in entries:
        if isinstance(entry, (list, tuple)) and entry and entry[0] == -1:
            meta = entry[1] if len(entry) > 1 and isinstance(entry[1], dict) else {}
            kind = str(meta.get('error') or '').strip()
            message = str(meta.get('message') or '').strip()
            if kind in _UPSTREAM_BUG_ERRORS:
                return ('The scraping tool could not read this site: its support for '
                        'it is out of date (gallery-dl raised '
                        f'{kind}{": " + message if message else ""}). This is not '
                        'something a different URL will fix — the site changed and '
                        'the tool has to catch up. Try another source meanwhile.')
            return message or kind or "gallery-dl: the extractor failed."
    return None


def enumerate(url, *, platform='generic', max_items=DEFAULT_MAX_ITEMS,
              max_albums=DEFAULT_MAX_ALBUMS, cookies=None, extra_opts=None,
              image_range=None, per_album=None, deadline=None):
    """Enumerate URL media through gallery-dl; return (items, error), never raise.

    Handle message types -1 (propagate errors), 2 (ignore headers), 3 (media)
    and 6 (recurse into at most max_albums children). image_range bounds only
    the top-level listing. Album recursion retains 1-max_items by default.
    per_album limits recursive album media (1 means a cover); it never limits
    top-level media, so a direct album URL still returns the full album.

    deadline is an absolute time.monotonic timestamp, not a duration. None
    applies DEFAULT_SCAN_BUDGET_SECONDS automatically for every caller. It
    limits album recursion only: top-level scanning is one subprocess and
    already-started children run to completion. The real worst case remains
    about 2*GDL_TIMEOUT. On expiry, preserve collected items with partial=True
    rather than returning an error after a long wait."""
    if deadline is None:
        deadline = time.monotonic() + network_timeout(DEFAULT_SCAN_BUDGET_SECONDS)
    try:
        entries, err = _run_simulate(url, max_items, cookies, extra_opts,
                                     image_range=image_range)
        if err:
            return None, err
        # Propagate type -1 auth/429/DDoS-Guard errors BEFORE deciding no media
        # were found; this fixes the original Erome bug.
        sentinel = _error_sentinel(entries)
        if sentinel:
            return None, GdlError(sentinel, 'toolerror')

        items = []
        for entry in entries:
            if isinstance(entry, (list, tuple)) and entry and entry[0] == 3:
                item = _media_item(entry, platform)
                if item:
                    items.append(item)
                    if len(items) >= max_items:
                        return items[:max_items], None
        if items:
            return items[:max_items], None

        # No direct media: recurse into type-6 albums.
        album_urls = []
        for entry in entries:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2 and entry[0] == 6:
                if isinstance(entry[1], str) and entry[1]:
                    album_urls.append(entry[1])
                    if len(album_urls) >= max_albums:
                        break
        def _from_albums(collected):
            """Wrap recursively collected album items with from_albums/partial
            provenance (see base.ResultList)."""
            out = ResultList(collected[:max_items])
            out.from_albums = True
            out.partial = timed_out
            return out

        album_errors = []
        timed_out = False
        for album_url in album_urls:
            # Stop when the global budget expires, checked at loop entry rather than
            # during an already-running subprocess. At least the first iteration
            # always starts, even if the deadline has already passed.
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            # When per_album is set, bound simulation itself with --range 1-N so
            # gallery-dl stops after N images rather than enumerating the full album.
            sub, sub_err = _run_simulate(album_url, max_items, cookies, extra_opts,
                                         image_range=f'1-{per_album}' if per_album else None)
            if sub_err:
                album_errors.append(sub_err)
                continue
            if not sub:
                continue
            sent = _error_sentinel(sub)
            if sent:
                # Use the same GdlError wrapper as the top-level sentinel. A plain str
                # would lose kind and be silently misclassified as None rather than
                # toolerror by getattr-based consumers.
                album_errors.append(GdlError(sent, 'toolerror'))
                continue
            taken = 0
            for entry in sub:
                if isinstance(entry, (list, tuple)) and entry and entry[0] == 3:
                    item = _media_item(entry, platform)
                    if item:
                        items.append(item)
                        taken += 1
                        if len(items) >= max_items:
                            return _from_albums(items), None
                        if per_album and taken >= per_album:
                            break
        if items:
            return _from_albums(items), None
        # Album errors take precedence over timed_out. A blocked scan can collect
        # auth/429/DDoS-Guard errors before its budget expires. Checking timeout
        # first would hide the real rejection behind kind=empty and discard the
        # extractor message. Preserve error propagation even when time also expires.
        if album_errors:
            return None, album_errors[0]
        if timed_out:
            # Budget exhausted with neither collected items nor album errors: follow
            # the empty-result convention (kind=empty), not toolerror. A truncated
            # scan without results is still a valid empty result.
            return None, GdlError(
                "gallery-dl: time budget exhausted before any album could be scanned.",
                'empty')
        return None, GdlError("gallery-dl: no media found.", 'empty')
    except Exception as e:  # garde-fou ultime
        logger.exception("gdl.enumerate: unexpected error")
        return None, GdlError(f"gallery-dl: unexpected error ({e}).", 'toolerror')


def download(url, dest_dir, filename, *, cookies=None, extra_opts=None):
    """Download through gallery-dl into dest_dir with a deterministic name.
    Return (ok, abs_path|None, error|None); never raise. Use --ignore-config,
    shell=False, list arguments and -- before the URL."""
    cmd = [sys.executable, '-m', 'gallery_dl', '--ignore-config',
           '-D', dest_dir, '-o', f'filename={filename}_{{num}}.{{extension}}',
           '--no-part', '--no-mtime']
    if cookies:
        cmd += ['--cookies', cookies]
    if extra_opts:
        cmd += list(extra_opts)
    cmd += ['--', url]
    try:
        os.makedirs(dest_dir, exist_ok=True)
        before = set(os.listdir(dest_dir))
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=network_timeout(DOWNLOAD_TIMEOUT), shell=False)
    except subprocess.TimeoutExpired:
        # Any partial file is not cleaned up here (outside this function's scope).
        return False, None, GdlError("gallery-dl: download timed out.", 'network')
    except Exception as e:
        logger.warning("gallery-dl download: failed %s: %s", url, e)
        return False, None, GdlError(f"gallery-dl: failed ({e}).", 'toolerror')

    if proc.returncode:
        kind = classify_exit(proc.returncode)
        last = ((proc.stderr or '').strip().splitlines() or [''])[-1]
        return False, None, GdlError(f"gallery-dl: {kind or 'failed'} ({last[:200]}).", kind)

    # Find the output path by parsing gallery-dl stdout, which lists written
    # paths; otherwise use the newest file that appeared in dest_dir.
    for line in reversed((proc.stdout or '').splitlines()):
        line = line.strip()
        if line and os.path.isfile(line):
            return True, line, None
    after = set(os.listdir(dest_dir)) - before
    if after:
        newest = max((os.path.join(dest_dir, f) for f in after), key=os.path.getmtime)
        return True, newest, None
    return False, None, GdlError("gallery-dl: no file produced.", 'toolerror')
