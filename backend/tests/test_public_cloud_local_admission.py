"""A refused cloud continuation cannot move a pre-existing local lane."""
import pytest

from test_public_backend_mount import factory  # noqa: F401
from test_public_cloud_local_continuation import history  # noqa: F401
from app.extensions import db
from app.models import FaceDataset
from app.services import lora_training as lt

REAL_RUN_ROOT = lt._run_root


@pytest.fixture
def ready_local(history, monkeypatch):
    for name in ('assert_interpreter_ready', 'assert_zimage_custom_recipe_confirmed',
                 'assert_trainable', '_assert_no_vision_pass_on_gpu', 'preflight_custom_paths'):
        monkeypatch.setattr(lt, name, lambda *a, **kw: None)
    monkeypatch.setattr(lt, 'is_installed', lambda: True)
    monkeypatch.setattr(lt, '_aitoolkit_supports_krea', lambda: True)
    return history


def resume():
    return lt.continue_training('local', 3, train_type='krea', base_model='',
                                variant='base', from_step=100, expected_record_id=11)


def test_collision_refusal_preserves_other_dataset_lane_byte_for_byte(ready_local, monkeypatch, tmp_path):
    monkeypatch.setattr(lt, '_run_root', REAL_RUN_ROOT)
    monkeypatch.setattr(lt, '_output_dir', lambda: tmp_path / 'output')
    other = FaceDataset(id=4, user_id='local', name='Other dataset', trigger_word='fixture',
                        train_type='krea', train_variant='base')
    db.session.add(other)
    db.session.commit()
    lane = lt._run_root(other, '', 'krea', 'base')
    assert lane == lt._run_root(ready_local.dataset, '', 'krea', 'base')
    file = lane / 'lora_fixture/lora_fixture_000000100.safetensors'
    file.parent.mkdir(parents=True)
    original = b'OTHER-DATASET-LOCAL-CHECKPOINT'
    file.write_bytes(original)
    assert lt.find_run_collision('local', 3, base_model='', variant='base').id == 4
    with pytest.raises(ValueError, match='training collision'):
        resume()
    assert file.read_bytes() == original
    assert list(lane.parent.glob(lane.name + '_superseded_*')) == []
    assert ready_local.source.read_bytes() == b'PUBLIC-CLOUD-CHECKPOINT-100'


def test_unavailable_trainer_refuses_before_copy(ready_local, monkeypatch):
    monkeypatch.setattr(lt, 'is_installed', lambda: False)
    with pytest.raises(RuntimeError, match='ai-toolkit is not configured'):
        resume()
    assert ready_local.old.read_bytes() == b'DIFFERENT-LOCAL-RUN-SAME-STEP'
    assert list(ready_local.lane.parent.glob('local-lane_superseded_*')) == []


def test_normalized_recipe_cannot_redirect_the_cloud_seed(ready_local, monkeypatch):
    monkeypatch.setattr(lt, '_lt_refuse_or_resolve', lambda *a: (ready_local.dataset, 'other', 'base', 'krea'))
    with pytest.raises(ValueError, match='resolved local training recipe'):
        resume()
    assert ready_local.old.read_bytes() == b'DIFFERENT-LOCAL-RUN-SAME-STEP'
