"""Model references use the same search roots and resolution as the LDS UI."""
from app.services.model_integrity import FORM_STRUCTURED


import os


def search_roots(folder_type):
    from app.services import comfy_model_paths
    return comfy_model_paths.search_roots(folder_type)


def scan_family_folders(roots, dir_tokens, *, suffixes):
    from app.services import comfy_model_paths
    return comfy_model_paths.scan_family_folders(roots, dir_tokens, suffixes=suffixes)


def normalize_ref(name, sep=os.sep):
    from app.services.klein_edit_helper import normalize_rel_model_name
    return normalize_rel_model_name(name, sep=sep)


def resolve_ref(folder_type, value):
    """Return (relative loader name, status); only status == 'ok' is usable."""
    from app.services.klein_edit_helper import resolve_model_ref
    return resolve_model_ref(folder_type, value)


def resolve_lora_path(relative_name):
    from app.services.klein_edit_helper import _lora_abs
    return _lora_abs(relative_name)


def resolve_model_file(folder_type, reference):
    from app.services import comfy_model_paths
    return comfy_model_paths.resolve_model_file(folder_type, reference)


def detect_safetensors_arch(keys):
    from app.services.lora_training import _detect_safetensors_arch
    return _detect_safetensors_arch(keys)


def detect_lora_arch(path):
    from app.services import lora_training
    return lora_training.detect_lora_arch(path)


def lora_arch_conflicts(detected, family):
    from app.services import lora_training
    return lora_training.lora_arch_conflicts(detected, family)


def validate_model_file(path, min_bytes=None):
    from app.services import model_integrity
    return model_integrity.validate_model_file(path, min_bytes=min_bytes)


def quantization_report(path):
    from app.services import model_integrity
    return model_integrity.quantization_report(path)


__all__ = ['FORM_STRUCTURED', 'detect_lora_arch', 'detect_safetensors_arch', 'lora_arch_conflicts', 'normalize_ref', 'quantization_report', 'resolve_lora_path', 'resolve_model_file', 'resolve_ref', 'scan_family_folders', 'search_roots', 'validate_model_file']
