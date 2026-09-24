"""Convert single-file ComfyUI Z-Image checkpoints to ai-toolkit diffusers
format for custom-merge LoRA training.

Run convert_comfy_zimage_to_diffusers.py with ai-toolkit Python and
diffusers, using the validated official ComfyUI mapping. Conversion
writes about 12 GB over several minutes, once per cached base, in a
background thread under <aitoolkit dir>/converted/<name>/.

Ported from the parent application. Former machine-specific module
constants are now live cfg-backed accessors, and converted cache data
lives under the configured ai-toolkit directory."""
from __future__ import annotations
from ..timeout_settings import processing_timeout

import glob
import logging
import os
import subprocess
import threading

from .. import config as cfg
from ..job_queue import queue_manager
from ..utils.comfy_names import local_model_path
from . import infer_env
from .lora_training import (_aitoolkit_dir, _hf_home, _venv_python,
                            assert_free_disk, MIN_FREE_GB_CONVERT)

logger = logging.getLogger(__name__)

_CONVERTER = str(cfg.BACKEND_DIR / 'infer' / 'convert_comfy_zimage_to_diffusers.py')
_CONVERT_KEY = 'zimage_base_convert'  # system_state: current conversion status
_convert_lock = threading.Lock()      # Serialize acquisition of the conversion lock.


def _converted_root():
    return _aitoolkit_dir() / 'converted'


def _official_config() -> str | None:
    """Official Z-Image-Turbo transformer config.json in ai-toolkit's HF cache,
    available after the first official-base training run."""
    g = glob.glob(os.path.join(str(_hf_home()), 'hub', 'models--Tongyi-MAI--Z-Image-Turbo',
                               'snapshots', '*', 'transformer', 'config.json'))
    return g[0] if g else None


def _is_absolute_anywhere(path) -> bool:
    """Absolute on ANY platform, not just the host: a Windows drive path
    (``C:\\...``) is a custom-weights value that must read as absolute even when
    this app runs on Linux (os.path.isabs only knows the host's scheme)."""
    path = str(path)
    return os.path.isabs(path) or bool(_WINDOWS_ABS_RE.match(path))


_WINDOWS_ABS_RE = __import__('re').compile(r'^[A-Za-z]:[\\/]|^\\\\')


def _resolve_merge(z_model: str) -> str | None:
    """Resolve an absolute local safetensors path from a ComfyUI z_model value.
    Reject absolute input and traversal (..); lexically confine candidate
    paths to model roots. Check commonpath before realpath so legitimate
    Windows junctions across drives do not raise mismatched-drive errors.
    Use realpath only for existence and the path returned to the worker.

    Le confinement est vérifié LEXICALEMENT sur `cand` (construit sous root_real
    à partir d'une valeur sans '..' ni chemin absolu) : il reste sur le même
    disque, donc commonpath ne crashe jamais. On NE fait PAS commonpath sur le
    realpath : celui-ci peut légitimement traverser un disque via une jonction
    Windows (models/ symlinké vers un 2e DD, cas courant pour les gros modèles),
    ce qui levait `ValueError: Paths don't have the same drive` et cassait la
    conversion. realpath ne sert donc qu'à tester l'existence et à retourner le
    chemin réel dont le sous-process a besoin.

    Les racines fouillées sont celles de ComfyUI lui-même — ``<base>/models/{unet,
    diffusion_models}`` PLUS toute racine ``diffusion_models`` déclarée dans
    ``extra_model_paths.yaml`` — dans l'ordre de priorité de ComfyUI (``is_default``
    d'abord). Avant ce correctif, un merge Z-Image rangé sous une racine yaml était
    tout simplement inconvertible : présent sur le disque, chargé par ComfyUI tous
    les jours, et « base model not found on disk » ici. `unet` et `diffusion_models`
    ne sont plus deux dossiers en dur mais le MÊME type canonique côté ComfyUI
    (folder_paths.map_legacy), ce que ``search_roots`` applique déjà.

    Sans yaml, les racines sont exactement les deux dossiers historiques, dans le
    même ordre : la résolution est inchangée au bit près."""
    if not z_model or _is_absolute_anywhere(z_model) or '..' in z_model.replace('\\', '/'):
        return None
    if not cfg.comfyui_dir('models'):
        return None
    # Use local filesystem separators, not literal ComfyUI widget backslashes.
    # On Linux a backslash becomes part of one filename, yielding a missing
    # model rather than a directory path (GitHub #21).
    rel = local_model_path(z_model)
    base = os.path.basename(rel)
    from . import comfy_model_paths
    roots = comfy_model_paths.search_roots('diffusion_models')
    for root in roots:
        root_real = os.path.realpath(str(root))
        root_key = os.path.normcase(os.path.normpath(root_real))
        for want in (rel, os.path.join('z image', base)):
            cand = os.path.join(root_real, want)
            cand_key = os.path.normcase(os.path.normpath(cand))
            if os.path.commonpath([root_key, cand_key]) != root_key:
                continue
            real = os.path.realpath(cand)
            if os.path.isfile(real):
                return real
    # Second pass ignores case: persisted picker/template casing can differ
    # from disk. Windows tolerates that; Linux/cloud training does not.
    for root in roots:
        root_real = os.path.realpath(str(root))
        for want in (rel, os.path.join('z image', base)):
            hit = comfy_model_paths.ci_resolve(root_real, want)
            if hit:
                real = os.path.realpath(hit)
                if os.path.isfile(real):
                    return real
    return None


