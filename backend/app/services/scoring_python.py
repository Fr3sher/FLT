"""Find a Python already on this machine that can run ✨ Score on the GPU.

The scoring extra deliberately installs CPU-only torch (Setup builds it a small
private venv rather than pushing a ~2.5 GB CUDA download on people who have no
card). On a machine that *does* have a card that default costs hours: CLIP
ViT-L/14 measures ~336 ms/image on the CPU against ~15 ms on a recent GPU.

The obvious fix — a button that pip-installs a CUDA torch — is the one we
deliberately do NOT build: it means a 2.5 GB download plus picking a wheel index
against the driver, and getting that wrong is exactly how a `--index-url`
install shredded someone's numpy. The better move is the opposite one: a machine
that trains LoRAs every day ALREADY has a proven CUDA Python (ai-toolkit's venv,
ComfyUI's, a conda env). Point the scoring pass at it instead of building a
third one.

What makes this honest rather than hopeful:

* **Every dependency, not just CUDA.** ``bank_score_infer.py`` needs torch AND
  open_clip AND transformers/timm AND numpy/Pillow. An interpreter with a
  perfect CUDA torch but no ``open_clip`` will die mid-pass. So the probe reports
  a state PER DEPENDENCY and the UI can say "ai-toolkit has CUDA but is missing
  open_clip" instead of an opaque no.
* **Read-only.** We never install anything into an environment we did not build.
  The ai-toolkit venv runs the user's training; silently pip-installing into it
  would be unacceptable. When something is missing we name it and hand over the
  exact command — the user decides.
* **Known candidates only.** Interpreters the app already knows about, plus a
  path the user types. Sweeping the disk would be slow and fragile.
* **Fail safe.** Nothing proven -> nothing changes, and the pass keeps running
  where it runs today. ``select()`` refuses any interpreter it could not verify.

The probe imports ONLY torch (CUDA needs the real module); the other modules are
resolved with ``find_spec``, which is cheap and does not execute them — the whole
check is one short subprocess per interpreter, cached.
"""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import config as cfg

# Everything backend/infer/bank_score_infer.py imports to complete a pass, in
# report order. `pip` is the name to install, `module` is what actually gets
# imported — they differ for three of the six, which is precisely why a
# copy-pasteable command has to be generated rather than guessed.
SCORING_DEPS = (
    {'module': 'torch', 'pip': 'torch', 'label': 'PyTorch'},
    {'module': 'open_clip', 'pip': 'open_clip_torch', 'label': 'OpenCLIP'},
    {'module': 'transformers', 'pip': 'transformers', 'label': 'Transformers'},
    {'module': 'timm', 'pip': 'timm', 'label': 'timm'},
    {'module': 'numpy', 'pip': 'numpy', 'label': 'NumPy'},
    {'module': 'PIL', 'pip': 'Pillow', 'label': 'Pillow'},
)
_DEP_MODULES = tuple(d['module'] for d in SCORING_DEPS)

# A cold `import torch` on a fresh machine (antivirus scanning ~300 MB of native
# DLLs) runs tens of seconds. Generous, because a timeout here reads as "this
# interpreter is unusable" and that would be a lie about a working venv.
PROBE_TIMEOUT = 90
_PROBE_TTL = 600
_probe_cache = {}     # normalised path -> (ts, info|None)

_PROBE_CODE = (
    'import importlib.util as _u, json, sys\n'
    'mods = ' + repr(list(_DEP_MODULES)) + '\n'
    'found = {}\n'
    'for m in mods:\n'
    '    try:\n'
    '        found[m] = _u.find_spec(m) is not None\n'
    '    except Exception:\n'
    '        found[m] = False\n'
    'cuda, device, torch_version = False, None, None\n'
    'if found.get("torch"):\n'
    '    try:\n'
    '        import torch\n'
    '        torch_version = torch.__version__\n'
    '        cuda = bool(torch.cuda.is_available())\n'
    '        if cuda:\n'
    '            device = torch.cuda.get_device_name(0)\n'
    '    except Exception:\n'
    '        found["torch"] = False\n'
    'print(json.dumps({"python": "%d.%d.%d" % sys.version_info[:3],\n'
    '                  "modules": found, "cuda": cuda, "device_name": device,\n'
    '                  "torch_version": torch_version}))\n'
)


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path or '')))


def clear_cache() -> None:
    """Forget every probe result. Called by the rescan action so a user who just
    ran the suggested pip command sees the truth instead of a 10-minute-old
    'missing open_clip'."""
    _probe_cache.clear()


