"""The completed LoRA must outrank an earlier numbered save."""
from types import SimpleNamespace


def test_final_checkpoint_outranks_numbered_saves(app):
    from lds_cloud_training import cloud_training as ct
    files = [
        {'path': '/output/training_run/training_run_000000250.safetensors', 'size': 100},
        {'path': '/output/training_run/optimizer.pt', 'size': 100},
    ]
    remote = SimpleNamespace(list_files=lambda _job: files)
    assert ct._newest_remote_checkpoint(remote, 'job') == files[0]
    files.append({'path': '/output/training_run/training_run_000000500.safetensors', 'size': 100})
    assert ct._newest_remote_checkpoint(remote, 'job') == files[-1]
    final = {'path': '/output/training_run/training_run.safetensors', 'size': 100}
    files.insert(0, final)
    assert ct._newest_remote_checkpoint(remote, 'job') == final
    files.clear()
    assert ct._newest_remote_checkpoint(remote, 'job') is None
