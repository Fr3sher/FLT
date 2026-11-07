from flask import jsonify

def _seedvr2_missing_response(e):
    """Turn a SeedVR2ModelsMissing into a structured 409, in the same
    `{files, nodes, node_packs}` vocabulary as the Krea one so a single banner
    renders every engine.

    The one real difference is the node pack: this app INSTALLS Krea's (it has no
    pip dependencies) and deliberately does NOT install this one, whose thirteen
    dependencies belong in ComfyUI's interpreter (see seedvr2_helper's module
    docstring). So the weights auto-start exactly like Klein's and Krea's, and
    the pack gets an instruction naming ComfyUI-Manager — the tool that installs
    a pack's requirements properly."""
    from lds_sdk import local_render as capabilities, config as cfg
    from . import seedvr2_helper as svr
    files = svr.missing_file_entries(e.missing)
    node_packs = svr.seedvr2_node_hints(e.missing_nodes)
    dir_valid = capabilities.resolve_comfyui_base(cfg.get('comfyui.base_dir') or '')['valid']
    started = _autostart_seedvr2_downloads(e.missing) if dir_valid else []
    parts = ["SeedVR2 can't run yet."]
    if not dir_valid:
        parts.append('Point the app at your ComfyUI install folder in Setup ▸ ComfyUI '
                     'and the app can download the weights for you; until then, by hand:')
    if e.missing_nodes:
        if svr.seedvr2_node_pack_installed():
            # On disk, absent from /object_info: the ONE thing no installer can do.
            parts.append(
                f"The “{svr.SEEDVR2_NODE_PACK['pack']}” node pack is already installed "
                "but ComfyUI has not loaded it — RESTART ComfyUI (it only registers "
                "custom nodes at startup). If it still doesn't appear, its Python "
                "dependencies failed to install: check ComfyUI's console.")
        else:
            parts.append(
                f"Install the “{svr.SEEDVR2_NODE_PACK['pack']}” custom-node pack in "
                f"ComfyUI (search “{svr.SEEDVR2_NODE_PACK['search']}” in ComfyUI-Manager, "
                f"or clone {svr.SEEDVR2_NODE_PACK['url']} and install its "
                "requirements.txt), then restart ComfyUI — it provides "
                f"{', '.join(e.missing_nodes)}.")
    if started:
        names = ', '.join(svr.SEEDVR2_ASSETS[a]['kind'] for a in started
                          if a in svr.SEEDVR2_ASSETS)
        parts.append(f"I've started downloading {names} into your ComfyUI folder "
                     "(~3.9 GB in total) — watch progress in Setup ▸ ComfyUI.")
    else:
        # Nothing could be started: the by-hand answer is still owed in full.
        for f in files:
            parts.append(f"Missing {f['kind']}: place it at {f['path']} inside your "
                         f"ComfyUI folder (from {f['source']}).")
    parts.append('Then retry.')
    return jsonify({'ok': False, 'error': ' '.join(parts),
                    'downloading': started,
                    'seedvr2_missing': {'assets': e.missing, 'files': files,
                                        'nodes': e.missing_nodes,
                                        'node_packs': node_packs}}), 409


def _autostart_seedvr2_downloads(missing):
    """Start the weight downloads that close a SeedVR2 preflight miss. Returns the
    actions actually started; never raises, so a download that can't start leaves
    the manual instructions standing."""
    from lds_sdk import setup as setup_installer
    started = []
    for action in (missing or []):
        if not setup_installer.known_action(action):
            continue
        try:
            setup_installer.start(action)
            started.append(action)
        except Exception:   # noqa: BLE001 — already running / disk precondition
            continue
    return started


def error_response(error):
    from .seedvr2_helper import SeedVR2ModelsMissing
    return _seedvr2_missing_response(error) if isinstance(error, SeedVR2ModelsMissing) else None
