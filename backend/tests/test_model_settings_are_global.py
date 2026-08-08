"""One model setting per engine, wherever it is edited.

THE DECISION
------------
A model setting is GLOBAL. Changing the Klein model from a dataset screen, or the
Krea base from the work screen, or either one from Settings, are the same act on
the same value — and it applies to every run from then on, not to the batch in
front of you.

Klein used to be per-dataset (a `face_dataset.klein_model` column). That made the
same question — "which Klein model runs?" — answerable two different ways
depending on which screen asked, and let Settings disagree with the dataset you
were looking at.

WHY THIS FILE EXISTS AT ALL
---------------------------
The switch broke NOTHING in the existing suite: 329 Klein tests stayed green,
because every one of them writes and reads through the same accessor pair, so a
round-trip works whichever storage sits underneath. Nothing pinned the property
that actually changed. That is precisely the shape of a behaviour that silently
reverts one day, so it gets pinned here, from the outside: write on one dataset,
read from ANOTHER.

⚠️ The column itself is left in place and unread. Dropping it would destroy picks
made under the old behaviour, and SQLite cannot drop a column on the versions
this app supports. An unread column costs nothing; a deleted one cannot be
reconsidered.
"""
import pytest

from app.config import LOCAL_USER as LOCAL


@pytest.fixture
def two_datasets(app):
    from app.services import face_dataset_service as svc
    with app.app_context():
        a = svc.create_dataset(LOCAL, 'First', 'first')
        b = svc.create_dataset(LOCAL, 'Second', 'second')
        yield svc, a.id, b.id


def test_a_klein_pick_made_on_one_dataset_is_read_by_another(two_datasets):
    """THE assertion. It fails the moment the setting goes back to per-dataset
    storage, and it is the only thing in the suite that would."""
    svc, a, b = two_datasets
    svc.set_dataset_klein_model(LOCAL, a, 'flux-2-klein-9b-fp8.safetensors')
    assert svc.dataset_klein_model(svc.get_dataset(LOCAL, b)) \
        == 'flux-2-klein-9b-fp8.safetensors', (
            'the Klein model is per-dataset again — Settings and the dataset '
            'screens can now disagree about which model runs')


def test_the_klein_pick_and_the_global_setting_are_the_same_value(two_datasets, app):
    """Not "kept in sync" — the SAME key. Two values that agree today are two
    values that drift, and the drift is invisible until a run uses the wrong one."""
    from app import config as cfg
    svc, a, _b = two_datasets
    with app.app_context():
        svc.set_dataset_klein_model(LOCAL, a, 'flux-2-klein-9b-bf16.safetensors')
        assert (cfg.get('klein.unet') or '') == 'flux-2-klein-9b-bf16.safetensors'
        cfg.save_config({'klein': {'unet': 'another.safetensors'}})
        assert svc.dataset_klein_model(None) == 'another.safetensors'


def test_clearing_from_any_screen_clears_it_everywhere(two_datasets, app):
    from app import config as cfg
    svc, a, b = two_datasets
    svc.set_dataset_klein_model(LOCAL, a, 'flux-2-klein-9b-fp8.safetensors')
    assert svc.set_dataset_klein_model(LOCAL, b, '') is None
    with app.app_context():
        assert (cfg.get('klein.unet') or '') == ''


def test_a_write_still_needs_a_real_dataset(two_datasets):
    """The value is global, the gesture is still made from a screen. A write that
    names a dataset nobody owns is a bug worth a 404, not a silent global edit."""
    svc, _a, _b = two_datasets
    with pytest.raises(ValueError):
        svc.set_dataset_klein_model(LOCAL, 999999, 'flux-2-klein-9b-fp8.safetensors')


def test_a_path_is_still_refused_now_that_it_writes_a_global(two_datasets):
    """The guard has to survive the storage change: the picker sends bare names,
    and a separator means the value did not come from the UI. It matters MORE now
    — a bad value here poisons every dataset at once, not one."""
    svc, a, _b = two_datasets
    for bad in ('klein/x.safetensors', 'klein\\x.safetensors', '..'):
        with pytest.raises(ValueError):
            svc.set_dataset_klein_model(LOCAL, a, bad)
