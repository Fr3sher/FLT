"""Operator-adjustable budgets, resolved when work starts, with unchanged defaults."""
import math

from . import config as cfg


def _multiplier(kind):
    settings = cfg.get('timeouts')
    raw = settings.get(f'{kind}_multiplier') if isinstance(settings, dict) else None
    try:
        value = float(raw) if not isinstance(raw, bool) else 1.0
    except (TypeError, ValueError, OverflowError):
        return 1.0
    return max(0.1, min(value, 100.0)) if math.isfinite(value) else 1.0


def processing_timeout(seconds):
    """Scale a processing/startup budget; an already unlimited wait stays unlimited."""
    factor = _multiplier('processing')
    return seconds if seconds is None or factor == 1 else seconds * factor


def network_timeout(seconds, *, processing=False):
    """Scale socket waits once, at the transport boundary.

    AI calls use the processing factor for the response and the network factor
    for connecting. Other HTTP calls scale both parts with the network factor.
    Preserve the original scalar/tuple form when no setting changes it.
    """
    factor = _multiplier('network')
    read_factor = _multiplier('processing') if processing else factor
    if factor == read_factor == 1:
        return seconds
    if seconds is None:
        return None
    if isinstance(seconds, (tuple, list)):
        connect, read = seconds
        return (None if connect is None else connect * factor,
                None if read is None else read * read_factor)
    return (seconds * factor, seconds * read_factor) if processing else seconds * factor
