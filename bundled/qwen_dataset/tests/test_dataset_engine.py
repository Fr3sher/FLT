"""CPU contracts for references, preparation and the public queue boundary."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'bundled/qwen_dataset')]

from lds_qwen_dataset import assets, engine, graph, register


def model_names():
    return {slot: spec['filename'] for slot, spec in assets.ASSETS.items()}


@pytest.mark.parametrize('count', [1, 2, 10])
def test_graph_uses_all_identity_refs_and_matching_conditioning(count):
    refs = [f'ref_{i}.png' for i in range(count)]
    prompt = graph.identity_prompt('left profile, smiling', count)
    workflow = graph.build_graph(assets=model_names(), references=refs, prompt=prompt,
                                 seed=2**64 - 1, aspect_ratio='2:3', megapixels=1.0)
    encoder = workflow['4']['inputs']
    assert encoder['vae'] == ['3', 0]
    assert encoder['resolution'] == 1024
    assert '<image1>' in encoder['prompt'] and f'<image{count}>' in encoder['prompt']
    for i, filename in enumerate(refs, 1):
        link = encoder[f'images.image_{i}']
        assert workflow[link[0]]['inputs']['image'] == filename
    sampler = workflow['7']['inputs']
    assert sampler['positive'] == ['4', 0] and sampler['negative'] == ['4', 1]
    assert sampler['seed'] == 2**64 - 1
    assert sampler['model'] == ['5', 0]
    geometry = workflow['6']['inputs']
    assert geometry['width'] % 32 == geometry['height'] % 32 == 0
    assert abs(geometry['width'] / geometry['height'] - 2 / 3) < 0.03
    assert 950000 < geometry['width'] * geometry['height'] < 1050000
    assert {node['class_type'] for node in workflow.values()} == graph.REQUIRED_NODES


def test_bad_references_geometry_and_settings_fail_before_graph_creation():
    with pytest.raises(ValueError, match='Reference count'):
        graph.build_graph(assets=model_names(), references=['ref.png'] * 11, prompt='shot', seed=1)
    for value in (float('nan'), -1, True, 3):
        with pytest.raises(ValueError):
            graph.dimensions('1:1', value)
    with pytest.raises(ValueError, match='multiple of 32'):
        graph.settings({'reference_resolution': 1000})
    with pytest.raises(ValueError, match='Steps'):
        graph.settings({'steps': 1.5})
    with pytest.raises(ValueError, match='inside ComfyUI'):
        graph.build_graph(assets={**model_names(), 'unet': '../escape.safetensors'},
                          references=['ref.png'], prompt='shot', seed=1)


def test_prompt_follows_animal_and_anime_subjects_without_human_identity_rules():
    animal = graph.identity_prompt('side view in snow', 2, 'animal')
    anime = graph.identity_prompt('smile', 1, 'anime')
    assert 'markings, coat' in animal and 'person' not in animal
    assert 'illustration style' in anime and 'photo' not in anime
    assert 'side view in snow' in animal


@pytest.fixture
def ready(monkeypatch, tmp_path):
    values = {'variations.output_megapixels': 0.5}
    monkeypatch.setattr(engine.config, 'get', lambda key, default=None: values.get(key, default))
    monkeypatch.setattr(engine.config, 'comfyui_dir', lambda _: str(tmp_path / 'input'))
    monkeypatch.setattr(assets, 'inspect_assets', lambda: {
        'models': model_names(), 'missing': [], 'invalid': []})
    monkeypatch.setattr(engine.local_render, 'fetch_object_info_classes', lambda: graph.REQUIRED_NODES)
    enums = {
        'KSampler': {'sampler_name': ['res_multistep'], 'scheduler': ['simple']},
        'CLIPLoader': {'type': ['qwen_image']},
        'QwenImage21Cache': {'device': ['auto'], 'dtype': ['default']},
    }
    monkeypatch.setattr(engine.local_render, 'fetch_object_info_enums', lambda: enums)
    return values, enums


def test_preflight_never_certifies_missing_nodes_or_unknown_sampler(ready, monkeypatch):
    assert engine.preflight(reference_count=2)['ok']
    assert not engine.preflight(reference_count=11)['ok']
    assert not engine.preflight(reference_count=0)['ok']
    ready[1]['KSampler']['sampler_name'] = ['euler']
    assert 'Update ComfyUI' in engine.probe()['detail']
    del ready[1]['KSampler']['sampler_name']
    assert 'cannot verify' in engine.probe()['detail']
    monkeypatch.setattr(engine.local_render, 'fetch_object_info_classes',
                        lambda: graph.REQUIRED_NODES - {'QwenImage21Cache'})
    assert engine.probe()['missing_nodes'] == ['QwenImage21Cache']
    monkeypatch.setattr(engine.local_render, 'fetch_object_info_classes', lambda: None)
    assert not engine.probe()['ok']
    assert 'start ComfyUI' in engine.probe()['detail']


def test_enqueue_uses_host_queue_metadata_and_never_drops_references(ready, monkeypatch, tmp_path):
    source = tmp_path / 'source.png'
    extra = tmp_path / 'extra.png'
    source.write_bytes(b'fixture')
    extra.write_bytes(b'fixture')
    staged, admitted = [], []
    monkeypatch.setattr(engine.comfy, 'ensure_input_usable', lambda path: path)
    monkeypatch.setattr(engine.comfy, 'stage_input_image',
                        lambda path, name, destination: staged.append((path, name)) or name)
    monkeypatch.setattr(engine.comfy.queue, 'add_job', lambda **kwargs: admitted.append(kwargs))
    job = engine.enqueue('test-user', 'source.png', str(source), 'full body',
                         extra_ref_paths=[str(extra)], aspect_ratio='2:3', seed=12,
                         extra_metadata={'is_dataset': True, 'dataset_id': 7, 'variation_label': 'Body'})
    assert job == admitted[0]['job_id']
    assert len(staged) == 2
    assert admitted[0]['metadata']['is_dataset'] is True
    assert admitted[0]['metadata']['dataset_id'] == 7
    assert admitted[0]['metadata']['engine'] == 'qwen_dataset'
    assert admitted[0]['metadata']['staged_inputs'] == [item[1] for item in staged]
    assert admitted[0]['workflow_data']['6']['inputs']['height'] < 1000
    with pytest.raises(ValueError, match='Reference 2 is missing'):
        engine.enqueue('test-user', 'source.png', str(source), 'shot',
                       extra_ref_paths=[str(tmp_path / 'gone.png')])
    assert len(staged) == 2 and len(admitted) == 1


def test_staging_failure_removes_only_the_jobs_staged_files(ready, monkeypatch, tmp_path):
    source = tmp_path / 'source.png'
    source.write_bytes(b'fixture')
    input_dir = tmp_path / 'input'
    input_dir.mkdir()
    keep = input_dir / 'existing.png'
    keep.write_bytes(b'keep')
    monkeypatch.setattr(engine.comfy, 'ensure_input_usable', lambda path: path)
    def stage(path, name, destination):
        target = Path(destination) / name
        target.write_bytes(b'staged')
        return str(target)
    def refuse(**kwargs):
        raise ValueError('GPU queue admission refused')
    monkeypatch.setattr(engine.comfy, 'stage_input_image', stage)
    monkeypatch.setattr(engine.comfy.queue, 'add_job', refuse)
    with pytest.raises(ValueError, match='admission refused'):
        engine.enqueue('test-user', 'source.png', str(source), 'shot')
    assert list(input_dir.iterdir()) == [keep]


def test_asset_discovery_is_exact_family_and_reuses_subfolders(monkeypatch, tmp_path):
    monkeypatch.setattr(assets.config, 'get', lambda *args: '')
    canonical = assets.ASSETS['text_encoder']['filename']
    present = tmp_path / 'qwen' / canonical
    choices = [('qwen3vl_4b_fp8_scaled.safetensors', str(tmp_path / 'wrong')),
               ('qwen/' + canonical, str(present))]
    monkeypatch.setattr(assets.models, 'list_models', lambda _: choices)
    monkeypatch.setattr(assets.models, 'search_roots', lambda _: [str(tmp_path)])
    assert assets.resolve('text_encoder') == 'qwen/' + canonical
    assert str(present.parent) in assets.download_roots('text_encoder')
    monkeypatch.setattr(assets.models, 'list_models', lambda _: choices[:1])
    assert assets.resolve('text_encoder') is None
    assert assets.candidates('text_encoder') == []
    monkeypatch.setattr(assets.config, 'get', lambda *args: 'qwen3vl_4b_fp8_scaled.safetensors')
    monkeypatch.setattr(assets.models, 'resolve_ref', lambda *_: ('qwen3vl_4b_fp8_scaled.safetensors', 'ok'))
    assert assets.resolve('text_encoder') is None
    monkeypatch.setattr(assets.config, 'get', lambda *args: 'stale.safetensors')
    monkeypatch.setattr(assets.models, 'resolve_ref', lambda *_: (None, 'missing'))
    assert assets.resolve('text_encoder') is None


def test_corrupt_asset_is_not_ready(monkeypatch):
    monkeypatch.setattr(assets, 'resolve', lambda slot: model_names()[slot])
    monkeypatch.setattr(assets.models, 'resolve_model_file', lambda folder, name: name)
    monkeypatch.setattr(assets.models, 'validate_model_file', lambda _: {'blocking': True})
    result = assets.inspect_assets()
    assert not result['missing']
    assert {row['asset'] for row in result['invalid']} == set(assets.ACTIONS)


def test_manifest_owns_every_registered_capability_and_requires_new_local_api():
    manifest = json.loads((ROOT / 'bundled/qwen_dataset/plugin.json').read_text(encoding='utf-8'))
    events = []
    class Context:
        def register_config_defaults(self, mapping):
            assert mapping == graph.DEFAULTS
        def __getattr__(self, name):
            def record(*args, **kwargs):
                events.append((name, args[0] if args else kwargs['id'], kwargs))
            return record
    register(Context())
    ownership = {
        'register_engine': 'engines', 'register_probe': 'probes',
        'register_model_download': 'install_actions', 'register_model_slot': 'model_slots',
        'register_install_group': 'install_groups',
    }
    for kind, name, kwargs in events:
        assert name in manifest['owns'][ownership[kind]]
        if kind == 'register_model_download':
            assert kwargs['license_url'] == assets.LICENSE_URL
            assert kwargs['expected_bytes'] > 0
            assert callable(kwargs['extra_roots'])
        if kind == 'register_engine':
            assert kwargs['local_enqueue'] is engine.enqueue
            assert kwargs['local_preflight'] is engine.preflight
    assert manifest['schema_version'] == 2
    assert manifest['compatibility']['api'] == '>=1.23,<2'
    assert manifest['requires'] == []
