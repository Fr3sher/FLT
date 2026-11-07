"""Real public history/files and factory; no network, GPU or worker can start."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_public_backend_mount import factory  # noqa: F401
from app import config as cfg
from app.extensions import db
from app.models import CloudTrainingRun, FaceDataset, TrainingRunRecord
from app.services import cloud_local_continuation as continuation
from app.services import lora_training as lt


@pytest.fixture
def history(factory, tmp_path, monkeypatch):
    app = factory()
    with app.app_context():
        dataset = FaceDataset(id=3, user_id='local', name='Public fixture', trigger_word='fixture',
                              train_type='krea', train_variant='base')
        params = {'train_type': 'krea', 'base_model': '', 'variant': 'base', 'steps': 300}
        run = CloudTrainingRun(id=7, dataset_id=3, status='done', train_params=json.dumps(params))
        record = TrainingRunRecord(id=11, dataset_id=3, source='cloud', cloud_run_id=7,
                                   family='krea', base_model='', variant='base', steps=300,
                                   fingerprint='fixture', version=1)
        db.session.add_all([dataset, run, record])
        db.session.commit()
        store = cfg.checkpoints_root() / 'run_7'
        store.mkdir()
        source = store / 'lora_remote_000000100.safetensors'
        source.write_bytes(b'PUBLIC-CLOUD-CHECKPOINT-100')
        (store / 'lora_remote_000000300.safetensors').write_bytes(b'NEWER-CLOUD-CHECKPOINT')
        lane = tmp_path / 'local-lane'
        (lane / 'lora_fixture').mkdir(parents=True)
        old = lane / 'lora_fixture' / 'lora_fixture_000000100.safetensors'
        old.write_bytes(b'DIFFERENT-LOCAL-RUN-SAME-STEP')
        monkeypatch.setattr(lt, '_run_root', lambda *a, **kw: lane)
        monkeypatch.setattr(lt, 'assert_free_disk', lambda *a: None)
        yield SimpleNamespace(app=app, dataset=dataset, run=run, record=record,
                              source=source, lane=lane, old=old, params=params)


def resolve():
    return continuation.resolve_cloud_checkpoint('local', 3, 'krea', '', 'base', 11, 100)


def test_windows_stat_and_open_handle_use_the_same_creation_timestamp():
    # Reproduced on real Windows files: fstat's deprecated ctime can report the
    # write time, while stat reports creation; birthtime agrees on both APIs.
    values = dict(st_dev=1, st_ino=2, st_size=7, st_mtime_ns=500, st_birthtime_ns=100)
    path = SimpleNamespace(**values, st_ctime_ns=100)
    handle = SimpleNamespace(**values, st_ctime_ns=500)
    assert continuation._fingerprint(path) == continuation._fingerprint(handle)
    handle.st_mtime_ns = 501
    assert continuation._fingerprint(path) != continuation._fingerprint(handle)


def test_exact_cloud_source_remains_local_when_plugin_absent(history):
    assert history.app.extensions['lds_plugins'].records == {}
    chosen = resolve()
    assert chosen['record_id'] == 11 and chosen['step'] == 100
    assert Path(chosen['path']) == history.source.resolve()
    lt._expected_resume_record(chosen, 11, 3, 'krea', '', 'base', user_id='local')
    with pytest.raises(ValueError, match='no longer belongs'):
        lt._expected_resume_record({'record_id': 11, 'step': 100}, 11, 3, 'krea', '', 'base', user_id='local')


@pytest.mark.parametrize('change', ['user', 'dataset', 'table', 'family', 'base', 'variant',
                                  'run_id', 'deleted', 'dense', 'record_missing', 'step', 'file'])
def test_foreign_or_stale_identity_cannot_select_a_file(history, change):
    if change == 'user':
        history.dataset.user_id = 'another-account'
    elif change == 'dataset':
        history.run.dataset_id = 99
    elif change == 'table':
        history.run.dataset_table = 'video_dataset'
    elif change in ('family', 'base', 'variant'):
        setattr(history.record, {'family': 'family', 'base': 'base_model', 'variant': 'variant'}[change], 'other')
    elif change == 'run_id':
        history.record.cloud_run_id = 99
    elif change in ('deleted', 'dense'):
        history.params['dataset_deleted' if change == 'deleted' else 'training_mode'] = True if change == 'deleted' else 'full_transformer'
        history.run.train_params = json.dumps(history.params)
    elif change == 'record_missing':
        db.session.delete(history.record)
    elif change == 'step':
        history.source.rename(history.source.with_name('lora_remote_000000200.safetensors'))
    elif change == 'file':
        history.source.unlink()
    db.session.commit()
    with pytest.raises(ValueError, match='no longer belongs'):
        resolve()
    assert history.old.read_bytes() == b'DIFFERENT-LOCAL-RUN-SAME-STEP'


@pytest.mark.parametrize('field', ['train_type', 'base_model', 'variant'])
def test_cloud_snapshot_must_agree_with_record_and_request(history, field):
    history.params[field] = 'other'
    history.run.train_params = json.dumps(history.params)
    db.session.commit()
    with pytest.raises(ValueError, match='no longer belongs'):
        resolve()


def test_hardlinked_foreign_checkpoint_is_not_owned_by_the_run(history):
    history.source.unlink()
    os.link(history.old, history.source)
    with pytest.raises(ValueError, match='no longer belongs'):
        resolve()


def test_seed_copies_exact_cloud_bytes_and_preserves_both_source_and_old_lane(history):
    chosen = resolve()
    archived = continuation.seed_cloud_checkpoint('local', 3, 'krea', '', 'base', chosen)
    assert history.old.read_bytes() == b'PUBLIC-CLOUD-CHECKPOINT-100'
    assert history.source.read_bytes() == b'PUBLIC-CLOUD-CHECKPOINT-100'
    assert (Path(archived) / 'lora_fixture' / history.old.name).read_bytes() == b'DIFFERENT-LOCAL-RUN-SAME-STEP'
    assert list(history.old.parent.iterdir()) == [history.old]


@pytest.mark.parametrize('failure', ['stale', 'missing', 'copy', 'disk', 'record_during_copy', 'file_during_copy', 'rename'])
def test_failed_seed_preserves_existing_local_lane(history, monkeypatch, failure):
    chosen = resolve()
    def fail(*args, **kwargs):
        raise OSError('fixture copy failed')
    if failure == 'stale':
        history.source.write_bytes(b'REPLACED-CLOUD-CHECKPOINT')
    elif failure == 'missing':
        history.source.unlink()
    elif failure == 'copy':
        monkeypatch.setattr(continuation.shutil, 'copyfileobj', fail)
    elif failure == 'disk':
        monkeypatch.setattr(lt, 'assert_free_disk', fail)
    elif failure == 'rename':
        monkeypatch.setattr(continuation.os, 'replace', fail)
    else:
        copy = continuation.shutil.copyfileobj
        def mutate_after_copy(*args, **kwargs):
            copy(*args, **kwargs)
            if failure == 'record_during_copy':
                history.run.dataset_id = 99
                db.session.commit()
            else:
                with history.source.open('ab') as changed:
                    changed.write(b'CHANGED')
        monkeypatch.setattr(continuation.shutil, 'copyfileobj', mutate_after_copy)
    with pytest.raises((ValueError, OSError)):
        continuation.seed_cloud_checkpoint('local', 3, 'krea', '', 'base', chosen)
    assert history.old.read_bytes() == b'DIFFERENT-LOCAL-RUN-SAME-STEP'
    assert not list(history.lane.parent.glob('local-lane_superseded_*'))


def test_harvested_weights_never_claim_a_full_optimizer_state(history, monkeypatch):
    for name in ('assert_interpreter_ready', 'assert_zimage_custom_recipe_confirmed', 'assert_trainable'):
        monkeypatch.setattr(lt, name, lambda *a, **kw: None)
    with pytest.raises(ValueError, match='weights-only local continuation'):
        lt.continue_training('local', 3, train_type='krea', base_model='', variant='base',
                             from_step=100, expected_record_id=11, resume_mode='full_state',
                             state_bundle_id='0123456789abcdef0123456789abcdef')
    assert history.old.read_bytes() == b'DIFFERENT-LOCAL-RUN-SAME-STEP'


def test_real_continue_dispatch_seeds_cloud_owner_then_calls_local_launch_only(history, monkeypatch):
    for name in ('assert_interpreter_ready', 'assert_zimage_custom_recipe_confirmed', 'assert_trainable',
                 '_assert_no_vision_pass_on_gpu', 'preflight_custom_paths'):
        monkeypatch.setattr(lt, name, lambda *a, **kw: None)
    monkeypatch.setattr(lt, 'is_installed', lambda: True)
    monkeypatch.setattr(lt, '_aitoolkit_supports_krea', lambda: True)
    monkeypatch.setattr(lt, '_output_dir', lambda: history.lane.parent)
    monkeypatch.setattr(lt, 'list_checkpoints', lambda *a, **kw: pytest.fail('must not substitute local same-step file'))
    calls = []
    def launch(user, dataset_id, **kwargs):
        assert history.old.read_bytes() == b'PUBLIC-CLOUD-CHECKPOINT-100'
        calls.append((user, dataset_id, kwargs))
        return {'ok': True}
    monkeypatch.setattr(lt, 'launch_training', launch)
    result = lt.continue_training('local', 3, train_type='krea', base_model='', variant='base',
                                  from_step=100, extra_steps=200, expected_record_id=11)
    assert result['resumed_from'] == 100 and result['target_steps'] == 300
    assert len(calls) == 1
    assert calls[0][0:2] == ('local', 3)
    assert calls[0][2]['parent_record_id'] == 11
    assert calls[0][2]['resumed_from'] == 100
    assert history.source.read_bytes() == b'PUBLIC-CLOUD-CHECKPOINT-100'


def test_existing_local_owner_still_seeds_its_own_lane(history, monkeypatch):
    history.record.source = 'local'
    db.session.commit()
    for name in ('assert_interpreter_ready', 'assert_zimage_custom_recipe_confirmed', 'assert_trainable'):
        monkeypatch.setattr(lt, name, lambda *a, **kw: None)
    monkeypatch.setattr(lt, 'list_checkpoints', lambda *a, **kw: [
        {'step': 100, 'filename': history.old.name, 'record_id': 11}])
    calls = []
    monkeypatch.setattr(lt, 'launch_training', lambda *a, **kw: calls.append(kw) or {'ok': True})
    result = lt.continue_training('local', 3, train_type='krea', base_model='', variant='base',
                                  from_step=100, expected_record_id=11)
    assert result['resumed_from'] == 100 and len(calls) == 1
    assert calls[0]['parent_record_id'] == 11
    assert history.old.read_bytes() == b'DIFFERENT-LOCAL-RUN-SAME-STEP'
    assert history.source.read_bytes() == b'PUBLIC-CLOUD-CHECKPOINT-100'
