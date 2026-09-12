"""Finishing profile owned by the image improvement product."""
import math
from lds_sdk import config as cfg

def profile(engine) -> dict:
    def _num(key, ceiling):
        try:
            value = float(cfg.get(f'improve.{key}'))
        except (TypeError, ValueError):
            return 0.0
        # NaN has to be rejected BEFORE the clamp, not by it. Every comparison
        # against NaN is False, so `min(ceiling, nan)` returns the CEILING and
        # `max(0.0, ...)` keeps it: a corrupt config.json would not turn the dial
        # off, it would turn it up to maximum. Measured, not theorised.
        if not math.isfinite(value):
            return 0.0
        return max(0.0, min(ceiling, value))
    return {
        'colour_strength': _num('colour_match', 1.0),
        'sharpen': _num('sharpen', 3.0),
        'grain': _num('grain', 0.2),
        'grain_saturation': _num('grain_saturation', 1.0),
    }
