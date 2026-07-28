"""The GPU image's config seeder: fills what is empty, never what is set."""
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def seeder():
    """Load the seeder by path. It is a container-boot script, not part of the
    `app` package, and it deliberately imports nothing from it."""
    path = REPO_ROOT / 'packaging' / 'docker' / 'seed_comfy_config.py'
    spec = importlib.util.spec_from_file_location('seed_comfy_config', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seeds_the_container_paths_into_an_empty_config(seeder, tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    monkeypatch.setenv('LDS_CONFIG', str(config))
    monkeypatch.setenv('BASE_DIRECTORY', '/basedir')
    monkeypatch.delenv('LDS_OLLAMA_URL', raising=False)

    assert seeder.main() == 0

    written = json.loads(config.read_text(encoding='utf-8'))
    assert written['comfyui']['base_dir'] == '/comfy/mnt/ComfyUI'
    assert written['comfyui']['api_url'] == 'http://127.0.0.1:8188'
    assert written['comfyui']['models_dir'] == '/basedir/models'
    assert written['comfyui']['loras_dir'] == '/basedir/models/loras'
    assert written['comfyui']['input_dir'] == '/basedir/input'
    assert written['comfyui']['output_dir'] == '/basedir/output'
    assert 'ollama' not in written


def test_never_overwrites_a_path_the_user_chose(seeder, tmp_path, monkeypatch):
    """This runs on EVERY boot, so anything set in Settings has to survive it."""
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({
        'comfyui': {'base_dir': '/my/own/comfy', 'models_dir': '   '},
        'paths': {'dataset_images_root': '/keep/me'},
    }), encoding='utf-8')
    monkeypatch.setenv('LDS_CONFIG', str(config))
    monkeypatch.setenv('BASE_DIRECTORY', '/basedir')

    assert seeder.main() == 0

    written = json.loads(config.read_text(encoding='utf-8'))
    assert written['comfyui']['base_dir'] == '/my/own/comfy'
    assert written['comfyui']['models_dir'] == '/basedir/models'
    assert written['paths']['dataset_images_root'] == '/keep/me'


def test_without_base_directory_the_four_overrides_stay_empty(seeder, tmp_path, monkeypatch):
    """No BASE_DIRECTORY means ComfyUI keeps models/ and input/ inside its own
    checkout, and config.resolve_comfyui_dir derives them from base_dir. Writing
    overrides then would only pin paths that are already correct."""
    config = tmp_path / 'config.json'
    monkeypatch.setenv('LDS_CONFIG', str(config))
    monkeypatch.delenv('BASE_DIRECTORY', raising=False)

    assert seeder.main() == 0

    comfy = json.loads(config.read_text(encoding='utf-8'))['comfyui']
    assert comfy['base_dir'] == '/comfy/mnt/ComfyUI'
    assert 'models_dir' not in comfy
    assert 'input_dir' not in comfy


def test_seeds_ollama_only_when_a_url_is_supplied(seeder, tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    monkeypatch.setenv('LDS_CONFIG', str(config))
    monkeypatch.delenv('BASE_DIRECTORY', raising=False)
    monkeypatch.setenv('LDS_OLLAMA_URL', 'http://ollama.internal:11434')

    assert seeder.main() == 0

    written = json.loads(config.read_text(encoding='utf-8'))
    assert written['ollama']['url'] == 'http://ollama.internal:11434'


def test_a_corrupt_config_is_left_alone_rather_than_replaced(seeder, tmp_path,
                                                            monkeypatch, capsys):
    """A half-written config.json is the user's data. Replacing it would silently
    reset every setting; refusing and saying so loses nothing."""
    config = tmp_path / 'config.json'
    config.write_text('{not json', encoding='utf-8')
    monkeypatch.setenv('LDS_CONFIG', str(config))

    assert seeder.main() == 0
    assert config.read_text(encoding='utf-8') == '{not json'
    assert 'unreadable' in capsys.readouterr().out


def test_leaves_no_temp_file_behind(seeder, tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    monkeypatch.setenv('LDS_CONFIG', str(config))
    monkeypatch.delenv('BASE_DIRECTORY', raising=False)

    assert seeder.main() == 0

    assert [p.name for p in tmp_path.iterdir()] == ['config.json']
