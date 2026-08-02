"""End-to-end launcher tests using a stateful fake Docker executable.

The real Docker daemon is never contacted.  The common PowerShell launcher and
its child helpers are exercised from a throw-away checkout instead.
"""

import itertools
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
POWERSHELL = shutil.which("powershell.exe")
LAUNCHER_FILES = (
    ".env.example",
    "docker-compose.yml",
    "docker-compose.gpu.yml",
    "docker-compose.external-comfy.yml",
    "docker-compose.ollama-host.yml",
    "docker-compose.ollama-sidecar.yml",
    "docker-compose.ollama-gpu.yml",
    "scripts/docker-launch.ps1",
    "scripts/docker-launch-inspect.ps1",
    "scripts/docker-ollama-mode.ps1",
    "scripts/configure-external-comfy.ps1",
)


FAKE_DOCKER = r'''import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["FAKE_DOCKER_STATE"])
log_path = Path(os.environ["FAKE_DOCKER_LOG"])
state = json.loads(state_path.read_text(encoding="utf-8"))
args = sys.argv[1:]


def save():
    state_path.write_text(json.dumps(state), encoding="utf-8")


with log_path.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({
        "args": args,
        "bind_address": os.environ.get("LDS_BIND_ADDRESS"),
        "host_port": os.environ.get("LDS_HOST_PORT"),
        "comfy_port": os.environ.get("LDS_COMFY_HOST_PORT"),
        "data": os.environ.get("LDS_DATA"),
        "comfy_run": os.environ.get("LDS_COMFY_RUN"),
        "comfy_basedir": os.environ.get("LDS_COMFY_BASEDIR"),
        "bank_sources": os.environ.get("LDS_BANK_SOURCES"),
    }) + "\n")

if args == ["compose", "version"]:
    print("Docker Compose version v2.fake")
    raise SystemExit(0)

if args == ["info"]:
    remaining = int(state.get("info_failures_remaining", 0))
    if remaining:
        state["info_failures_remaining"] = remaining - 1
        save()
        print("Docker Desktop is starting", file=sys.stderr)
        raise SystemExit(1)
    print("fake engine ready")
    raise SystemExit(0)

if len(args) >= 4 and args[:3] == ["inspect", "--type", "container"]:
    name = args[3]
    project = state["project"]
    if name == project:
        if not state.get("studio_running"):
            print(f"Error: No such container: {name}", file=sys.stderr)
            raise SystemExit(1)
        labels = {
            "com.docker.compose.project": state.get("studio_label_project", project),
            "com.docker.compose.service": "studio",
            "com.docker.compose.project.working_dir": state["repo"],
            "io.lora-dataset-studio.launch-mode": state["launch_mode"],
        }
        bind_address = state.get("bind_address", "127.0.0.1")
        secondary_bind = "::1" if bind_address == "127.0.0.1" else "::"
        ports = {
            "5050/tcp": [
                {"HostIp": bind_address, "HostPort": str(state["app_port"])},
                {"HostIp": secondary_bind, "HostPort": str(state["app_port"])},
            ]
        }
        if state["stack"] == "gpu":
            ports["8188/tcp"] = [
                {"HostIp": bind_address, "HostPort": str(state["comfy_port"])},
                {"HostIp": secondary_bind, "HostPort": str(state["comfy_port"])},
            ]
        payload = [{
            "Config": {"Labels": labels},
            "State": {"Status": "running"},
            "NetworkSettings": {"Ports": ports},
        }]
        print(json.dumps(payload))
        raise SystemExit(0)

    if name == project + "-ollama":
        if not state.get("sidecar_running"):
            print(f"Error: No such container: {name}", file=sys.stderr)
            raise SystemExit(1)
        labels = {
            "com.docker.compose.project": project,
            "com.docker.compose.service": "ollama",
            "com.docker.compose.project.working_dir": state["repo"],
        }
        role = state.get("sidecar_role", "ollama")
        if role is not None:
            labels["io.lora-dataset-studio.role"] = role
        print(json.dumps([{
            "Config": {"Labels": labels},
            "State": {"Status": "running"},
            "NetworkSettings": {"Ports": {}},
        }]))
        raise SystemExit(0)

    print(f"Error: No such object: {name}", file=sys.stderr)
    raise SystemExit(1)

if len(args) >= 4 and args[:2] == ["inspect", "--format"]:
    health_sequence = state.get("health_sequence", [])
    if health_sequence:
        health = health_sequence.pop(0)
        state["health_sequence"] = health_sequence
        state["health"] = health
        save()
    else:
        health = state.get("health", "healthy")
    print("running|" + health)
    raise SystemExit(0)

if args and args[0] == "compose":
    if "config" in args:
        raise SystemExit(0)

    if "up" in args and args[-1] == "studio":
        state["studio_running"] = True
        state["bind_address"] = os.environ.get("LDS_BIND_ADDRESS", "127.0.0.1")
        selected_mode = state.get("mode_after_studio_up")
        if selected_mode:
            data_name = "data-docker-gpu" if state["stack"] == "gpu" else "data-docker"
            config = Path(state["repo"], data_name, "config.json")
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text(json.dumps({
                "ollama": {"deployment_mode": selected_mode},
                "secret_token": "never-print-this",
            }), encoding="utf-8")
        save()
        raise SystemExit(0)

    if "up" in args and args[-1] == "ollama":
        gpu_overlay = any(value.endswith("docker-compose.ollama-gpu.yml") for value in args)
        if (state.get("fail_gpu_ollama") and gpu_overlay
                and "--force-recreate" not in args):
            state["gpu_ollama_failed_once"] = True
            save()
            print("fake NVIDIA failure", file=sys.stderr)
            raise SystemExit(1)
        state["sidecar_running"] = True
        state["sidecar_role"] = "ollama"
        save()
        raise SystemExit(0)

    if "stop" in args and args[-1] == "ollama":
        state["sidecar_running"] = False
        save()
        raise SystemExit(0)

    if "logs" in args:
        raise SystemExit(0)

if args and args[0] == "exec":
    raise SystemExit(0)

print("unsupported fake docker call: " + repr(args), file=sys.stderr)
raise SystemExit(2)
'''


