"""👁️ ComfyUI's console, read from the app.

ComfyUI keeps the last few hundred lines of its own console in memory and
serves them on `/internal/logs/raw` — the very text a `.bat` window shows,
progress bars included. That buffer is the only place the state of a render
lives once the window is hidden: a 175-frame clip that paged its way through a
24 GB card ran for hours as `3/4 [1:07:21<1:03:12, 3792.78s/it]`, and nothing
in the app could say so. The queue called it "paused", the banner said
"ComfyUI stopped answering", and the person holding the phone had no way to
tell a dead job from a slow one.

This module turns that buffer into three things every surface can show:
the last lines (paths and tokens redacted, colour codes stripped), the current
progress bar parsed into numbers, and a one-line "where is it" summary. Cached
for a couple of seconds and shared, because the queue dock, the banner and the
clip card all ask at once. Read-only by construction; it never posts anything.
"""
from __future__ import annotations
from ..timeout_settings import network_timeout

import logging
import re
import threading
import time
from datetime import datetime

import requests

from .. import config as cfg
from ..utils.redact import redact_tokens, redact_user_paths

logger = logging.getLogger(__name__)

# ComfyUI's route (`api_server/routes/internal/internal_routes.py`). Fixed
# path, GET only; an older ComfyUI answers 404 and the snapshot says so.
_RAW_LOGS_PATH = '/internal/logs/raw'
# Short on purpose: the queue dock's listing and the clip poll wait on this
# read, and a ComfyUI whose HTTP loop is starved by the very render it is asked
# about answers late or not at all. A late answer serves the last good
# snapshot, marked stale, rather than holding every listing hostage.
_TIMEOUT = (1.0, 2.5)
_CACHE_SECONDS = 2.0
_MAX_LINES = 200

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')
# tqdm's bar, as ComfyUI prints it for a sampler:
#   ` 75%|███████▌  | 3/4 [1:07:21<1:03:12, 3792.78s/it]`
#   `100%|██████████| 6/6 [01:06<00:00, 11.14s/it]`
#   `  0%|          | 0/4 [00:00<?, ?it/s,   Model Initializing ...  ]`
_PROGRESS_RE = re.compile(
    r'(?P<percent>\d{1,3})%\|[^|]*\|\s*(?P<value>\d+)/(?P<total>\d+)\s*'
    r'\[(?P<elapsed>[\d:]+)<(?P<remaining>[\d:?]+),\s*(?P<rate>[\d.?]+)\s*(?P<unit>s/it|it/s)')
_PROMPT_FINISHED_RE = re.compile(r'^(?:\[INFO\]\s*)?Prompt executed in ')

_lock = threading.Lock()
_cache: dict = {'at': 0.0, 'snapshot': None}
# How long a last good snapshot keeps standing in for a silent ComfyUI.
_STALE_SECONDS = 120.0


def _clock_seconds(text) -> int | None:
    """'1:03:12' / '01:06' -> seconds; '?' -> None."""
    if not text or '?' in text:
        return None
    parts = text.split(':')
    try:
        numbers = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for number in numbers:
        seconds = seconds * 60 + number
    return seconds


def parse_progress(line, at=None) -> dict | None:
    """The numbers inside one tqdm line, or None when the line is not a bar.

    `at` is the ISO timestamp ComfyUI stamped the line with, so a reader can
    tell a bar that moved a minute ago from one that has not moved in an hour.
    """
    if not line:
        return None
    match = _PROGRESS_RE.search(line)
    if not match:
        return None
    try:
        value = int(match.group('value'))
        total = int(match.group('total'))
    except ValueError:
        return None
    rate_text = match.group('rate')
    try:
        rate = float(rate_text) if '?' not in rate_text else None
    except ValueError:
        rate = None
    unit = match.group('unit')
    seconds_per_step = None
    if rate is not None and rate > 0:
        seconds_per_step = rate if unit == 's/it' else 1.0 / rate
    return {
        'value': value,
        'total': total,
        'percent': max(0, min(100, int(match.group('percent')))),
        'elapsed_s': _clock_seconds(match.group('elapsed')),
        'remaining_s': _clock_seconds(match.group('remaining')),
        'seconds_per_step': seconds_per_step,
        'at': at,
    }


# Any absolute path — a drive, a UNC share, a POSIX root — shortened to its
# last two components. The home-folder helper only hides the account name, and
# ComfyUI's folders are configurable: models on another disk, outputs on a
# NAS, a dataset folder named after a person, all printed in full by a
# traceback (found by refutation). The file name survives, which is what a
# console line needs to stay readable; where it lives does not leave the app.
# A drive letter is a path only at a word start: `http://` must not read as
# the `p:` drive.
_WIN_PATH_RE = re.compile(r'(?:(?<![\w.])[A-Za-z]:[\\/]|\\\\|(?<![\w.])~[\\/])[^\s"\'<>|,;)\]]*')
_POSIX_PATH_RE = re.compile(r'(?<![\w/:.…])~?/(?:[^\s"\'<>|,;)\]/]+/)+[^\s"\'<>|,;)\]/]*')


