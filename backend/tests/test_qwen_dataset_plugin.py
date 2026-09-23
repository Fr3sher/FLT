"""Boot the actual Dataset Forge package and route dataset work through its SDK."""
from pathlib import Path
from types import SimpleNamespace
import json

import pytest

from app import config, setup_installer
from app.engines import registry
from app.models import FaceDatasetImage
from app.services import face_dataset_service as datasets
from test_generate_multi_engine import _dataset_with_ref, _shots

pytestmark = pytest.mark.plugins('qwen_dataset')


@pytest.fixture
def forge(plugin_app_factory, monkeypatch, tmp_path):
    from lds_qwen_dataset import assets, engine, graph

    (tmp_path / 'comfy-input').mkdir()
    monkeypatch.setattr(engine.local_render, 'fetch_object_info_classes', lambda: graph.REQUIRED_NODES)
    monkeypatch.setattr(engine.local_render, 'fetch_object_info_enums', lambda: {
        'KSampler': {'sampler_name': ['res_multistep'], 'scheduler': ['simple']},
        'CLIPLoader': {'type': ['qwen_image']},
        'QwenImage21Cache': {'device': ['auto'], 'dtype': ['default']},
    })
    monkeypatch.setattr(assets, 'inspect_assets', lambda: {
        'models': {slot: spec['filename'] for slot, spec in assets.ASSETS.items()},
        'missing': [], 'invalid': [],
    })
    monkeypatch.setattr(engine.config, 'comfyui_dir', lambda _: str(tmp_path / 'comfy-input'))
    monkeypatch.setattr(config, 'comfyui_dir', lambda _: str(tmp_path / 'comfy-input'))
    admitted = []
    monkeypatch.setattr('app.job_queue.queue_manager.add_job', lambda **job: admitted.append(job))
    monkeypatch.setattr('app.routes.datasets._require_no_stalled_comfyui', lambda: None)
    app = plugin_app_factory(enabled=('qwen_dataset',))
    config.save_config({'engines': {'enabled': list(registry.ids())}})
    return app, admitted


def test_real_package_registers_settings_engine_and_own_installers(forge):
    app, _ = forge
    spec = registry.get('qwen_dataset')
    assert spec.plugin == 'qwen_dataset' and spec.kind == 'local'
    assert callable(spec.local_enqueue) and callable(spec.local_preflight)
    assert spec.label == 'Qwen-Image 2.1'
    assert config.get('plugins.qwen_dataset.steps') == 25
    assert config.get('plugins.qwen_dataset.cfg') == 3
    plugins = app.extensions['lds_plugins']
    assert plugins.records['qwen_dataset'].state == 'loaded'
    for action in ('qwen_dataset_model', 'qwen_dataset_text_encoder', 'qwen_dataset_vae'):
        assert setup_installer.known_action(action)
        assert plugins.model_downloads[action]['plugin'] == 'qwen_dataset'
    with app.app_context():
        assert spec.local_preflight(reference_count=2)['ok']
        assert 'qwen_dataset' in datasets.known_engine_ids()
        assert 'qwen_dataset' not in datasets.editable_engines()


def test_real_route_enqueues_native_graph_and_preserves_reference_identity(forge, monkeypatch):
    app, admitted = forge
    client = app.test_client()
    dataset_id = _dataset_with_ref(client, name='Fixture')
    with app.app_context():
        ds = datasets.get_dataset('local', dataset_id)
        datasets.add_extra_ref('local', dataset_id, Path(datasets._ref_path(ds)).read_bytes())
    response = client.post(f'/api/dataset/{dataset_id}/generate', json={
        'generator': 'qwen_dataset', 'variations': _shots(1)})
    assert response.status_code == 200, response.json
    assert response.json['per_engine'] == {'qwen_dataset': 1}
    assert len(admitted) == 1
    job = admitted[0]
    assert job['metadata']['is_dataset'] and job['metadata']['dataset_id'] == dataset_id
    assert job['metadata']['model_name'] == 'qwen_dataset'
    assert job['metadata']['dataset_engine_plugin'] == 'qwen_dataset'
    assert len(job['metadata']['staged_inputs']) == 2
    encoder = job['workflow_data']['4']['inputs']
    assert encoder['images.image_1'] and encoder['images.image_2']
    assert '<image2>' in encoder['prompt']
    with app.app_context():
        row = FaceDatasetImage.query.filter_by(dataset_id=dataset_id).one()
        assert row.job_id == job['job_id']
        assert datasets._image_engine(row) == 'qwen_dataset'
        from app import job_queue
        from app.services.queue_view import _engine_label
        finished = SimpleNamespace(job_id=row.job_id, status='failed',
                                   job_metadata=json.dumps(job['metadata']),
                                   error_message='ComfyUI rejected workflow')
        assert _engine_label(job['metadata']) == 'Qwen-Image 2.1'
        assert job_queue._job_owner_available(finished)
        monkeypatch.setattr('app.auth_policy.plugin_available', lambda _: False)
        assert not job_queue._job_owner_available(finished)
        # Core-owned rows must finish even when a plugin stops accepting work.
        job_queue._dispatch_completion(finished, None, failed=True)
        assert row.status == 'failed'
        assert row.fail_reason == 'ComfyUI rejected workflow'
        assert not list(Path(config.comfyui_dir('input')).glob('lds_dataset_forge_*'))


def test_real_route_returns_preparation_refusal_before_queueing(forge, monkeypatch):
    from lds_qwen_dataset import engine, graph

    app, admitted = forge
    client = app.test_client()
    dataset_id = _dataset_with_ref(client, name='Fixture')
    monkeypatch.setattr(engine.local_render, 'fetch_object_info_classes',
                        lambda: graph.REQUIRED_NODES - {'TextEncodeQwenImage21'})
    response = client.post(f'/api/dataset/{dataset_id}/generate', json={
        'generator': 'qwen_dataset', 'variations': _shots(1)})
    assert response.status_code == 409, response.json
    assert response.json['setup_path'] == '/plugins/qwen_dataset/settings'
    assert 'Update ComfyUI' in response.json['error']
    assert not admitted
    with app.app_context():
        assert FaceDatasetImage.query.filter_by(dataset_id=dataset_id).count() == 0
