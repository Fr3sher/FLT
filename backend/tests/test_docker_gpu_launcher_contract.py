"""Static safety contract for both novice Windows Docker launchers."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def read(name):
    return (REPO_ROOT / name).read_text(encoding='utf-8')


def test_public_batch_files_are_small_space_safe_wrappers_without_ollama_menu():
    external = read('start-docker.bat')
    gpu = read('start-docker-gpu.bat')

    for script, stack in ((external, 'studio'), (gpu, 'gpu')):
        assert 'setlocal EnableExtensions DisableDelayedExpansion' in script
        assert 'pushd "%~dp0"' in script
        assert 'popd' in script
        assert 'powershell.exe -NoLogo -NoProfile -STA' in script
        assert 'scripts\\docker-launch.ps1' in script
        assert f'-Stack {stack}' in script
        assert '--update-rebuild' in script
        assert 'choice.exe' not in script.lower()
        assert 'set /p' not in script.lower()
        assert 'OLLAMA_MODE=' not in script
        assert 'docker compose' not in script.lower()

    assert '--configure' in external
    assert '--configure' not in gpu


def test_engine_keeps_stacks_isolated_and_uses_atomic_dynamic_ports():
    engine = read('scripts/docker-launch.ps1')

    assert "$Project = 'lora-dataset-studio'" in engine
    assert "$Project = 'lora-dataset-studio-gpu'" in engine
    assert "'data-docker'" in engine
    assert "'data-docker-gpu'" in engine
    assert "LDS_HOST_PORT = '5050-5149'" in engine
    assert "LDS_COMFY_HOST_PORT = '8188-8287'" in engine
    assert "'--force-recreate'" in engine
    assert "Inspect-Container" in engine
    assert "APP_PORT" in engine
    assert "COMFY_PORT" in engine
    assert 'Start-Process $Uri' in engine
    assert '$NonInteractive' in engine
    assert "up', '-d', '--build'" in engine
    assert '-not $Configure' in engine
    assert "@('down'" not in engine.lower()
    assert "'rm'" not in engine


def test_marker_is_one_constant_line_and_contains_no_ollama_choice():
    engine = read('scripts/docker-launch.ps1')

    assert "'LAST_LAUNCHER=' + $Stack" in engine
    assert '.docker-launch-settings' in engine
    assert 'File]::Replace' in engine
    assert 'STUDIO_OLLAMA_MODE' not in engine
    assert 'GPU_OLLAMA_MODE' not in engine


def test_ollama_mode_comes_only_from_persistent_config_and_wait_is_bounded():
    engine = read('scripts/docker-launch.ps1')
    helper = read('scripts/docker-ollama-mode.ps1')

    assert "deployment_mode" in helper
    assert "'none', 'host', 'docker'" in helper
    assert "mode -eq 'unconfigured'" in helper
    assert "TimeoutSeconds = 900" in helper
    assert "Get-OllamaMode -Wait" in engine
    assert "if ($NonInteractive)" in engine
    assert 'updater mode will not wait' in engine.lower()
    assert 'Choose the Ollama deployment mode in the Studio Setup page.' in engine
    assert 'choice.exe' not in engine.lower()
    assert 'config.json' not in engine.split('Write-Host')[-1]


def test_sidecar_is_optional_private_persistent_and_owned_before_stop():
    engine = read('scripts/docker-launch.ps1')
    inspect = read('scripts/docker-launch-inspect.ps1')
    sidecar = read('docker-compose.ollama-sidecar.yml')
    gpu = read('docker-compose.ollama-gpu.yml')

    assert 'image: ollama/ollama:latest' in sidecar
    assert 'profiles: [ollama]' in sidecar
    assert ':/root/.ollama' in sidecar
    assert 'ports:' not in sidecar
    assert 'model pull' not in sidecar.lower()
    assert 'depends_on' not in sidecar
    assert 'io.lora-dataset-studio.role: ollama' in sidecar
    assert 'ExpectedRole' in inspect
    assert "Role 'ollama'" in engine
    assert "@('stop', 'ollama')" in engine
    assert "'--force-recreate', 'ollama'" in engine
    assert "'rm'" not in engine
    assert 'ollama-data was preserved' in engine
    assert 'driver: nvidia' in gpu
    assert 'portable CPU mode' in engine


def test_external_comfy_override_is_versioned_validated_and_read_write():
    engine = read('scripts/docker-launch.ps1')
    helper = read('scripts/configure-external-comfy.ps1')
    static = read('docker-compose.external-comfy.yml')

    assert '-STA' in read('start-docker.bat')
    assert 'FolderBrowserDialog' in helper
    assert 'TopMost = $true' in helper
    assert "Join-Path $LiteralPath 'ComfyUI'" in helper
    assert "'main.py'" in helper
    assert "'models'" in helper
    assert 'lds-external-comfy-schema: 1' in helper
    assert 'lds-external-comfy-path-base64' in helper
    assert "Replace($dollar, ($dollar + $dollar))" in helper
    assert '.Replace("\'", "\'\'")' in helper
    assert 'target: /external-comfyui' in helper
    assert 'read_only' not in helper
    assert 'mounted read-write' in engine
    assert 'LDS_RUNTIME: docker-external-comfy' in static
    assert 'LDS_DOCKER_COMFY_MODE: external' in static
    assert 'http://host.docker.internal:8188' in static
    assert '/external-comfyui' in static
    assert '--listen 0.0.0.0' in engine
    assert 'private/trusted networks only' in engine


def test_no_docker_socket_or_automatic_model_download_is_exposed():
    combined = '\n'.join(
        read(name)
        for name in (
            'scripts/docker-launch.ps1',
            'docker-compose.yml',
            'docker-compose.gpu.yml',
            'docker-compose.ollama-sidecar.yml',
        )
    )

    assert '/var/run/docker.sock' not in combined
    assert 'ollama pull' not in combined.lower()
    assert '11434:' not in combined