def _shorten_path(match) -> str:
    parts = [p for p in re.split(r'[\\/]+', match.group(0))
             if p and p != '~' and not re.fullmatch(r'[A-Za-z]:', p)]
    if len(parts) <= 1:
        return match.group(0)
    if len(parts) == 2 and parts[0].lower() in ('users', 'home'):
        return '~'                    # a bare home folder: the account name IS the path
    return '…/' + '/'.join(parts[-2:])


def redact_console_line(text) -> str:
    """Every absolute path shortened to its last two components, then the
    home-folder helper for whatever shape it still recognises, then tokens."""
    text = _WIN_PATH_RE.sub(_shorten_path, str(text or ''))
    text = _POSIX_PATH_RE.sub(_shorten_path, text)
    text = redact_user_paths(text)
    return redact_tokens(text)


def _clean(message) -> str:
    text = _ANSI_RE.sub('', str(message or ''))
    text = text.replace('\r', '\n').rstrip()
    return redact_console_line(text)


def _entries(payload) -> list:
    entries = payload.get('entries') if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return []
    lines = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        text = _clean(entry.get('m'))
        if not text.strip():
            continue
        stamp = entry.get('t')
        for piece in text.split('\n'):
            piece = piece.rstrip()
            if piece.strip():
                lines.append({'t': stamp if isinstance(stamp, str) else None, 'm': piece})
    return lines[-_MAX_LINES:]


def _last_progress(lines) -> dict | None:
    for line in reversed(lines):
        # The next prompt can be loading models while the buffer still holds
        # the previous sampler's 100% bar. Completion ends that bar's lifetime.
        # "got prompt" cannot do this: it also logs work queued behind a render.
        if _PROMPT_FINISHED_RE.match(line['m'].lstrip()):
            return None
        progress = parse_progress(line['m'], line.get('t'))
        if progress is not None:
            return progress
    return None


def _age_seconds(stamp) -> float | None:
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
    except ValueError:
        return None
    if when.tzinfo is not None:
        when = when.replace(tzinfo=None)
    # ComfyUI stamps its buffer in the machine's local time, naive.
    return max(0.0, (datetime.now() - when).total_seconds())


def _running_prompt(api_url):
    """The prompt id ComfyUI is executing right now, or None when it cannot say.

    The console never names a prompt — not one line of a 300-line buffer holds
    an id (measured) — so the only way to know whose bar it shows is to ask
    /queue which prompt is running. A bar shown under a prompt that is merely
    queued behind another would be the other one's, read as ours.
    """
    try:
        response = requests.get(api_url.rstrip('/') + '/queue', timeout=network_timeout(_TIMEOUT),
                                allow_redirects=False)
        if not 200 <= response.status_code < 300:
            return None
        queue = response.json()
        running = queue.get('queue_running') if isinstance(queue, dict) else None
        if not isinstance(running, list) or not running:
            return None
        entry = running[0]
        if isinstance(entry, (list, tuple)) and len(entry) > 1:
            return str(entry[1])
        if isinstance(entry, dict):
            return str(entry.get('prompt_id') or entry.get('id') or '') or None
    except (requests.RequestException, ValueError, AttributeError):
        return None
    return None


def _read(api_url) -> dict:
    url = api_url.rstrip('/') + _RAW_LOGS_PATH
    try:
        response = requests.get(url, timeout=network_timeout(_TIMEOUT), allow_redirects=False)
    except requests.ReadTimeout:
        return {'available': False, 'reason': 'ComfyUI is slow to answer right now.'}
    except requests.RequestException:
        return {'available': False, 'reason': 'ComfyUI did not answer.'}
    if response.status_code == 404:
        return {'available': False,
                'reason': 'This ComfyUI does not expose its console over its API '
                          '(it needs ComfyUI 0.2.3 or newer).'}
    if not 200 <= response.status_code < 300:
        return {'available': False, 'reason': f'ComfyUI answered HTTP {response.status_code}.'}
    try:
        payload = response.json()
    except ValueError:
        return {'available': False, 'reason': 'ComfyUI answered something that is not its console.'}
    lines = _entries(payload)
    progress = _last_progress(lines)
    if progress is not None:
        progress['age_s'] = _age_seconds(progress.get('at'))
    # When the console last moved at all. A prompt ComfyUI lists forever with
    # a dead executor prints nothing more; a long step prints nothing either.
    # The number does not decide, it lets the person looking decide.
    activity_age = _age_seconds(lines[-1].get('t')) if lines else None
    return {'available': True, 'reason': None, 'lines': lines, 'progress': progress,
            'activity_age_s': activity_age,
            'running_prompt_id': _running_prompt(api_url) if progress is not None else None}


