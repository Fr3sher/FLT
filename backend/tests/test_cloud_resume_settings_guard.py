"""The staging guard that refuses a cloud run whose Dataset training options
moved after the run was requested — and why a CONTINUE must not trip it.

A fresh launch freezes the dataset's `train_settings` column verbatim, so a raw
comparison was true enough. A continue does NOT: it folds the parent
checkpoint's recorded topology (rank / alpha / network_type) into the frozen
copy so the resumed run emits tensors the checkpoint can load. Those keys live
in `train_settings` only when the user set them BY HAND — left on auto they are
absent from the dataset and present in the snapshot, and the old text
comparison then reported a change the user never made (reported 2026-08-12,
cloud run 16: "The Dataset training options changed after this cloud run was
requested", on an untouched dataset).

The guard must therefore compare what the USER can change, tolerating exactly
the keys the resume itself injected — and nothing more.
"""
import json

import pytest


@pytest.fixture()
def ct(app):
    from app.services import cloud_training
    return cloud_training


def test_continue_on_an_untouched_dataset_is_not_reported_as_changed(ct):
    """The reported bug: auto rank/alpha, dataset never edited, continue refused."""
    observed = json.dumps({'resolution': '768', 'save_every': 250})
    topology = {'rank': 16, 'alpha': 16, 'network_type': 'lora'}
    snapshot = ct._merge_resume_overrides(observed, topology)

    # Precondition — the snapshot really is a different string, which is what
    # the old `!=` tripped on. If this ever stops being true the test below
    # would pass for the wrong reason.
    assert snapshot != observed

    assert ct._train_settings_drifted(observed, snapshot, topology) is False


def test_a_real_settings_change_is_still_caught(ct):
    """The guard's whole point: the dataset moved under a requested run."""
    requested = json.dumps({'resolution': '768', 'save_every': 250})
    topology = {'rank': 16, 'alpha': 16, 'network_type': 'lora'}
    snapshot = ct._merge_resume_overrides(requested, topology)
    observed_now = json.dumps({'resolution': '1024', 'save_every': 250})

    assert ct._train_settings_drifted(observed_now, snapshot, topology) is True


def test_a_user_override_of_a_topology_key_is_caught(ct):
    """Tolerating an injected key must not mean ignoring it: a dataset that now
    pins rank=32 against a checkpoint trained at 16 is a real, unloadable
    divergence — the exact thing the topology fold exists to prevent."""
    topology = {'rank': 16, 'alpha': 16, 'network_type': 'lora'}
    snapshot = ct._merge_resume_overrides(json.dumps({'resolution': '768'}), topology)
    observed_now = json.dumps({'resolution': '768', 'rank': 32})

    assert ct._train_settings_drifted(observed_now, snapshot, topology) is True


def test_key_order_alone_is_not_a_change(ct):
    """`train_settings` is a Text column compared as text. Two writes with the
    same content in a different order must not read as a change."""
    snapshot = json.dumps({'resolution': '768', 'save_every': 250})
    observed = json.dumps({'save_every': 250, 'resolution': '768'})

    assert ct._train_settings_drifted(observed, snapshot, {}) is False


def test_a_fresh_launch_keeps_the_plain_comparison(ct):
    """No topology to tolerate: absent-vs-empty and equal blobs stay equal, and
    a change is still a change."""
    assert ct._train_settings_drifted(None, None, {}) is False
    assert ct._train_settings_drifted(None, json.dumps({'rank': 16}), {}) is True
    assert ct._train_settings_drifted(json.dumps({'rank': 16}), None, {}) is True
