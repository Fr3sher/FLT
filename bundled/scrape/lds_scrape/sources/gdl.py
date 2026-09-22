# app/scrape/sources/gdl.py
"""Reusable gallery-dl engine: enumeration (--simulate -j) and exit classification.

The configurable platform tag generalizes the original Erome wrapper, including
its type--1 error sentinel fix: authentication, 429 and DDoS-Guard failures were
previously mistaken for empty results.

Security: --ignore-config, shell=False, argument lists, never --exec."""
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

# Default enumerate() time budget when the caller supplies no deadline.
# Derive it from GDL_TIMEOUT: the initial subprocess can consume that entire
# timeout before the album loop checks the deadline, and an already-started
# album subprocess runs to completion. The actual worst case is therefore
# about 2 * GDL_TIMEOUT, not this budget. An extra 30 seconds allows small album
# listings to finish while limiting pathological synchronous Flask requests.
# Apply this by default to every gallery-dl source so new callers cannot
# accidentally omit the protection.
DEFAULT_SCAN_BUDGET_SECONDS = GDL_TIMEOUT + 30

# gallery-dl exit codes are a bitmask (gallery_dl/exception.py), verified on 1.32.3.
EXIT_HTTP = 4
EXIT_NOTFOUND = 8
EXIT_AUTH = 16
EXIT_UNSUPPORTED = 64


def classify_exit(returncode):
    """Map a gallery-dl exit code to unsupported/auth/network/toolerror, or None
    for zero. Check OR-combined bits from most specific to most general.

    Success requires equality to zero rather than Python falsiness. subprocess.run
    never returns None, but an incomplete test double might. Treat None explicitly
    as 'toolerror' instead of silently classifying it as success and then 'empty'."""
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
    """A gallery-dl error message carrying a classified kind.

    As a str subclass, it preserves existing message-only callers. Branch on kind
    (see classify_exit); the text is only for display. This avoids brittle string
    comparisons that once made universal.py's yt-dlp fallback unreachable.

    The five supported kinds are:
    - 'unsupported', 'auth', 'network', 'toolerror', derived from the exit code;
    - 'empty', assigned by enumerate() when extraction succeeds without media.
    Keep 'empty' distinct from 'toolerror' so a valid empty page cannot be mistaken
    for an extractor failure."""

    def __new__(cls, message, kind=None):
        obj = super().__new__(cls, message)
        obj.kind = kind
        return obj