def _copy_launcher_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "test neuf é avec espaces"
    for relative in LAUNCHER_FILES:
        source = REPO_ROOT / relative
        destination = checkout / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    comfy = tmp_path / "Portable ! % & '$ ${X}" / "ComfyUI"
    comfy.mkdir(parents=True)
    (comfy / "main.py").write_text("# fake\n", encoding="utf-8")
    (comfy / "models").mkdir()
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-STA",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(checkout / "scripts" / "configure-external-comfy.ps1"),
            "-Configure",
            "-CandidatePath",
            str(comfy),
            "-OverridePath",
            str(checkout / ".docker-compose.external-comfy.override.yml"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "STATE=SAVED"
    return checkout


def _make_fake_docker(tmp_path: Path):
    fake_python = tmp_path / "fake_docker.py"
    fake_python.write_text(FAKE_DOCKER, encoding="utf-8")
    fake_ps1 = tmp_path / "fake docker.ps1"
    fake_ps1.write_text(
        "param([Parameter(ValueFromRemainingArguments=$true)]"
        "[string[]]$DockerArguments)\n"
        "$utf8 = New-Object System.Text.UTF8Encoding($false)\n"
        "[Console]::OutputEncoding = $utf8\n"
        "& $env:FAKE_PYTHON_EXE $env:FAKE_DOCKER_SCRIPT @DockerArguments\n",
        encoding="utf-8",
    )
    return fake_ps1, fake_python


def _write_mode(checkout: Path, stack: str, mode: str):
    data_name = "data-docker-gpu" if stack == "gpu" else "data-docker"
    config = checkout / data_name / "config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps({
            "ollama": {"deployment_mode": mode},
            "secret_token": "never-print-this",
        }),
        encoding="utf-8",
    )


