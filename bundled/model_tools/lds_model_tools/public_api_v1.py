"""Version 1 FP8 conversion service; implementation and UI remain Model tools."""
from .fp8_quantize import QuantizeError

API_VERSION = 1
__all__ = ['API_VERSION', 'QuantizeError', 'write_headroom_bytes', 'plan',
           'quantize', 'interpreter', 'status']


def write_headroom_bytes():
    from . import fp8_quantize
    return fp8_quantize.WRITE_HEADROOM_BYTES


def plan(source, *, overwrite=False, destination=None):
    from .fp8_quantize import plan as operation
    return operation(source, overwrite=overwrite, destination=destination)


def quantize(source, *, overwrite=False, destination=None, progress=None, cancelled=None):
    from .fp8_quantize import quantize as operation
    return operation(source, overwrite=overwrite, destination=destination,
                     progress=progress, cancelled=cancelled)


def interpreter():
    from .fp8_quantize import interpreter as operation
    return operation()


def status():
    from .fp8_quantize import status as operation
    return operation()
