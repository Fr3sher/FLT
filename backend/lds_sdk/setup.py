"""Read the public host installation catalog; the caller owns its setup UI."""
from app.setup_installer import AlreadyRunning

def resolve_install_folder(path):
    from app.capabilities import resolve_comfyui_base
    return resolve_comfyui_base(path)

def known_action(action):
    from app import setup_installer as host
    operation = getattr(host, 'known_action', None)
    return operation(action) if operation else action in host._WORKERS

def start(action):
    from app.setup_installer import start as operation
    return operation(action)

def model_download_spec(action):
    from app import setup_installer as host
    operation = getattr(host, 'model_download_spec', None)
    return operation(action) if operation else host._MODEL_DOWNLOADS[action]

__all__ = ['AlreadyRunning', 'resolve_install_folder', 'known_action', 'start', 'model_download_spec']