def _safe_name(z_model: str) -> str:
    """Derive the conversion directory name from the full relative path,
    including subdirectories, so same-basename merges do not overwrite
    each other's cached conversions."""
    rel = z_model.replace('\\', '/').rsplit('.', 1)[0]
    safe = ''.join(c if (c.isalnum() or c in '_-') else '_' for c in rel).strip('_')
    return safe or 'base'


def converted_dir(z_model: str) -> str:
    return str(_converted_root() / _safe_name(z_model))


def is_converted(z_model: str) -> bool:
    d = os.path.join(converted_dir(z_model), 'transformer')
    return (os.path.isfile(os.path.join(d, 'diffusion_pytorch_model.safetensors'))
            and os.path.isfile(os.path.join(d, 'config.json')))


def convert(z_model: str) -> str:
    """Blocking conversion, taking several minutes. Return the diffusers root
    for name_or_path; raise ValueError on failure."""
    if is_converted(z_model):
        return converted_dir(z_model)
    merge = _resolve_merge(z_model)
    if not merge:
        raise ValueError(f'base model not found on disk: {z_model}')
    official_config_path = _official_config()
    if not official_config_path:
        raise ValueError("config.json for Z-Image-Turbo is missing from the HF cache - first run "
                         "a training on the official base (this downloads the model)")
    out = converted_dir(z_model)
    os.makedirs(out, exist_ok=True)
    logger.info(f'base conversion {z_model} -> {out}')
    proc = subprocess.run(infer_env.worker_argv(_venv_python(), _CONVERTER, merge,
                                                official_config_path, '--save', out),
                          capture_output=True, text=True, timeout=processing_timeout(2400),
                          env=infer_env.worker_env(_venv_python()))
    if not is_converted(z_model):
        tail = (proc.stdout or '')[-600:] + ' | ' + (proc.stderr or '')[-600:]
        raise ValueError(f'conversion failed: {tail}')
    return out


# Background conversion and status for UI polling.
def convert_status() -> dict:
    return queue_manager._get_system_state(_CONVERT_KEY, {}) or {}


def start_convert_async(app, z_model: str) -> None:
    """Start daemon-thread conversion, tracking running/done/error in
    system_state. Reject if conversion is already running."""
    if not _resolve_merge(z_model):
        raise ValueError(f'base model not found: {z_model}')
    # About 12 GB will be written: reject insufficient space before starting,
    # rather than failing at 90% with an invalid cache consuming 10 GB.
    assert_free_disk(_converted_root(), MIN_FREE_GB_CONVERT, 'the base conversion (~12 GB)')
    # Atomic check-and-set under the lock prevents concurrent 12 GB
    # conversions from double clicks or simultaneous datasets.
    with _convert_lock:
        if convert_status().get('status') == 'running':
            raise ValueError('a conversion is already in progress')
        queue_manager._set_system_state(_CONVERT_KEY, {'z_model': z_model, 'status': 'running'},
                                        ttl_seconds=3600)

    def _run():
        with app.app_context():
            try:
                convert(z_model)
                queue_manager._set_system_state(
                    _CONVERT_KEY, {'z_model': z_model, 'status': 'done'}, ttl_seconds=3600)
                logger.info(f'base conversion completed: {z_model}')
            except Exception as e:
                queue_manager._set_system_state(
                    _CONVERT_KEY, {'z_model': z_model, 'status': 'error', 'error': str(e)},
                    ttl_seconds=3600)
                logger.error(f'base conversion failed ({z_model}) : {e}')

    threading.Thread(target=_run, daemon=True).start()
