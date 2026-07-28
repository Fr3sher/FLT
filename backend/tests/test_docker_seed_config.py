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
    monkeypatch.delenv('LDS_OLLAMA_URL', raising=False)

    assert seeder.main() == 0

    written = json.loads(config.read_text(encoding='utf-8'))
    assert written['comfyui']['base_dir'] == seeder.FALLBACK_COMFY_ROOT
    assert written['comfyui']['api_url'] == 'http://127.0.0.1:8188'
    assert 'models_dir' not in written['comfyui']
    assert 'loras_dir' not in written['comfyui']
    assert 'input_dir' not in written['comfyui']
    assert 'output_dir' not in written['comfyui']
    assert 'ollama' not in written


def test_never_overwrites_a_path_the_user_chose(seeder, tmp_path, monkeypatch):
    """This runs on EVERY boot, so anything set in Settings has to survive it."""
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({
        'comfyui': {'base_dir': '/my/own/comfy'},
        'paths': {'dataset_images_root': '/keep/me'},
    }), encoding='utf-8')
    monkeypatch.setenv('LDS_CONFIG', str(config))

    assert seeder.main() == 0

    written = json.loads(config.read_text(encoding='utf-8'))
    assert written['comfyui']['base_dir'] == '/my/own/comfy'
    assert written['paths']['dataset_images_root'] == '/keep/me'


def test_base_dir_is_whichever_folder_actually_holds_models(seeder, tmp_path, monkeypatch):
    """capabilities._is_comfyui_dir accepts a folder with models/ plus main.py OR
    custom_nodes/. Under upstream's BASE_DIRECTORY layout the checkout has neither
    models/ nor custom_nodes/, so pointing at it would fail that check and the app
    would find no models at all."""
    basedir = tmp_path / 'basedir'
    (basedir / 'models').mkdir(parents=True)
    checkout = tmp_path / 'ComfyUI'
    checkout.mkdir()
    monkeypatch.setattr(seeder, 'COMFY_ROOT_CANDIDATES', (str(basedir), str(checkout)))

    assert seeder.comfy_root() == str(basedir)


def test_base_dir_falls_back_to_the_checkout_when_no_models_folder_exists(seeder, tmp_path, monkeypatch):
    """First boot can reach the seeder before ComfyUI has created anything. A
    concrete path the user can correct in Settings beats an empty field."""
    monkeypatch.setattr(seeder, 'COMFY_ROOT_CANDIDATES',
                        (str(tmp_path / 'nope'), str(tmp_path / 'also-nope')))

    assert seeder.comfy_root() == seeder.FALLBACK_COMFY_ROOT


def test_main_honours_the_probed_root(seeder, tmp_path, monkeypatch):
    """main() must actually use comfy_root(), not a hardcoded constant."""
    config = tmp_path / 'config.json'
    monkeypatch.setenv('LDS_CONFIG', str(config))
    basedir = tmp_path / 'basedir'
    (basedir / 'models').mkdir(parents=True)
    monkeypatch.setattr(seeder, 'COMFY_ROOT_CANDIDATES', (str(basedir),))

    assert seeder.main() == 0

    written = json.loads(config.read_text(encoding='utf-8'))
    assert written['comfyui']['base_dir'] == str(basedir)


def test_seeds_ollama_only_when_a_url_is_supplied(seeder, tmp_path, monkeypatch):
    config = tmp_path / 'config.json'
    monkeypatch.setenv('LDS_CONFIG', str(config))
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

    assert seeder.main() == 0

    assert [p.name for p in tmp_path.iterdir()] == ['config.json']
