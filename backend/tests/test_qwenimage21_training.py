"""Qwen 2.1 must never fall back to an older Qwen/Z-Image/SD training recipe."""
from pathlib import Path

import pytest


def _dataset(app, tmp_path):
    from app import config as cfg
    from app.services import face_dataset_service as fds
    cfg.save_config({'aitoolkit': {'dir': str(tmp_path / 'aitoolkit')},
                     'comfyui': {'base_dir': str(tmp_path / 'comfy')}})
    return fds.create_dataset(cfg.LOCAL_USER, 'Qwen subject', 'subject_token',
                              train_type='qwenimage21')


def test_recipe_and_provenance_agree(app, tmp_path):
    from app.services import lora_training as lt
    from app.services import face_dataset_service as fds
    with app.app_context():
        ds = _dataset(app, tmp_path)
        assert fds.normalize_train_type('QWENIMAGE21') == 'qwenimage21'
        p = lt.build_job_config(ds, str(tmp_path / 'dataset'), 1200)['config']['process'][0]
        m = p['model']
        assert m['arch'] == 'qwen_image_2'
        assert m['name_or_path'] == lt.QWENIMAGE21_BASE
        assert m['extras_name_or_path'] == lt.QWENIMAGE21_EXTRAS
        assert m['qtype'] == m['qtype_te'] == 'convrot8'
        assert m['quantize'] and m['quantize_te'] and m['low_vram']
        assert m['model_kwargs'] == {'rgba': False}
        assert p['network'] == {'type': 'lora', 'linear': 32, 'linear_alpha': 32}
        assert p['train']['noise_scheduler'] == 'flowmatch'
        assert p['train']['timestep_type'] == 'shift'
        assert p['train']['unload_text_encoder'] is False
        assert p['datasets'][0]['cache_text_embeddings'] is False
        assert p['sample']['guidance_scale'] == 3
        assert p['sample']['sample_steps'] == 40
        snap = lt.launch_settings_snapshot(ds)
        for key in ('qtype', 'qtype_te', 'extras_name_or_path'):
            assert snap[key] == m[key]
        assert snap['model_arch'] == m['arch']
        assert snap['effective_base'] == m['name_or_path']
        assert lt.official_base_repo(ds) == lt.QWENIMAGE21_BASE


def test_extension_guard_rejects_old_qwen_and_comments(app, tmp_path):
    from app.services import lora_training as lt
    with app.app_context():
        _dataset(app, tmp_path)
        source = tmp_path / 'aitoolkit/extensions_built_in/diffusion_models/qwen_image_2/qwen_image_2.py'
        source.parent.mkdir(parents=True)
        source.write_text('# arch = "qwen_image_2"\nclass Old:\n    arch = "qwen_image"\n')
        assert not lt._aitoolkit_supports_qwenimage21()
        with pytest.raises(ValueError, match='qwen_image_2 arch missing'):
            lt._assert_qwenimage21_ready('qwenimage21')
        source.write_text('class QwenImage2Model:\n    arch = "qwen_image_2"\n')
        assert lt._aitoolkit_supports_qwenimage21()
        lt._assert_qwenimage21_ready('qwenimage21')


def test_base_info_keeps_qwen_separate_from_zimage(app, client, tmp_path, monkeypatch):
    monkeypatch.setattr('app.capabilities.probe_aitoolkit', lambda: {'ok': True})
    monkeypatch.setattr('app.capabilities.probe', lambda *a, **k: {'aitoolkit': {'valid': True}})
    with app.app_context():
        ds = _dataset(app, tmp_path)
        dataset_id = ds.id
    response = client.get(f'/api/dataset/{dataset_id}/train/base-info')
    assert response.status_code == 200
    info = response.get_json()
    assert info['qwenimage21_supported'] is False
    assert info['bases_by_type']['qwenimage21'] == [
        {'value': '', 'label': 'Official - Qwen-Image 2.1'}]


