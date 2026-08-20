"""Auto-apply the dataset's own trained LoRA to Krea variation generation (A).

latest_trained_lora must return the NEWEST deployed checkpoint matching the
dataset's trigger in the krea pool (mtime wins, so a re-imported/re-trained LoRA
supersedes an older one), and None when nothing is deployed."""
import os

import pytest


def _ds():
    from types import SimpleNamespace
    return SimpleNamespace(trigger_word='G1_AI', train_type='krea', id=2)


def test_latest_trained_lora_picks_the_newest_deployed(monkeypatch, tmp_path):
    import app.services.lora_test_studio as lts
    from app.services.lora_test_studio import latest_trained_lora

    old = tmp_path / 'old.safetensors'
    new = tmp_path / 'new.safetensors'
    old.write_bytes(b'x')
    new.write_bytes(b'x')
    old_mtime = os.path.getmtime(old)
    os.utime(new, (old_mtime + 100, old_mtime + 100))

    def fake_match(ds, family=None):
        return [{'filename': 'krea/old.safetensors'},
                {'filename': 'krea/new.safetensors'}]

    def fake_resolve(name):
        return tmp_path / os.path.basename(name)

    monkeypatch.setattr(lts, '_trigger_match_checkpoints', fake_match)
    monkeypatch.setattr(lts, '_resolve_lora_abs_path', fake_resolve)

    assert latest_trained_lora(_ds(), 'krea') == 'krea/new.safetensors'


def test_latest_trained_lora_returns_none_when_nothing_deployed(monkeypatch):
    import app.services.lora_test_studio as lts
    from app.services.lora_test_studio import latest_trained_lora
    monkeypatch.setattr(lts, '_trigger_match_checkpoints', lambda ds, family=None: [])
    assert latest_trained_lora(_ds(), 'krea') is None


def test_train_lora_strength_defaults_to_0_6_and_clamps(app, monkeypatch):
    # Default config ships 0.6 (opt-in reinforcement); a bad value clamps.
    import app.config as cfg
    from app.services import krea_edit_helper as keh
    monkeypatch.setattr(cfg, 'get', lambda key, default=None: {
        'krea.train_lora_strength': 0.6,
    }.get(key, default))
    assert keh.train_lora_strength() == 0.6
    monkeypatch.setattr(cfg, 'get', lambda key, default=None: {
        'krea.train_lora_strength': 99,
    }.get(key, default))
    assert keh.train_lora_strength() == 1.5
    monkeypatch.setattr(cfg, 'get', lambda key, default=None: {
        'krea.train_lora_strength': -5,
    }.get(key, default))
    assert keh.train_lora_strength() == 0.0