def _run_probe(python: str):
    """Raw probe facts for `python`, or None when we could not learn anything
    (interpreter missing/broken, cold-import timeout, garbage on stdout). None is
    UNKNOWN — never a claim that the interpreter is unusable."""
    try:
        proc = subprocess.run(
            [python, '-c', _PROBE_CODE], capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=PROBE_TIMEOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception:      # noqa: BLE001 — OSError, TimeoutExpired, anything
        return None
    if proc.returncode != 0:
        return None
    try:
        info = json.loads(((proc.stdout or '').strip().splitlines() or [''])[-1])
    except Exception:      # noqa: BLE001
        return None
    return info if isinstance(info, dict) else None


def probe(python: str, force=False):
    """Cached _run_probe. A None result is NOT cached: a cold-import timeout must
    not freeze a working venv into 'unreachable' for ten minutes."""
    key = _norm(python)
    if not key:
        return None
    now = time.time()
    hit = _probe_cache.get(key)
    if hit and not force and (now - hit[0]) < _PROBE_TTL:
        return hit[1]
    info = _run_probe(python)
    if info is not None:
        _probe_cache[key] = (now, info)
    return info


def _quote(p: str) -> str:
    return f'"{p}"' if ' ' in str(p) else str(p)


def describe(python: str, info) -> dict:
    """Turn raw probe facts into the verdict the UI renders.

    status ∈
      'unreachable' — the interpreter did not answer (missing, broken, timeout).
      'incomplete'  — it answered, but the scoring pass would crash on an import.
      'cpu_only'    — every dependency is there, torch just has no usable CUDA.
      'gpu_ready'   — every dependency is there AND torch sees the GPU.

    `missing` names the modules that aren't there and `install_command` is the
    exact line to fix it — we never run it ourselves.
    """
    out = {
        'path': str(python), 'status': 'unreachable', 'cuda': False,
        'device_name': None, 'python_version': None, 'torch_version': None,
        'deps': [dict(d, present=False) for d in SCORING_DEPS],
        'missing': [d['pip'] for d in SCORING_DEPS],
        'install_command': '', 'usable': False, 'gpu': False,
        'detail': 'this interpreter did not answer — check the path',
    }
    if not info:
        return out
    mods = info.get('modules') or {}
    deps = [dict(d, present=bool(mods.get(d['module']))) for d in SCORING_DEPS]
    missing = [d for d in deps if not d['present']]
    out.update({
        'deps': deps,
        'missing': [d['pip'] for d in missing],
        'cuda': bool(info.get('cuda')),
        'device_name': info.get('device_name') or None,
        'python_version': info.get('python') or None,
        'torch_version': info.get('torch_version') or None,
    })
    if missing:
        names = ', '.join(d['label'] for d in missing)
        out['status'] = 'incomplete'
        out['install_command'] = (f'{_quote(python)} -m pip install '
                                  + ' '.join(d['pip'] for d in missing))
        out['detail'] = (
            f'has CUDA but is missing {names}' if out['cuda']
            else f'missing {names}')
        return out
    out['usable'] = True
    if out['cuda']:
        out['status'] = 'gpu_ready'
        out['gpu'] = True
        card = out['device_name'] or 'a CUDA GPU'
        out['detail'] = f'ready — scores on {card}'
    else:
        out['status'] = 'cpu_only'
        out['detail'] = 'ready, but torch here has no usable CUDA — scores on the CPU'
    return out


def _comfyui_pythons() -> list:
    """Interpreter paths a ComfyUI install may use: its own venv, or the portable
    bundle's python_embeded (which sits NEXT TO the ComfyUI folder, not inside)."""
    base = (cfg.get('comfyui.base_dir') or '').strip()
    if not base:
        return []
    root = Path(base)
    exe = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    out = [root / 'venv' / exe, root / '.venv' / exe]
    if os.name == 'nt':
        out += [root / 'python_embeded' / 'python.exe',
                root.parent / 'python_embeded' / 'python.exe']
    return out


def candidates() -> list:
    """Interpreters worth probing, best-known first: [{path, source, label}].

    Deliberately NOT a disk sweep — only Pythons the app already knows about
    (plus whatever the user types, handled by the caller). Deduplicated on the
    normalised path so the currently-selected one doesn't appear twice, and
    filtered to files that exist: an entry we cannot even find is noise, not
    information. The app's own interpreter is always last — it is what runs the
    pass today, so it belongs in the list as the way back."""
    from .. import setup_installer
    seen, out = set(), []

    def add(path, source, label):
        if not path:
            return
        key = _norm(path)
        if not key or key in seen:
            return
        try:
            if not Path(path).is_file():
                return
        except OSError:
            return
        seen.add(key)
        out.append({'path': str(path), 'source': source, 'label': label})

    # The DESCRIPTIVE sources go in first on purpose. The interpreter in use is
    # usually one of them, and "ai-toolkit — the environment that trains your
    # LoRAs" tells the user far more than "currently used": which one is selected
    # is already carried by `selected` (and an "In use" badge). The configured
    # path is added afterwards only when it matches nothing we recognise.
    try:
        add(setup_installer._bank_scoring_env_python(), 'managed',
            "The app's own scoring environment")
    except Exception:      # noqa: BLE001 — a data-dir hiccup must not empty the list
        pass
    try:
        add(cfg.aitoolkit_path('venv_python'), 'aitoolkit',
            'ai-toolkit — the environment that trains your LoRAs')
    except Exception:      # noqa: BLE001
        pass
    for p in _comfyui_pythons():
        add(p, 'comfyui', 'ComfyUI')
    add((cfg.get('masks.python') or '').strip(), 'masks',
        "The app's masking environment")
    add((cfg.get('watermark.python') or '').strip(), 'watermark',
        "The app's inpainting environment")
    add(sys.executable, 'app', "The app's own Python")
    add((cfg.get('bank_scoring.python') or '').strip(), 'configured',
        'Currently used for ✨ Score')
    return out


def detect(force=False, extra_path='') -> dict:
    """The whole picture for the picker: every candidate with its per-dependency
    verdict, which one is selected, and whether the selected one reaches the GPU.

    `extra_path` is a path the user typed — probed like any other candidate and
    reported even when it does not exist (that IS the answer they need). Never
    raises: a candidate that explodes degrades to 'unreachable'."""
    selected = (cfg.get('bank_scoring.python') or '').strip()
    entries = list(candidates())
    typed = (extra_path or '').strip()
    if typed and _norm(typed) not in {_norm(e['path']) for e in entries}:
        entries.append({'path': typed, 'source': 'manual', 'label': 'The path you entered'})
    # Probed in PARALLEL: each candidate costs a cold `import torch`, which is
    # seconds of native-DLL loading (and antivirus scanning) that spends its time
    # in a subprocess, not holding the GIL. Serially, four interpreters made the
    # dialog take the better part of a minute to open for the first time; this
    # makes the wait the slowest one instead of the sum. Order is preserved.
    def probe_one(entry):
        try:
            return describe(entry['path'], probe(entry['path'], force=force))
        except Exception:      # noqa: BLE001 — a broken candidate is a row, not a 500
            return describe(entry['path'], None)

    with ThreadPoolExecutor(max_workers=min(8, len(entries) or 1)) as pool:
        verdicts = list(pool.map(probe_one, entries))
    out = []
    for entry, verdict in zip(entries, verdicts):
        verdict.update(source=entry['source'], label=entry['label'],
                       selected=bool(selected) and _norm(entry['path']) == _norm(selected))
        out.append(verdict)
    return {
        'selected': selected,
        # No explicit selection = the pass runs in the app's own Python. Naming it
        # keeps "what am I on right now" answerable in both states.
        'default_python': sys.executable,
        'interpreters': out,
    }


class SelectionError(ValueError):
    """A refused selection, carrying the verdict so the caller can show WHY."""

    def __init__(self, message, verdict=None):
        super().__init__(message)
        self.verdict = verdict


def select(path: str) -> dict:
    """Point ✨ Score at `path` (or back at the app default when blank).

    Verifies FIRST and refuses anything it could not prove — an interpreter that
    is missing open_clip would fail an hour into a pass. On success the
    capability caches are dropped so ``bank_scoring_gpu_available()`` and the
    Score button agree with the new choice immediately, with no restart."""
    from .. import capabilities
    target = (path or '').strip()
    if not target:
        cfg.save_config({'bank_scoring': {'python': ''}})
        capabilities.clear_import_cache()
        return {'selected': '', 'reverted': True}
    verdict = describe(target, probe(target, force=True))
    if not verdict['usable']:
        if verdict['status'] == 'unreachable':
            raise SelectionError(
                'That path did not answer as a Python interpreter — '
                'nothing was changed.', verdict)
        raise SelectionError(
            f"That Python cannot run ✨ Score: {verdict['detail']}. "
            'Nothing was changed — install the missing packages there first.',
            verdict)
    cfg.save_config({'bank_scoring': {'python': target}})
    capabilities.clear_import_cache()
    return {'selected': target, 'reverted': False, 'verdict': verdict}