def test_launch_and_queue_refuse_missing_arch(app, tmp_path, monkeypatch):
    from app import config as cfg
    from app.services import lora_training as lt
    with app.app_context():
        ds = _dataset(app, tmp_path)
        root = tmp_path / 'aitoolkit'
        (root / 'venv/Scripts').mkdir(parents=True)
        (root / 'venv/Scripts/python.exe').write_text('fake')
        (root / 'run.py').write_text('fake')
        monkeypatch.setattr(lt.shutil, 'disk_usage', lambda _: type('Usage', (), {'free': 500e9})())
        monkeypatch.setattr(lt, 'assert_trainable', lambda *_a, **_kw: None)
        with pytest.raises(ValueError, match='qwen_image_2 arch missing'):
            lt.launch_training(cfg.LOCAL_USER, ds.id, check_captions=False)
        with pytest.raises(ValueError, match='qwen_image_2 arch missing'):
            lt.enqueue_training(cfg.LOCAL_USER, ds.id, extra_steps=100)


def test_checkpoint_isolation_and_arch_detection(app, tmp_path):
    from app.services import lora_training as lt
    from app.services import lora_test_studio as studio
    from app.utils.comfyui import family_of_lora
    with app.app_context():
        ds = _dataset(app, tmp_path)
        assert lt._dest_base_tag(ds) == '_Qwen-Image-2-1'
        assert Path(lt._lora_dest_dir(ds)).name == 'qwenimage21'
        assert family_of_lora('qwenimage21/subject.safetensors') == 'qwenimage21'
        assert lt._family_from_base_model_version('qwen_image_2') == 'qwenimage21'
        assert lt._family_from_base_model_version('qwen_image') is None
        assert lt._lora_arch_from_keys({'diffusion_model.transformer_blocks.0.img_mlp.gate_up.lora_A.weight'}) == 'qwenimage21'
        assert lt.lora_arch_conflicts('qwenimage21', 'zimage')
        assert 'qwenimage21' in studio.FAMILIES
        assert not studio.can_generate_with('qwenimage21')


@pytest.mark.plugins('cloud_training')
def test_cloud_recipe_resources_and_price_without_invented_estimate(app, tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from app import config as cfg
    from lds_cloud_training import cloud_training as ct
    monkeypatch.setattr(ct.cfg, 'secret', lambda k: 'fake-key' if k == 'VAST_API_KEY' else None)
    searches = []
    def offers(**kwargs):
        searches.append(kwargs)
        return [{'offer_id': 1, 'gpu_name': 'RTX A6000', 'gpu_ram_gb': 48,
                 'dph_total': 0.6}]
    monkeypatch.setattr(ct.vast_client, 'search_offers', offers)
    monkeypatch.setattr(ct, '_filter_offers', lambda rows: rows)
    with app.app_context():
        ds = _dataset(app, tmp_path)
        tiers = ct.gpu_tiers(cfg.LOCAL_USER, ds.id)
        assert searches[0]['min_vram_gb'] == 32
        assert searches[0]['min_disk_gb'] == 100
        assert searches[0]['min_compute_cap'] == 800
        assert tiers['tiers'][0]['dph_total'] == 0.6
        assert tiers['tiers'][0]['est_cost'] is None
        params = {'train_type': 'qwenimage21', 'steps': 100}
        run = SimpleNamespace(dataset_id=ds.id, job_name='qwen_test',
                              train_params=json.dumps(params))
        assert '0bd3411-2026-09-23' in ct._pod_image_for(run, {'image': 'old-trainer'})
        settings = {'DATASETS_FOLDER': '/workspace/datasets', 'TRAINING_FOLDER': '/workspace/output'}
        job = ct._build_pod_job_config(run, str(tmp_path / 'dataset'), settings)
        proc = job['config']['process'][0]
        assert proc['model']['arch'] == 'qwen_image_2'
        assert proc['type'] == 'diffusion_trainer'
        assert proc['datasets'][0]['folder_path'] == '/workspace/datasets/qwen_test'
        assert proc['model']['qtype'] == proc['model']['qtype_te'] == 'convrot8'