def _run_launcher(
    tmp_path: Path,
    stack: str,
    mode=None,
    *,
    launcher_env=None,
    switches=(),
    state_changes=None,
):
    if POWERSHELL is None:
        pytest.skip("Windows PowerShell 5.1 is unavailable")
    checkout = _copy_launcher_checkout(tmp_path)
    if mode is not None:
        _write_mode(checkout, stack, mode)

    fake_ps1, fake_python = _make_fake_docker(tmp_path)
    project = "lora-dataset-studio-gpu" if stack == "gpu" else "lora-dataset-studio"
    state = {
        "repo": str(checkout.resolve()),
        "stack": stack,
        "project": project,
        "launch_mode": "gpu" if stack == "gpu" else "external",
        "studio_running": False,
        "sidecar_running": False,
        "bind_address": "127.0.0.1",
        "app_port": 5067 if stack == "gpu" else 5073,
        "comfy_port": 8201,
        "health": "healthy",
    }
    state.update(state_changes or {})
    state_path = tmp_path / "fake-state.json"
    log_path = tmp_path / "fake-docker.jsonl"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    log_path.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "LDS_DOCKER_EXE": str(fake_ps1),
        "LDS_TEST_MODE": "1",
        "FAKE_PYTHON_EXE": sys.executable,
        "FAKE_DOCKER_SCRIPT": str(fake_python),
        "FAKE_DOCKER_STATE": str(state_path),
        "FAKE_DOCKER_LOG": str(log_path),
        "LDS_DOCKER_DESKTOP_EXE": str(Path(os.environ["SystemRoot"]) / "System32" / "whoami.exe"),
        "LDS_DATA": "C:/must-not-be-shared/data",
        "LDS_COMFY_RUN": "C:/must-not-be-shared/run",
        "LDS_COMFY_BASEDIR": "C:/must-not-be-shared/models",
        "LDS_BANK_SOURCES": "C:/must-not-be-shared/images",
    })
    env.pop("LDS_HOST_PORT", None)
    env.pop("LDS_COMFY_HOST_PORT", None)
    env.pop("LDS_BIND_ADDRESS", None)
    env.update(launcher_env or {})

    command = [
        POWERSHELL,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-STA",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(checkout / "scripts" / "docker-launch.ps1"),
        "-Stack",
        stack,
        *switches,
    ]
    result = subprocess.run(
        command,
        cwd=checkout,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    final_state = json.loads(state_path.read_text(encoding="utf-8"))
    calls = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    return checkout, result, final_state, calls


def _compose_calls(calls, action, service):
    return [
        call for call in calls
        if call["args"]
        and call["args"][0] == "compose"
        and action in call["args"]
        and call["args"][-1] == service
    ]


@pytest.mark.parametrize(
    ("stack", "mode"),
    itertools.product(("studio", "gpu"), ("none", "host", "docker")),
)
def test_fresh_install_matrix_uses_dynamic_ranges_and_selected_mode(
    tmp_path, stack, mode
):
    checkout, result, state, calls = _run_launcher(tmp_path, stack, mode)

    assert result.returncode == 0, result.stderr + result.stdout
    assert "never-print-this" not in result.stdout
    assert "never-print-this" not in result.stderr
    assert (checkout / ".docker-launch-settings").read_text(
        encoding="utf-8"
    ) == f"LAST_LAUNCHER={stack}\n"
    studio_up = _compose_calls(calls, "up", "studio")
    assert len(studio_up) == 1
    assert studio_up[0]["host_port"] == "5050-5149"
    assert studio_up[0]["bind_address"] == "127.0.0.1"
    assert studio_up[0]["data"] == (
        "./data-docker-gpu" if stack == "gpu" else "./data-docker"
    )
    if stack == "gpu":
        assert studio_up[0]["comfy_port"] == "8188-8287"
        assert studio_up[0]["comfy_run"] == "./run"
        assert studio_up[0]["comfy_basedir"] == "./basedir"
        assert studio_up[0]["bank_sources"] == "./bank-images"
    assert f"http://127.0.0.1:{state['app_port']}/" in result.stdout
    assert state["sidecar_running"] is (mode == "docker")
    assert bool(_compose_calls(calls, "up", "ollama")) is (mode == "docker")


@pytest.mark.parametrize("stack", ["studio", "gpu"])
def test_unconfigured_first_run_reads_choice_only_after_studio_is_ready(
    tmp_path, stack
):
    checkout, result, state, calls = _run_launcher(
        tmp_path,
        stack,
        mode=None,
        state_changes={"mode_after_studio_up": "docker"},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Choose the Ollama deployment mode in the Studio Setup page." in result.stdout
    assert state["studio_running"] is True
    assert state["sidecar_running"] is True
    actions = [call["args"][-1] for call in calls if "up" in call["args"]]
    assert actions.index("studio") < actions.index("ollama")
    assert "never-print-this" not in result.stdout
    assert checkout.joinpath(
        "data-docker-gpu" if stack == "gpu" else "data-docker",
        "config.json",
    ).exists()


def test_update_rebuild_waits_for_health_and_skips_setup(tmp_path):
    _, result, _, calls = _run_launcher(
        tmp_path,
        "gpu",
        mode=None,
        switches=("-UpdateRebuild",),
        state_changes={"health_sequence": ["starting", "healthy"]},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "LoRA Dataset Studio is healthy at" in result.stdout
    assert ("Updater mode will not wait for the browser or the Setup choices."
            in result.stdout)
    health_calls = [call for call in calls if "--format" in call["args"]]
    assert len(health_calls) == 2
    assert "Choose the Ollama deployment mode" not in result.stdout
    assert "Opening " not in result.stdout
    assert not _compose_calls(calls, "up", "ollama")


def test_update_rebuild_returns_nonzero_when_health_is_unhealthy(tmp_path):
    _, result, _, calls = _run_launcher(
        tmp_path,
        "gpu",
        mode=None,
        switches=("-UpdateRebuild",),
        state_changes={"health": "unhealthy"},
    )

    assert result.returncode != 0
    assert "became unhealthy" in result.stderr
    assert "LoRA Dataset Studio is healthy at" not in result.stdout
    assert "Choose the Ollama deployment mode" not in result.stdout
    assert not _compose_calls(calls, "up", "ollama")


def test_gpu_ollama_falls_back_to_cpu_without_failing_studio(tmp_path):
    _, result, state, calls = _run_launcher(
        tmp_path,
        "gpu",
        mode="docker",
        state_changes={"fail_gpu_ollama": True},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    ollama_up = _compose_calls(calls, "up", "ollama")
    assert len(ollama_up) == 2
    assert any("docker-compose.ollama-gpu.yml" in value for value in ollama_up[0]["args"])
    assert "--force-recreate" in ollama_up[1]["args"]
    assert not any("docker-compose.ollama-gpu.yml" in value for value in ollama_up[1]["args"])
    assert state["sidecar_running"] is True


@pytest.mark.parametrize(
    ("role", "should_stop"),
    [("ollama", True), (None, False), ("foreign", False)],
)
def test_none_mode_stops_only_a_verified_lds_sidecar(
    tmp_path, role, should_stop
):
    _, result, state, calls = _run_launcher(
        tmp_path,
        "studio",
        mode="none",
        state_changes={"sidecar_running": True, "sidecar_role": role},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    stops = _compose_calls(calls, "stop", "ollama")
    assert bool(stops) is should_stop
    assert state["sidecar_running"] is (not should_stop)

def test_update_none_mode_still_stops_an_owned_sidecar(tmp_path):
    _, result, state, calls = _run_launcher(
        tmp_path,
        "gpu",
        mode="none",
        switches=("-UpdateRebuild",),
        state_changes={
            "sidecar_running": True,
            "sidecar_role": "ollama",
            "health": "healthy",
        },
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert len(_compose_calls(calls, "stop", "ollama")) == 1
    assert state["sidecar_running"] is False


def test_rebuild_preserves_the_inspected_numeric_ports(tmp_path):
    _, result, _, calls = _run_launcher(
        tmp_path,
        "gpu",
        mode="none",
        switches=("-Rebuild",),
        state_changes={
            "studio_running": True,
            "app_port": 5099,
            "comfy_port": 8255,
        },
    )

    assert result.returncode == 0, result.stderr + result.stdout
    studio_up = _compose_calls(calls, "up", "studio")
    assert len(studio_up) == 1
    assert studio_up[0]["host_port"] == "5099"
    assert studio_up[0]["comfy_port"] == "8255"
    assert "--force-recreate" in studio_up[0]["args"]


def test_foreign_container_collision_fails_without_compose_mutation(tmp_path):
    _, result, _, calls = _run_launcher(
        tmp_path,
        "studio",
        mode="none",
        state_changes={
            "studio_running": True,
            "studio_label_project": "foreign-project",
        },
    )

    assert result.returncode == 1
    assert "belongs to another project or folder" in result.stderr
    assert not _compose_calls(calls, "up", "studio")
    assert not _compose_calls(calls, "stop", "ollama")
    assert [call for call in calls if "logs" in call["args"]]


def test_launcher_recovers_when_docker_desktop_starts_late(tmp_path):
    _, result, state, _ = _run_launcher(
        tmp_path,
        "studio",
        mode="none",
        state_changes={"info_failures_remaining": 1},
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert "Starting Docker Desktop" in result.stdout
    assert state["info_failures_remaining"] == 0
