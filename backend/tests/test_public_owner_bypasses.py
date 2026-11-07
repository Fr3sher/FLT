"""The remaining core entry points must admit their active product first."""
from types import SimpleNamespace
from pathlib import Path

import pytest

from test_public_backend_mount import factory  # noqa: F401
from app import config as cfg
from app.extensions import db
from app.models import CloudTrainingRun, FaceDataset


@pytest.mark.parametrize('engine', ['klein', 'seedvr2'])
def test_off_restoration_refuses_resolve_preflight_and_enqueue(factory, engine):
    from app.services import face_dataset_service as fds
    from app.plugins.restoration import RestoreUnavailable
    app = factory()
    with app.app_context():
        with pytest.raises(RestoreUnavailable):
            fds.resolve_improve_engine(engine)
        with pytest.raises(RestoreUnavailable):
            fds._improve_preflight(engine)
        with pytest.raises(RestoreUnavailable):
            fds._enqueue_improve(engine, user_id='local', source=SimpleNamespace(filename='fixture.png'),
                                 source_path='fixture.png', prompt='fixture', label='fixture', dataset=None,
                                 extra_metadata={})


@pytest.mark.parametrize('engine,pid', [('klein', 'image_upscale'), ('seedvr2', 'seedvr2')])
def test_on_restoration_calls_registered_provider_and_closes_pending_disable(factory, engine, pid):
    from app.services import face_dataset_service as fds
    from app.plugins.restoration import RestoreUnavailable
    app = factory({pid})
    calls = []
    spec = app.extensions['lds_plugins'].restore_engines[engine]
    spec['preflight'] = lambda: calls.append('preflight')
    spec['enqueue'] = lambda **kwargs: calls.append(kwargs) or 'fake-job'
    if spec['profile']:
        spec['profile'] = lambda model: {'klein_model': model, 'sampler_steps': 4}
    with app.app_context():
        assert fds.resolve_improve_engine(engine) == engine
        fds._improve_preflight(engine)
        result = fds._enqueue_improve(engine, user_id='local', source=SimpleNamespace(filename='fixture.png'),
                                    source_path='fixture.png', prompt='fixture', label='fixture', dataset=None,
                                    extra_metadata={'fixture': True})
        assert result == 'fake-job' and calls[0] == 'preflight'
        assert calls[1]['source_filename'] == 'fixture.png'
        assert calls[1]['extra_metadata'] == {'fixture': True}
        assert ('prompt' in calls[1]) == (engine == 'klein')
        cfg.save_config({'plugins': {'enabled': {pid: False}}})
        with pytest.raises(RestoreUnavailable):
            fds._improve_preflight(engine)
        assert len(calls) == 2


@pytest.mark.parametrize('endpoint,payload', [
    ('/api/dataset/train/cloud/hub-presence', {'run_ids': [1]}),
    ('/api/dataset/1/train/run-checkpoint/delete', {'cloud_run_id': 1, 'filename': 'fixture.safetensors'}),
])
def test_off_cloud_core_entry_points_refuse_before_probe_or_provider(factory, endpoint, payload):
    app = factory()
    client = app.test_client()
    assert client.post(endpoint, json=payload).status_code == 409


def _runs(app):
    with app.app_context():
        own = FaceDataset(name='Fixture', trigger_word='fixture', user_id='local')
        foreign = FaceDataset(name='Other', trigger_word='other', user_id='other')
        db.session.add_all([own, foreign]); db.session.flush()
        runs = [CloudTrainingRun(dataset_id=d.id, dataset_table='face_dataset', status='done')
                for d in (own, foreign)]
        db.session.add_all(runs); db.session.commit()
        return own.id, runs[0].id, runs[1].id


def test_on_hub_check_uses_sdk_and_filters_foreign_runs(factory, monkeypatch):
    app = factory({'cloud_training'})
    _, own_run, foreign_run = _runs(app)
    monkeypatch.setattr('app.routes.training.ct._is_full_transformer_run', lambda _: True)
    monkeypatch.setattr('app.routes.training.ct._run_param', lambda run, _: f'fixture/{run.id}')
    calls = []
    def check_many(repos, **kwargs):
        calls.append(list(repos))
        return {repo: {'state': 'present'} for repo in calls[-1]}
    monkeypatch.setattr('lds_sdk.cloud_host.services.hub_presence.check_many', check_many)
    response = app.test_client().post('/api/dataset/train/cloud/hub-presence',
                                      json={'run_ids': [own_run, foreign_run]})
    assert response.status_code == 200
    assert set(response.json['results']) == {str(own_run)}
    assert calls == [[f'fixture/{own_run}']]


def test_cloud_delete_filters_dataset_and_user_before_sdk_dispatch(factory, monkeypatch):
    app = factory({'cloud_training'})
    own, own_run, foreign_run = _runs(app)
    calls = []
    monkeypatch.setattr('lds_sdk.cloud_training.delete_cloud_checkpoint',
                        lambda *args, **kwargs: calls.append((args, kwargs)) or 'fixture.safetensors')
    client = app.test_client()
    endpoint = f'/api/dataset/{own}/train/run-checkpoint/delete'
    assert client.post(endpoint, json={'cloud_run_id': foreign_run}).status_code == 404
    assert not calls
    assert client.post(endpoint, json={'cloud_run_id': own_run, 'filename': 'fixture.safetensors'}).status_code == 200
    assert calls == [((own, own_run, 'fixture.safetensors'), {'dataset_table': 'face_dataset'})]


def test_cloud_delete_real_sdk_moves_only_permitted_local_fixture_when_on(factory):
    from app.services import cloud_training as history
    app = factory({'cloud_training'})
    own, own_run, _ = _runs(app)
    with app.app_context():
        run = db.session.get(CloudTrainingRun, own_run)
        fixture = Path(history.checkpoint_store_dir(run, create=True)) / 'fixture.safetensors'
        fixture.write_bytes(b'fake checkpoint fixture')
    endpoint = f'/api/dataset/{own}/train/run-checkpoint/delete'
    payload = {'cloud_run_id': own_run, 'filename': fixture.name}
    client = app.test_client()
    cfg.save_config({'plugins': {'enabled': {'cloud_training': False}}})
    assert client.post(endpoint, json=payload).status_code == 409
    assert fixture.read_bytes() == b'fake checkpoint fixture'
    cfg.save_config({'plugins': {'enabled': {'cloud_training': True}}})
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200, response.json
    assert response.json['removed'] == fixture.name
    assert not fixture.exists()
