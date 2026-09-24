"""Shared FP8 artifact utility; conversion policy stays with the calling product."""

from app.services.fp8_export import Fp8ExportError, PROGRESS_PREFIX, RESULT_PREFIX

__all__ = ['Fp8ExportError', 'PROGRESS_PREFIX', 'RESULT_PREFIX', 'read_header',
           'plan_quantization', 'fp8_name_for', 'verify_export', 'worker_script',
           'estimate_fp8_bytes', 'typical_fp8_bytes']


def read_header(path):
    from app.services import fp8_export
    return fp8_export.read_header(path)


def plan_quantization(header):
    from app.services import fp8_export
    return fp8_export.plan_quantization(header)


def fp8_name_for(source_name):
    from app.services import fp8_export
    return fp8_export.fp8_name_for(source_name)


def verify_export(path):
    from app.services import fp8_export
    return fp8_export.verify_export(path)


def worker_script():
    """Host-supplied standalone utility path, for the chosen worker interpreter."""
    from app.services import fp8_export
    return fp8_export.__file__


def estimate_fp8_bytes(header):
    from app.services.fp8_export import estimate_fp8_bytes as operation
    return operation(header)


def typical_fp8_bytes(size_bytes):
    from app.services.fp8_export import typical_fp8_bytes as operation
    return operation(size_bytes)