def _media_item(entry, platform):
    """Convert gallery-dl type-3 [3, media_url, meta] to a shared-schema item or None."""
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
    Never raises. image_range (e.g. '101-200') bounds the listing's image window,
    defaulting to '1-{max_items}'. This enables "Load more" for direct-image
    sources such as Civitai; gallery queues use --chapter-range in extra_opts."""
    cmd = [sys.executable, '-m', 'gallery_dl', '--ignore-config',
           '--simulate', '-j', '--range', image_range or f'1-{max_items}']
    if cookies:
        cmd += ['--cookies', cookies]
    if extra_opts:
        cmd += list(extra_opts)
    cmd += ['--', url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=GDL_TIMEOUT, shell=False)
    except subprocess.TimeoutExpired:
        return None, GdlError(f"gallery-dl: timed out ({GDL_TIMEOUT}s).", 'network')
    except Exception as e:
        logger.warning("gallery-dl: failed %s: %s", url, e)
        return None, GdlError(f"gallery-dl: failed ({e}).", 'toolerror')

    stdout = (proc.stdout or '').strip()
    if not stdout:
        kind = classify_exit(proc.returncode)
        if kind is None:
            # Exit zero with empty stdout is a successful empty scan, not a tool
            # failure. classify_exit() returns None only for returncode=0; preserve
            # that distinction through the 'empty' kind.
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
    """Return the extractor message if a type--1 error entry is present.

    Reword extractor crashes rather than forwarding raw Python exceptions.
    Naming gallery-dl and explaining that its site support needs an update gives
    the user an actionable explanation instead of an unexplained parsing error."""
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
    """Enumerate media through gallery-dl and return (items, error). Never raises.

    Handle messages -1 (propagated error), 2 (ignored header), 3 (media), and 6
    (child album recursion bounded by max_albums).

    image_range selects the top-level image window; album recursion retains the
    1-max_items default. per_album limits media returned from each child album:
    1 selects its cover. It does not affect top-level media, so a direct album URL
    still returns the complete album.

    deadline is an absolute time.monotonic() timestamp. None automatically applies
    DEFAULT_SCAN_BUDGET_SECONDS, so all gallery-dl sources inherit the protection.
    Only album recursion checks this deadline; the initial subprocess and any
    already-started album subprocess can each take GDL_TIMEOUT. The real worst
    case is therefore about 2 * GDL_TIMEOUT. On expiry, return collected items
    with partial=True rather than discarding useful results for an error."""
    if deadline is None:
        deadline = time.monotonic() + DEFAULT_SCAN_BUDGET_SECONDS
    try:
        entries, err = _run_simulate(url, max_items, cookies, extra_opts,
                                     image_range=image_range)
        if err:
            return None, err
        # Propagate type--1 extractor errors (auth/429/DDoS-Guard) before
        # concluding that no media exists; this fixes the original Erome bug.
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
            """Wrap album-recursion items with from_albums and partial provenance.
            See base.ResultList."""
            out = ResultList(collected[:max_items])
            out.from_albums = True
            out.partial = timed_out
            return out

        album_errors = []
        timed_out = False
        for album_url in album_urls:
            # Stop when the global budget expires. Check between subprocesses,
            # never inside one already running. The first iteration always starts,
            # even if the deadline has already expired.
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            # Bound the simulation itself with --range 1-N when per_album is set,
            # so gallery-dl stops after N images instead of enumerating the whole album.
            sub, sub_err = _run_simulate(album_url, max_items, cookies, extra_opts,
                                         image_range=f'1-{per_album}' if per_album else None)
            if sub_err:
                album_errors.append(sub_err)
                continue
            if not sub:
                continue
            sent = _error_sentinel(sub)
            if sent:
                # Use GdlError just as for the top-level sentinel. A plain string
                # would lose .kind, causing callers to misroute this tool failure.
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
        # Album errors take precedence over timed_out: a blocked scan may
        # record authentication, 429 or DDoS-Guard errors before the deadline.
        # Checking timeout first would hide that actionable error behind 'empty'.
        # Preserve error reporting even when the time budget also expires.
        if album_errors:
            return None, album_errors[0]
        if timed_out:
            # No items and no album errors before the budget expired. Use 'empty',
            # as for any valid scan without media; truncation alone is not a tool
            # failure.
            return None, GdlError(
                "gallery-dl: time budget exhausted before any album could be scanned.",
                'empty')
        return None, GdlError("gallery-dl: no media found.", 'empty')
    except Exception as e:  # garde-fou ultime
        logger.exception("gdl.enumerate: unexpected error")
        return None, GdlError(f"gallery-dl: unexpected error ({e}).", 'toolerror')


def download(url, dest_dir, filename, *, cookies=None, extra_opts=None):
    """Download to dest_dir through gallery-dl with a deterministic filename.
    Return (ok, abs_path|None, error|None); never raises. Use --ignore-config,
    shell=False, an argument list and a -- separator before the URL."""
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
                              timeout=DOWNLOAD_TIMEOUT, shell=False)
    except subprocess.TimeoutExpired:
        # Any partial file is left in place here; cleanup is outside this function.
        return False, None, GdlError("gallery-dl: download timed out.", 'network')
    except Exception as e:
        logger.warning("gallery-dl download: failed %s: %s", url, e)
        return False, None, GdlError(f"gallery-dl: failed ({e}).", 'toolerror')

    if proc.returncode:
        kind = classify_exit(proc.returncode)
        last = ((proc.stderr or '').strip().splitlines() or [''])[-1]
        return False, None, GdlError(f"gallery-dl: {kind or 'failed'} ({last[:200]}).", kind)

    # Find the output path in stdout, where gallery-dl prints written paths;
    # fall back to the newest file created in dest_dir.
    for line in reversed((proc.stdout or '').splitlines()):
        line = line.strip()
        if line and os.path.isfile(line):
            return True, line, None
    after = set(os.listdir(dest_dir)) - before
    if after:
        newest = max((os.path.join(dest_dir, f) for f in after), key=os.path.getmtime)
        return True, newest, None
    return False, None, GdlError("gallery-dl: no file produced.", 'toolerror')