def snapshot(max_age=_CACHE_SECONDS) -> dict:
    """The console as of the last couple of seconds, shared by every caller.

    Always a dict with `available`; `lines` is the cleaned tail (newest last),
    `progress` the last bar parsed, or None. Never raises: a console that cannot
    be read is a snapshot that says so.
    """
    api_url = (cfg.get('comfyui.api_url') or '').strip()
    if not api_url:
        return {'available': False, 'reason': 'ComfyUI is not configured.',
                'lines': [], 'progress': None, 'fetched_at': time.time()}
    now = time.monotonic()
    with _lock:
        cached = _cache['snapshot']
        if cached is not None and now - _cache['at'] < max_age:
            return cached
    try:
        fresh = _read(api_url)
    except Exception:                       # noqa: BLE001 — a glance is never fatal
        logger.exception('comfyui console: read failed')
        fresh = {'available': False, 'reason': 'The console could not be read.'}
    if not fresh.get('available') and cached is not None and cached.get('available'):
        # ComfyUI was slow or silent THIS time; the previous lines are still the
        # truest thing on hand. Kept for a bounded while, and said to be stale.
        if time.monotonic() - _cache['at'] < _STALE_SECONDS:
            stale = dict(cached)
            stale['stale'] = True
            stale['reason'] = fresh.get('reason')
            with _lock:
                _cache['snapshot'] = stale    # the freshness clock is NOT reset
            return stale
    fresh.setdefault('lines', [])
    fresh.setdefault('progress', None)
    fresh['stale'] = False
    fresh['fetched_at'] = time.time()
    with _lock:
        _cache['snapshot'] = fresh
        _cache['at'] = time.monotonic()
    return fresh


def clear_cache() -> None:
    """Tests, and a launcher that just started a new ComfyUI."""
    with _lock:
        _cache['snapshot'] = None
        _cache['at'] = 0.0


def _owned_progress(snap, prompt_id):
    """The bar, only when it is THIS prompt's. Unknown ownership (no prompt id
    to compare, or /queue silent) keeps the bar: a lone LDS job on ComfyUI is
    the common case and a spinner would be the worse answer. A KNOWN foreign
    prompt on the GPU drops it: that bar is somebody else's render."""
    progress = snap.get('progress')
    if progress is None or not prompt_id:
        return progress, False
    running = snap.get('running_prompt_id')
    if running is None or str(running) == str(prompt_id):
        return progress, False
    return None, True


def tail(lines=12, prompt_id=None) -> dict:
    """The banner's and the card's slice: the last `lines`, plus the progress
    when it belongs to `prompt_id` (or when nobody can tell)."""
    snap = snapshot()
    keep = max(1, min(_MAX_LINES, int(lines or 12)))
    progress, foreign = _owned_progress(snap, prompt_id)
    return {'available': snap['available'], 'reason': snap.get('reason'),
            'lines': snap['lines'][-keep:], 'progress': progress,
            'foreign_render': foreign,
            'activity_age_s': snap.get('activity_age_s'), 'stale': bool(snap.get('stale'))}


def render_progress(job_id=None, prompt_id=None) -> dict | None:
    """What a listing carries while a job is on the GPU: the bar, the last
    console line and the one-line sentence, tagged with the job it belongs to.
    None when the console cannot say, or when the bar is another prompt's."""
    snap = snapshot()
    if not snap['available']:
        return None
    progress, foreign = _owned_progress(snap, prompt_id)
    if foreign:
        return None
    last = snap['lines'][-1]['m'] if snap['lines'] else None
    # job_id labels the requested LDS job; it is not proof of who produced
    # the console sample. Strict consumers need a separately verified owner.
    running = snap.get('running_prompt_id')
    owner_confirmed = bool(prompt_id and running and str(running) == str(prompt_id)
                           and not snap.get('stale'))
    return {'job_id': job_id, 'progress': progress, 'line': last,
            'owner_confirmed': owner_confirmed,
            'sentence': progress_sentence(progress)}


def progress_sentence(progress) -> str | None:
    """"step 3/4 · 63 min per step · about 1 h left" — the one line a card shows."""
    if not isinstance(progress, dict) or not progress.get('total'):
        return None
    parts = [f"step {progress.get('value', 0)}/{progress['total']}"]
    per_step = progress.get('seconds_per_step')
    if per_step:
        parts.append(f'{_duration(per_step)} per step')
    remaining = progress.get('remaining_s')
    if remaining is not None:
        parts.append(f'about {_duration(remaining)} left')
    return ' · '.join(parts)


def _duration(seconds) -> str:
    seconds = int(round(float(seconds)))
    if seconds < 60:
        return f'{seconds} s'
    minutes = seconds // 60
    if minutes < 60:
        return f'{minutes} min'
    hours, minutes = divmod(minutes, 60)
    return f'{hours} h {minutes:02d} min' if minutes else f'{hours} h'
