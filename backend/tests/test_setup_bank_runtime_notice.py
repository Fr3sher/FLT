"""Repair receipts distinguish an installed environment from a selected runtime."""
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_runs(monkeypatch):
    from app import setup_installer as installer
    monkeypatch.setattr(installer, '_runs', {})
    monkeypatch.setattr(installer, '_pip_current', None)
    monkeypatch.setattr(installer, '_pip_queue', [])


@pytest.mark.parametrize('action,key,profile', [
    ('bank_scoring', 'bank_scoring', 'scoring'),
    ('bank_siglip2', 'bank_semantic', 'semantic'),
])
@pytest.mark.parametrize('selection', ['managed', 'external_ok', 'external_broken'])
def test_bank_repair_reports_install_and_selected_runtime_separately(
        app, monkeypatch, tmp_path, action, key, profile, selection):
    from app import config, setup_installer as installer
    from app.services import bank_semantic_models as assets

    managed = str(tmp_path / 'managed' / 'python.exe')
    external = str(tmp_path / 'external' / 'python.exe')
    calls, probes = [], []
    monkeypatch.setattr(installer, '_bank_scoring_env_python', lambda: managed)
    monkeypatch.setattr(installer, '_ensure_bank_scoring_env', lambda *a, **k: managed)
    monkeypatch.setattr(installer, '_install_cpu_torch_pair',
                        lambda action, python: calls.append(python) or 0)
    monkeypatch.setattr(installer, '_run_pip',
                        lambda action, command: calls.append(command[0]) or 0)
    monkeypatch.setattr(assets, 'models_root', lambda: tmp_path / 'weights')
    monkeypatch.setattr(assets, 'weights_present', lambda root: True)

    def verify(feature, python, **kwargs):
        probes.append(python)
        return not (python == external and selection == 'external_broken')

    monkeypatch.setattr(installer, '_verify_capability_import', verify)
    with app.app_context():
        configured = '' if selection == 'managed' else external
        config.save_config({key: {'python': configured}})
        installer._runs[action] = installer._new_run()
        worker = installer._run_bank_scoring if action == 'bank_scoring' else installer._run_bank_siglip2
        rc = worker(action)
        assert rc == (1 if selection == 'external_broken' else 0)
        selected = managed if selection == 'managed' else external
        assert config.get(f'{key}.python') == selected
        receipt = installer.status(action)['runtime_notice']
        assert receipt == {
            'profile': profile, 'managed_python': managed, 'effective_python': selected,
            'uses_managed': selection == 'managed', 'managed_installed': True,
            'selected_imports_ok': selection != 'external_broken',
            'compute_tested': False, 'selection_failed': False,
        }
        # Repeated polling only reads the receipt; it does not re-import or compute.
        before = list(probes)
        receipt['selected_imports_ok'] = None
        assert installer.status(action)['runtime_notice']['selected_imports_ok'] is not None
        assert probes == before
    assert calls and all(python == managed for python in calls)
    assert probes == ([managed] if selection == 'managed' else [managed, external])


def test_failed_managed_install_has_no_ready_receipt(app, monkeypatch, tmp_path):
    from app import setup_installer as installer
    managed = str(tmp_path / 'python.exe')
    monkeypatch.setattr(installer, '_bank_scoring_env_python', lambda: managed)
    monkeypatch.setattr(installer, '_ensure_bank_scoring_env', lambda *a, **k: managed)
    monkeypatch.setattr(installer, '_install_cpu_torch_pair', lambda *a: 1)
    with app.app_context():
        installer._runs['bank_scoring'] = installer._new_run()
        assert installer._run_bank_scoring('bank_scoring') == 1
        assert installer.status('bank_scoring')['runtime_notice'] is None


def test_new_install_clears_previous_receipt_before_worker_starts(app, monkeypatch):
    from app import setup_installer as installer
    monkeypatch.setattr(installer.threading, 'Thread',
                        lambda **kwargs: SimpleNamespace(start=lambda: None))
    with app.app_context():
        installer._runs['bank_scoring'] = {
            **installer._new_run(), 'state': 'success',
            'runtime_notice': {'managed_installed': True},
        }
        assert installer.start('bank_scoring')['runtime_notice'] is None
        assert installer.status('bank_scoring')['state'] == 'running'
