"""Local plugin dispatch uses dataset rows and the existing GPU lifecycle."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app import config as cfg
from app.engines import registry
from app.extensions import db
from app.models import FaceDatasetImage
from app.services import face_dataset_service as svc
from app.services import local_dataset_engines as local
from test_generate_multi_engine import _dataset_with_ref, _shots, no_threads  # noqa: F401

pytestmark = pytest.mark.plugins('api_engines')


@pytest.fixture
def provider(app, monkeypatch):
    calls, preparations = [], []

    def prepare(**facts):
        preparations.append(facts)
        return {'ok': True}

    def enqueue(**facts):
        calls.append(facts)
        return f'plugin-job-{len(calls)}'

    registry.register(registry.EngineSpec(
        id='local_fixture', label='Local fixture', kind='local', order=2,
        plugin='api_engines', local_preflight=prepare, local_enqueue=enqueue))
    monkeypatch.setattr('app.routes.datasets._require_no_stalled_comfyui', lambda: None)
    cfg.save_config({'engines': {'enabled': list(registry.ids())}})
    return calls, preparations


def test_generate_uses_plugin_refs_dimensions_provenance_and_completion(client, provider):
    calls, preparations = provider
    dataset_id = _dataset_with_ref(client)
    with client.application.app_context():
        ds = svc.get_dataset('local', dataset_id)
        # A second anchor comes from the dataset, not from a sibling engine.
        source = Path(svc._ref_path(ds)).read_bytes()
        svc.add_extra_ref('local', dataset_id, source)
    response = client.post(f'/api/dataset/{dataset_id}/generate', json={
        'generator': 'local_fixture', 'variations': _shots(2), 'multiplier': 2})
    assert response.status_code == 200, response.json
    assert response.json['per_engine'] == {'local_fixture': 4}
    assert len(calls) == 4
    assert preparations[0]['reference_count'] == 2
    assert all(len(call['extra_ref_paths']) == 1 for call in calls)
    assert all(call['aspect_ratio'] and call['extra_metadata']['is_dataset'] for call in calls)
    with client.application.app_context():
        rows = FaceDatasetImage.query.filter_by(dataset_id=dataset_id).all()
        assert [row.job_id for row in rows] == [f'plugin-job-{i}' for i in range(1, 5)]
        assert all(svc._image_engine(row) == 'local_fixture' for row in rows)
        assert json.loads(rows[0].generation_meta)['seed'] == calls[0]['seed']
        svc.link_completed_dataset_image(rows[0].job_id, None, failed=True, reason='render failed')
        assert rows[0].status == 'failed' and rows[0].fail_reason == 'render failed'


def test_missing_plugin_assets_refuse_before_any_paid_or_local_dispatch(client, provider, no_threads):
    dataset_id = _dataset_with_ref(client)
    spec = registry.get('local_fixture')
    registry.register(replace(spec, local_preflight=lambda **_: {
        'ok': False, 'detail': 'Install the diffusion model in plugin settings.'}), replace=True)
    response = client.post(f'/api/dataset/{dataset_id}/generate', json={
        'engine_batches': [
            {'generator': 'chatgpt', 'variations': _shots(1)},
            {'generator': 'local_fixture', 'variations': _shots(1)}]})
    assert response.status_code == 409
    assert response.json['setup_path'] == '/plugins/api_engines/settings'
    assert not provider[0] and not no_threads
    with client.application.app_context():
        assert FaceDatasetImage.query.filter_by(dataset_id=dataset_id).count() == 0


def test_regenerate_uses_same_provider_and_preserves_raw_prompt(client, provider, monkeypatch):
    dataset_id = _dataset_with_ref(client)
    client.post(f'/api/dataset/{dataset_id}/generate', json={
        'generator': 'local_fixture', 'variations': _shots(1)})
    monkeypatch.setattr('app.job_queue.queue_manager.cancel_job', lambda *_, **__: True)
    with client.application.app_context():
        image_id = FaceDatasetImage.query.filter_by(dataset_id=dataset_id).first().id
    response = client.post(f'/api/dataset/image/{image_id}/regenerate', json={
        'prompt': 'new portrait expression'})
    assert response.status_code == 200, response.json
    assert len(provider[0]) == 2
    assert 'new portrait expression' in provider[0][-1]['edit_prompt']
    with client.application.app_context():
        row = db.session.get(FaceDatasetImage, image_id)
        assert row.klein_model == 'local_fixture'
        assert row.variation_prompt == 'new portrait expression'
        assert row.job_id == 'plugin-job-2'


def test_uninstalled_provider_retains_badge_and_cannot_fall_back_to_klein(client, provider):
    dataset_id = _dataset_with_ref(client)
    client.post(f'/api/dataset/{dataset_id}/generate', json={
        'generator': 'local_fixture', 'variations': _shots(1)})
    registry.unregister('local_fixture')
    with client.application.app_context():
        row = FaceDatasetImage.query.filter_by(dataset_id=dataset_id).first()
        assert svc._image_engine(row) == 'local_fixture'
        with pytest.raises(ValueError, match='unavailable'):
            svc._rgn_resolve_target(row, None, None)
    assert len(provider[0]) == 1


def test_dataset_only_engine_is_not_offered_as_reference_editor(client, provider):
    with client.application.app_context():
        assert 'local_fixture' in svc.known_engine_ids()
        assert 'local_fixture' not in svc.editable_engines()


def test_disabled_engine_setting_refuses_retry_instead_of_changing_provider(client, provider):
    dataset_id = _dataset_with_ref(client)
    client.post(f'/api/dataset/{dataset_id}/generate', json={
        'generator': 'local_fixture', 'variations': _shots(1)})
    cfg.save_config({'engines': {'enabled': ['klein', 'chatgpt'], 'default': 'chatgpt'}})
    with client.application.app_context():
        row = FaceDatasetImage.query.filter_by(dataset_id=dataset_id).first()
        with pytest.raises(ValueError, match='Enable Local fixture'):
            svc._rgn_resolve_target(row, None, None)
        with pytest.raises(ValueError, match='Enable Local fixture'):
            svc._rgn_resolve_target(row, None, 'local_fixture')
        with pytest.raises(ValueError, match='Enable Local fixture'):
            local.preflight('local', dataset_id, 'local_fixture')
    assert len(provider[0]) == 1


def test_stopped_candidate_cancels_just_admitted_job_and_stops_fanout(client, provider, monkeypatch):
    dataset_id = _dataset_with_ref(client)
    cancelled = []

    def stopped(**_):
        row = FaceDatasetImage.query.filter_by(dataset_id=dataset_id).first()
        db.session.delete(row)
        db.session.commit()
        return 'racing-job'

    registry.register(replace(registry.get('local_fixture'), local_enqueue=stopped), replace=True)
    monkeypatch.setattr(local, '_cancel_unlinked', lambda user, job: cancelled.append(job))
    with client.application.app_context():
        assert local.generate('local', dataset_id, _shots(3), 2, engine='local_fixture') == []
        assert FaceDatasetImage.query.filter_by(dataset_id=dataset_id).count() == 0
    assert cancelled == ['racing-job']


def test_failed_enqueue_leaves_visible_failed_candidate(client, provider):
    dataset_id = _dataset_with_ref(client)

    def failed(**_):
        raise RuntimeError('queue admission refused')

    registry.register(replace(registry.get('local_fixture'), local_enqueue=failed), replace=True)
    response = client.post(f'/api/dataset/{dataset_id}/generate', json={
        'generator': 'local_fixture', 'variations': _shots(1)})
    assert response.status_code == 409
    with client.application.app_context():
        row = FaceDatasetImage.query.filter_by(dataset_id=dataset_id).one()
        assert row.status == 'failed' and row.job_id is None


def test_unknown_legacy_single_engine_cannot_silently_run_klein(client):
    response = client.post('/api/dataset/1/generate', json={
        'generator': 'missing_plugin', 'variations': _shots(1)})
    assert response.status_code == 400
    assert 'unknown engine' in response.json['error']
