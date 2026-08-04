"""What each way of getting a checkpoint onto a pod COSTS, before the click.

THE NUMBER NOBODY WAS SHOWN
---------------------------
A pod is rented by the hour and is billed from the moment it boots. Seeding its
checkpoint happens on a pod that is already running: the GPU is paid for, and
idle, for the entire duration of the transfer. Three hours of uplink at $1.40/h
is $4.20 of graphics card computing nothing, and until now that was invisible —
the choice of lane was made in the source code, so the price of the choice had
nowhere to appear.

So every estimate here ends in a currency amount, not a duration. A duration is
a fact about a network; a price is a fact the user can act on.

MEASURED, OR HONESTLY GUESSED — AND IT SAYS WHICH
-------------------------------------------------
Uplink speed is the one input that cannot be looked up: it belongs to the
user's line, not to the app or to the pod. So it is MEASURED. Every transfer
this app makes to a pod — the dataset upload, and now the checkpoint push —
records how many bytes went out in how many seconds, and the estimate is the
median of the recent ones. The median rather than the mean because one transfer
throttled by a sick host would otherwise poison every forecast after it.

With no history there is no pretending: the estimate says it is an assumption
and names the number it assumed. A forecast labelled "measured" that was in
fact a guess is worth less than no forecast, because it will be believed.

The samples live in SystemState. They are three integers about the user's own
line, they never leave the machine, and they are worthless to anyone else.
"""
import json
import logging
import statistics
import time

from .. import config as cfg
from ..extensions import db
from ..models import SystemState

logger = logging.getLogger(__name__)

_SAMPLES_KEY = 'cloud_uplink_samples'
_MAX_SAMPLES = 12

# A sample has to be big enough and long enough to be about the LINE rather
# than about a round-trip. A 2 KB token upload measures latency, and letting it
# into the median would forecast a 26 GB transfer from the speed of a
# handshake.
MIN_SAMPLE_BYTES = 32 * 1024 * 1024
MIN_SAMPLE_SECONDS = 2.0

# The fallback when nothing has been measured and nothing configured. Chosen
# LOW on purpose: this number becomes a price, and the direction to be wrong in
# is the one where the transfer turns out cheaper than announced. It is also
# roughly the consumer upstream that still dominates outside fibre.
ASSUMED_UPLINK_MBPS = 50.0

# What the POD's link is worth, for the Hugging Face lane. Not a guess about a
# datacenter in the abstract: it is the floor this app already refuses to rent
# below (cloud.min_inet_down_mbps), so a pod that exists at all is at least
# this fast. Deliberately the floor and not a typical value — same direction of
# error as the uplink assumption.
DEFAULT_POD_DOWNLINK_MBPS = 200.0

# Neither lane is pure transfer. The Hub lane pays a fixed toll for the command
# round-trip and the Hub's own handshake; the direct lane pays for the pod-side
# assembly, which reads and rewrites the whole file on local disk.
_HUB_OVERHEAD_SECONDS = 90
_ASSEMBLE_BYTES_PER_SECOND = 700e6


def _load_samples() -> list:
    row = db.session.get(SystemState, _SAMPLES_KEY)
    if not row or not row.value:
        return []
    try:
        parsed = json.loads(row.value)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [s for s in parsed
            if isinstance(s, dict) and float(s.get('bps') or 0) > 0]


def record_uplink_sample(num_bytes, seconds) -> bool:
    """Remember one measured upload speed. Returns whether it was kept.

    NEVER raises and never rolls anything back the caller cares about: this is
    bookkeeping about a transfer that already succeeded, and a failure to write
    it must not turn a landed 26 GB upload into an error.
    """
    try:
        size = int(num_bytes or 0)
        elapsed = float(seconds or 0)
        if size < MIN_SAMPLE_BYTES or elapsed < MIN_SAMPLE_SECONDS:
            return False
        samples = _load_samples()
        samples.append({'bytes': size, 'seconds': round(elapsed, 2),
                        'bps': size / elapsed, 'at': int(time.time())})
        samples = samples[-_MAX_SAMPLES:]
        row = db.session.get(SystemState, _SAMPLES_KEY)
        if row is None:
            row = SystemState(key=_SAMPLES_KEY)
            db.session.add(row)
        row.value = json.dumps(samples)
        db.session.commit()
        return True
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.debug('could not record an uplink sample', exc_info=True)
        return False


