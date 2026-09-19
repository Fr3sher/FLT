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


def missing_modules(names):
    """API 1.20: inspect top-level Python module presence without importing it.

    This is a presence hint, not proof that native libraries can load. Dotted
    names are rejected because find_spec may import their parent package.
    """
    import importlib.util
    import re
    if not isinstance(names, (tuple, list)) or len(names) > 64:
        raise ValueError('Expected up to 64 top-level Python module names.')
    if any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_]\w*', name, re.ASCII)
           for name in names):
        raise ValueError('Expected top-level Python module names, not paths or submodules.')
    missing = []
    for name in names:
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)
    return missing


__all__ = ['AlreadyRunning', 'resolve_install_folder', 'known_action', 'start', 'model_download_spec',
           'missing_modules']


def bundled_node_pack_files(action):
    """Bytes of a registered local node pack, independent of its install path."""
    from pathlib import Path
    from app import setup_installer
    if action not in setup_installer._BUNDLED_NODE_PACKS:
        raise ValueError('Unknown bundled node pack.')
    root = Path(setup_installer._bundled_pack_source(action))
    return {path.name: path.read_bytes() for path in sorted(root.glob('*.py'))}


def bundled_node_pack_name(action):
    """Stable install folder of a known host-supplied rendering primitive."""
    from app import setup_installer
    try:
        return setup_installer._BUNDLED_NODE_PACKS[action]['folder']
    except KeyError:
        raise ValueError('Unknown bundled node pack.') from None
