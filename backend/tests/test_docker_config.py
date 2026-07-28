"""Static contracts shared by the app and its development entrypoints."""
import importlib.util
import json
import re
from pathlib import Path

from app.config import DEFAULTS


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path):
    return (REPO_ROOT / relative_path).read_text(encoding='utf-8')


def _docker_env(dockerfile):
    """Return ENV assignments regardless of single or continued-line layout."""
    logical_lines = dockerfile.replace('\\\n', ' ')
    assignments = {}
    for line in logical_lines.splitlines():
        if not line.startswith('ENV '):
            continue
        for key, value in re.findall(r'([A-Z][A-Z0-9_]*)=([^\s]+)', line[4:]):
            assignments[key] = value
    return assignments


def _shell_statements(script):
    """A shell script's executable lines: comments and blanks dropped."""
    return [line.strip() for line in script.splitlines()
            if line.strip() and not line.strip().startswith('#')]


def _load_script_module(name):
    """Import one of packaging/docker's standalone boot scripts by path. They sit
    outside the `app` package on purpose — they run under the container's system
    python, before any venv is active — so there is no import path to them."""
    path = REPO_ROOT / 'packaging' / 'docker' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(f'lds_docker_{name}', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_container_runtime_tracks_server_defaults():
    """The image must work both directly and through Docker Compose."""
    server = DEFAULTS['server']
    port = server['port']
    dockerfile = (REPO_ROOT / 'Dockerfile').read_text(encoding='utf-8')
    compose = _read('docker-compose.yml')
    image_env = _docker_env(dockerfile)

    assert image_env['LDS_DATA_DIR'] == '/data'
    assert image_env['LDS_CONFIG'] == '/data/config.json'
    assert image_env['LDS_HOST'] == '0.0.0.0'
    assert image_env['LDS_PORT'] == str(port)
    assert f'EXPOSE {port}' in dockerfile
    assert f'http://127.0.0.1:{port}/api/health' in dockerfile
    assert f'ports: ["{port}:{port}"]' in compose
    assert f'LDS_PORT={port}' in compose
    assert 'LDS_HOST=0.0.0.0' in compose
    assert 'LDS_CONFIG=/data/config.json' in compose


def test_developer_entrypoints_track_server_default():
    """Examples and the Vite proxy must follow the backend's real default port."""
    port = DEFAULTS['server']['port']
    example = json.loads(_read('config.example.json'))
    vite = _read('frontend/vite.config.js')

    assert example['server']['port'] == port

    # The proxy target is no longer a literal on the '/api' line — it is an
    # env-var override falling back to a named default, so that `npm run dev`
    # stops driving the real install by accident. What must still hold is the
    # thing this test was written for: that FALLBACK has to track the backend's
    # own default port, or the habit ("npm run dev", hit :5173) silently breaks.
    assert re.search(r"['\"]\/api['\"]\s*:", vite), 'Vite must declare an /api proxy'
    default = re.search(
        r"DEFAULT_DEV_API_TARGET\s*=\s*['\"]http:\/\/127\.0\.0\.1:(\d+)", vite)
    assert default, 'Vite must keep a named loopback default for /api'
    assert int(default.group(1)) == port


def test_docker_context_excludes_generated_artifacts():
    ignored = {
        line.strip().rstrip('/')
        for line in _read('.dockerignore').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }

    assert {'.worktrees', '.pytest_cache', 'packaging/build', 'packaging/dist'} <= ignored


def test_launcher_can_never_abort_the_upstream_boot():
    """Upstream's run_userscript does `$script || error_exit`, so a non-zero exit
    from the launcher kills the container's ComfyUI too. A studio problem must
    cost the studio only."""
    script = _read('packaging/docker/studio_launch.sh')
    statements = _shell_statements(script)

    assert script.startswith('#!/bin/bash')
    # The last thing the script DOES, not the last bytes of the file: a trailing
    # comment reading "exit 0" would satisfy endswith() and prove nothing.
    assert statements[-1] == 'exit 0'
    # Prose is free to name `set -e`; only a statement that enables it is the defect.
    assert not [line for line in statements if line.startswith('set -e')]
    assert '/app/.venv/bin/python' in script
    assert 'seed_comfy_config.py' in script
    # The studio is a background job beside ComfyUI's foreground process, so the
    # launcher has to be its own supervisor.
    assert [line for line in statements if line.startswith('while true')]


def test_healthcheck_covers_both_halves_of_the_gpu_image(monkeypatch):
    """One container, two services: a live ComfyUI with a dead studio is a broken
    stack, and Docker only gets one exit code to say so in. Imported rather than
    grepped, so an endpoint only counts if it is actually wired into TARGETS."""
    monkeypatch.delenv('LDS_PORT', raising=False)
    healthcheck = _load_script_module('healthcheck')
    targets = dict(healthcheck.TARGETS)

    assert f":{DEFAULTS['server']['port']}/api/health" in targets['studio']
    assert ':8188/system_stats' in targets['comfyui']


def test_gpu_image_layers_on_the_comfyui_base_without_hijacking_it():
    """Dockerfile.gpu is a layer on someone else's image. Three of its rules are
    invisible in a diff and fatal at runtime, so they are asserted here."""
    dockerfile = _read('Dockerfile.gpu')
    image_env = _docker_env(dockerfile)
    port = DEFAULTS['server']['port']

    assert 'mmartial/comfyui-nvidia-docker' in dockerfile
    assert image_env['LDS_DATA_DIR'] == '/data'
    assert image_env['LDS_CONFIG'] == '/data/config.json'
    assert image_env['LDS_HOST'] == '0.0.0.0'
    assert image_env['LDS_PORT'] == str(port)
    assert f'EXPOSE {port}' in dockerfile
    assert 'EXPOSE 8188' in dockerfile

    logical = [line.strip()
               for line in dockerfile.replace('\\\n', ' ').splitlines()
               if line.strip()]

    # 1. Upstream's ENTRYPOINT (/comfyui-nvidia_init.bash) must stay in charge.
    assert not [line for line in logical
                if line.startswith('ENTRYPOINT') or line.startswith('CMD ')]
    # 2. The container starts as comfytoo and upstream's init script remaps comfy
    #    to WANTED_UID before switching to it.
    assert logical[-1] == 'USER comfytoo'
    # 3. ComfyUI's venv activation must keep winning; the studio is only ever
    #    invoked through absolute paths.
    assert not [line for line in logical if line.startswith('ENV PATH')]

    # /userscripts_dir/*.sh run in "skip" mode: not executable means not run.
    assert 'install -D -m 755 packaging/docker/studio_launch.sh' in dockerfile
    assert '/userscripts_dir/50-lora-dataset-studio.sh' in dockerfile
    # The studio's venv must never be ComfyUI's.
    assert '/app/.venv' in dockerfile


def test_gpu_compose_publishes_both_uis_and_reserves_the_gpu():
    compose = _read('docker-compose.gpu.yml')
    port = DEFAULTS['server']['port']

    assert 'dockerfile: Dockerfile.gpu' in compose
    assert f'"${{LDS_HOST_PORT:-{port}}}:{port}"' in compose
    assert '"${LDS_COMFY_HOST_PORT:-8188}:8188"' in compose
    for mount in (':/comfy/mnt', ':/basedir', ':/data', './.env:/app/.env'):
        assert mount in compose, mount
    assert 'driver: nvidia' in compose
    assert re.search(r'capabilities:\s*\[\s*gpu', compose)
    assert 'WANTED_UID=' in compose and 'WANTED_GID=' in compose
    assert f'LDS_PORT={port}' in compose
    assert 'LDS_HOST=0.0.0.0' in compose
    assert 'LDS_CONFIG=/data/config.json' in compose

    # LDS_PORT is the port the app BINDS INSIDE the container. Interpolating it on
    # the host side of a mapping would publish a port nothing serves.
    assert '${LDS_PORT' not in compose
