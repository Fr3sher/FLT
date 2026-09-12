"""API 1.9: bounded local render discovery for image restoration products."""


def gpu_vram_gb():
    from app.capabilities import gpu_vram_gb as operation
    return operation()


def resolve_comfyui_base(path):
    from app.capabilities import resolve_comfyui_base as operation
    return operation(path)


def fetch_object_info_classes():
    from app.utils.comfyui import fetch_object_info_classes as operation
    return operation()


def visual_size_from_header(image):
    from app.services.image_encoding import visual_size_from_header as operation
    return operation(image)


def comfyui_reachable():
    from app.capabilities import probe_comfyui
    return bool(probe_comfyui().get('ok'))


__all__ = ['comfyui_reachable', 'fetch_object_info_classes', 'gpu_vram_gb', 'resolve_comfyui_base', 'visual_size_from_header']