def uplink_bytes_per_second() -> dict:
    """``{'bps', 'source', 'samples', 'mbps'}``.

    ``source`` is 'measured' (this machine's own recent transfers), 'configured'
    (the user told us their uplink) or 'assumed'. The caller SHOWS this word —
    that is the whole point of returning it rather than a bare number.
    """
    configured = 0.0
    try:
        configured = float((cfg.get('cloud') or {}).get('uplink_mbps') or 0)
    except (TypeError, ValueError):
        configured = 0.0
    try:
        samples = _load_samples()
    except Exception:
        logger.debug('uplink samples unreadable', exc_info=True)
        samples = []
    if samples:
        bps = statistics.median(float(s['bps']) for s in samples)
        return {'bps': bps, 'source': 'measured', 'samples': len(samples),
                'mbps': round(bps * 8 / 1e6, 1)}
    if configured > 0:
        bps = configured * 1e6 / 8
        return {'bps': bps, 'source': 'configured', 'samples': 0,
                'mbps': round(configured, 1)}
    bps = ASSUMED_UPLINK_MBPS * 1e6 / 8
    return {'bps': bps, 'source': 'assumed', 'samples': 0,
            'mbps': ASSUMED_UPLINK_MBPS}


def pod_downlink_bytes_per_second() -> float:
    try:
        mbps = float((cfg.get('cloud') or {}).get('min_inet_down_mbps') or 0)
    except (TypeError, ValueError):
        mbps = 0.0
    return (mbps or DEFAULT_POD_DOWNLINK_MBPS) * 1e6 / 8


def _cost(seconds, price_per_hour) -> float:
    return round(max(0.0, float(price_per_hour or 0)) * (seconds / 3600.0), 2)


def estimate_direct(size_bytes, price_per_hour=0.0) -> dict:
    """Sending the file from THIS computer, over the user's uplink."""
    size = max(0, int(size_bytes or 0))
    link = uplink_bytes_per_second()
    transfer = size / link['bps'] if link['bps'] else 0.0
    assemble = size / _ASSEMBLE_BYTES_PER_SECOND
    seconds = transfer + assemble
    return {
        'lane': 'direct',
        'bytes': size,
        'seconds': int(seconds),
        'transfer_seconds': int(transfer),
        'assemble_seconds': int(assemble),
        'rate_bytes_per_second': link['bps'],
        'rate_mbps': link['mbps'],
        'rate_source': link['source'],
        'rate_samples': link['samples'],
        'price_per_hour': round(float(price_per_hour or 0), 4),
        'gpu_cost': _cost(seconds, price_per_hour),
    }


def estimate_hub(size_bytes, price_per_hour=0.0) -> dict:
    """Having the POD pull the file from Hugging Face, over its own link."""
    size = max(0, int(size_bytes or 0))
    bps = pod_downlink_bytes_per_second()
    transfer = size / bps if bps else 0.0
    seconds = transfer + _HUB_OVERHEAD_SECONDS
    return {
        'lane': 'hub',
        'bytes': size,
        'seconds': int(seconds),
        'transfer_seconds': int(transfer),
        'rate_bytes_per_second': bps,
        'rate_mbps': round(bps * 8 / 1e6, 1),
        # Never 'measured': this is the floor the app refuses to rent below,
        # not something observed on this user's runs.
        'rate_source': 'floor',
        'rate_samples': 0,
        'price_per_hour': round(float(price_per_hour or 0), 4),
        'gpu_cost': _cost(seconds, price_per_hour),
    }


def duration_label(seconds) -> str:
    """A duration a human reads without converting. Rounded UP: a forecast that
    rounds 89 minutes down to "1 h" is the kind of small lie that makes the
    whole panel untrustworthy."""
    s = max(0, int(seconds or 0))
    if s < 90:
        return f'{max(1, s)} s'
    minutes = -(-s // 60)
    if minutes < 90:
        return f'{minutes} min'
    hours = s / 3600.0
    return f'{hours:.1f} h'


def size_label(num_bytes) -> str:
    v = float(num_bytes or 0)
    if v < 1e6:
        return f'{v / 1e3:.0f} kB'
    if v < 1e9:
        return f'{v / 1e6:.0f} MB'
    return f'{v / 1e9:.1f} GB'
