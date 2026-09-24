"""Public engine and checkpoint admission with fake provider calls only."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from test_public_backend_mount import factory  # noqa: F401
from app import config as cfg
from app.engines import registry


@pytest.mark.parametrize('engine', ['nanobanana', 'chatgpt', 'openrouter'])
def test_api_engine_off_refuses_before_dataset_or_worker(factory, monkeypatch, engine):
    from app.services import face_dataset_service as fds
    app = factory()
    monkeypatch.setattr(fds, '_guard_not_bank_export', lambda *_: pytest.fail('must admit engine first'))
    with app.app_context():
        with pytest.raises(ValueError, match='unavailable'):
            fds.generate_variations_nanobanana(app, 'local', 1, [], 1, engine=engine)
        with pytest.raises(ValueError, match='unavailable'):
            fds._api_generate_fn(engine)
        assert fds.editable_engines() == ('klein', 'krea')
        assert cfg.get('engines.default') == 'klein'


def test_api_dispatch_uses_registered_product_and_rechecks_captured_callable(factory):
    from app.services import face_dataset_service as fds
    app = factory({'api_engines'})
    calls = []
    original = registry.get('chatgpt')
    registry.register(replace(original, generate=lambda: lambda *a, **kw: calls.append((a, kw)) or b'fake',
                              generate_kwargs=lambda: {'force_lane': 'fixture'}), replace=True)
    with app.app_context():
        fn = fds._api_generate_fn('chatgpt')
        assert fds._edit_engine_call('chatgpt', [b'fake'], 'fixture') == b'fake'
        assert calls[0][1]['force_lane'] == 'fixture'
        cfg.save_config({'plugins': {'enabled': {'api_engines': False}}})
        with pytest.raises(ValueError, match='unavailable'):
            fn([], 'fixture')
        assert len(calls) == 1
        assert {s['id'] for s in app.test_client().get('/api/engines').json['engines']} == {'klein', 'krea'}


@pytest.mark.parametrize('changed', ['record_id', 'dataset_id', 'source', 'family', 'base_model', 'variant'])
def test_expected_checkpoint_record_refuses_foreign_or_changed_identity(factory, monkeypatch, changed):
    from app.services import lora_training as lt
    factory()
    record = SimpleNamespace(id=12, dataset_id=1, source='local', family='klein', base_model='', variant='base')
    chosen = {'record_id': 12}
    if changed == 'record_id':
        chosen['record_id'] = 11
    else:
        setattr(record, changed, 'foreign')
    monkeypatch.setattr('app.services.checkpoint_registry.record_by_id', lambda _: record)
    with pytest.raises(ValueError, match='no longer belongs'):
        lt._expected_resume_record(chosen, 12, 1, 'klein', '', 'base')


def test_expected_checkpoint_accepts_exact_record_and_legacy_omission(factory, monkeypatch):
    from app.services import lora_training as lt
    factory()
    record = SimpleNamespace(dataset_id=1, source='local', family='klein', base_model='', variant='base')
    monkeypatch.setattr('app.services.checkpoint_registry.record_by_id', lambda _: record)
    lt._expected_resume_record({'record_id': 12}, 12, 1, 'klein', '', 'base')
    lt._expected_resume_record({}, None, 1, 'klein', '', 'base')
    with pytest.raises(ValueError, match='positive integer'):
        lt.continue_training('local', 1, expected_record_id=True)
