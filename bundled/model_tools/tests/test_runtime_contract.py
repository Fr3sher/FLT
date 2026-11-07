"""Model tools consumer of API 1.15: isolated probes and full worker lifetime."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'bundled/model_tools')]
from lds_model_tools import fp8_quantize, lora_merge_job, runtime


@pytest.fixture
def managed(monkeypatch):
    events = []
    reservations = []
    python = str(Path('C:/t/owned-model-engine/python.exe').absolute())
    state = {'ready': True, 'can_install': True,
             'action': 'plugin_environment:model_tools', 'reason': None, 'python': python}

    @contextmanager
    def lease():
        reservations.append('environment')
        events.append('enter')
        try:
            yield state['python']
        finally:
            events.append('leave')

    @contextmanager
    def worker():
        reservations.append('worker')
        events.append('enter')
        try:
            yield
        finally:
            events.append('leave')

    ctx = SimpleNamespace(plugin_environment=lambda: dict(state), use_plugin_env=lease, use_plugin_worker=worker)
    monkeypatch.setattr(runtime, '_context', lambda: ctx)
    monkeypatch.setattr(runtime, 'explicit_python', lambda: '')
    runtime.clear_probe_cache()
    return SimpleNamespace(python=python, state=state, events=events, reservations=reservations)


def test_automatic_selection_uses_only_its_owned_ready_environment(managed, monkeypatch):
    assert runtime.candidates() == [managed.python]
    managed.state.update(ready=False, python=None)
    monkeypatch.setattr(runtime, 'probe', lambda _: pytest.fail('No missing-environment probe'))
    assert runtime.candidates() == []
    result = runtime.status()
    assert not result['ready'] and result['python'] is None
    assert result['environment']['action'] == 'plugin_environment:model_tools'
    assert 'Install the CPU engine' in result['reason']


def test_explicit_override_is_exclusive_and_never_acquires_or_installs_managed_env(managed, monkeypatch):
    monkeypatch.setattr(runtime, 'explicit_python', lambda: 'C:/t/explicit/python.exe')
    assert runtime.candidates() == ['C:/t/explicit/python.exe']
    monkeypatch.setattr(runtime, 'probe', lambda _: None)
    assert not runtime.interpreter()['ready'], 'An unknown probe is not readiness'
    with runtime.use_worker('C:/t/explicit/python.exe') as python:
        assert python == 'C:/t/explicit/python.exe'
    assert managed.events == ['enter', 'leave']
    assert managed.reservations == ['worker'], 'Reserve product work without borrowing managed packages.'
    with pytest.raises(RuntimeError, match='override changed'):
        with runtime.use_worker(managed.python):
            pytest.fail('changed override must not execute the prior plan')


def test_probe_runs_real_import_command_under_same_cpu_worker_policy_and_lease(managed, monkeypatch):
    seen = []

    def run(argv, **kwargs):
        assert managed.events[-1] == 'enter'
        assert argv[0] == managed.python
        assert argv[1] == '-I'
        assert 'import json, torch' in argv[-1]
        assert 'device="cpu"' in argv[-1]
        assert kwargs['env']['PYTHONNOUSERSITE'] == '1'
        assert 'PYTHONHOME' not in kwargs['env'] and 'PYTHONPATH' not in kwargs['env']
        seen.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'torch': True, 'torch_version': 'test-cpu'}))

    monkeypatch.setattr(runtime.subprocess, 'run', run)
    assert runtime.interpreter()['ready']
    assert managed.events == ['enter', 'leave']
    assert runtime.interpreter()['ready']
    assert len(seen) == 1, 'cached success avoids re-importing torch on every plan'
    assert managed.events == ['enter', 'leave'] * 2, 'A cached probe still checks current admission.'
    runtime.clear_probe_cache()
    assert runtime.interpreter()['ready']
    assert len(seen) == 2


@pytest.mark.parametrize('probe_result', [None, {'torch': False}])
def test_failed_or_unknown_probe_has_actionable_repair_and_is_never_ready(managed, monkeypatch, probe_result):
    monkeypatch.setattr(runtime, 'probe', lambda _: probe_result)
    result = runtime.interpreter()
    assert not result['ready']
    assert 'repair the CPU engine' in result['reason']


def test_changed_environment_cannot_run_an_old_plan_and_always_releases(managed):
    with pytest.raises(RuntimeError, match='engine changed'):
        with runtime.use_worker('C:/t/previous/python.exe'):
            pytest.fail('stale environment must be refused')
    assert managed.events == ['enter', 'leave']


@pytest.mark.parametrize('kind', ['quantize', 'merge'])
@pytest.mark.parametrize('mode', ['managed', 'override'])
@pytest.mark.parametrize('outcome', ['success', 'cancel', 'wait_timeout', 'popen_error'])
def test_workers_keep_the_lease_through_stream_wait_kill_and_cleanup(managed, monkeypatch, tmp_path, kind, outcome, mode):
    if mode == 'override':
        monkeypatch.setattr(runtime, 'explicit_python', lambda: managed.python)
    monkeypatch.setenv('PYTHONPATH', 'C:/t/unrelated-packages')
    monkeypatch.setenv('PYTHONHOME', 'C:/t/unrelated-python')
    module = fp8_quantize if kind == 'quantize' else lora_merge_job
    prefix = 'LDS_FP8' if kind == 'quantize' else 'LDS_MERGE'
    spec = tmp_path / 'merge-spec.json'
    spec.write_text('{}')
    if kind == 'merge':
        monkeypatch.setattr(module, 'write_spec', lambda _: str(spec))
    progress = []

    class Process:
        @property
        def stdout(self):
            assert managed.events[-1] != 'leave'
            yield f'{prefix}_PROGRESS 1 1\n'
            yield f'{prefix}_RESULT {{"ok": true}}\n'

        def kill(self):
            assert managed.events[-1] != 'leave'
            managed.events.append('kill')

        def wait(self, timeout=None):
            assert managed.events[-1] != 'leave'
            managed.events.append('wait')
            if timeout and outcome == 'wait_timeout':
                raise subprocess.TimeoutExpired('fake-worker', timeout)
            return 0

    def popen(argv, **kwargs):
        assert managed.events == ['enter']
        assert argv[0] == managed.python
        assert argv[1] == '-I'
        assert kwargs['env']['PYTHONNOUSERSITE'] == '1'
        assert not any(key.upper() in {'PYTHONHOME', 'PYTHONPATH'} for key in kwargs['env'])
        managed.events.append('popen')
        if outcome == 'popen_error':
            raise OSError('test cannot start')
        return Process()

    monkeypatch.setattr(module.subprocess, 'Popen', popen)
    kwargs = {'progress': lambda done, total: progress.append((done, total)),
              'cancelled': lambda: outcome == 'cancel'}

    def invoke():
        if kind == 'quantize':
            return module.run_worker(managed.python, 'src', 'dst', **kwargs)
        return module.run_worker({'python': managed.python}, **kwargs)

    if outcome in ('cancel', 'popen_error'):
        with pytest.raises(ValueError, match='stopped|could not be started'):
            invoke()
    else:
        assert invoke()['ok']
    assert managed.events[0] == 'enter' and managed.events[-1] == 'leave'
    assert managed.reservations == ['worker' if mode == 'override' else 'environment']
    if outcome != 'popen_error':
        assert progress == [(1, 1)]
        assert 'wait' in managed.events
    if outcome == 'wait_timeout':
        assert managed.events[-4:] == ['wait', 'kill', 'wait', 'leave']
    if kind == 'merge':
        assert not spec.exists(), 'the lease encloses cleanup of the merge specification'


def test_override_lease_yields_the_choice_revalidated_after_admission(managed, monkeypatch):
    choices = iter(['C:/t/stale/python.exe', 'C:/t/current/python.exe'])
    monkeypatch.setattr(runtime, 'explicit_python', lambda: next(choices))
    with runtime.use_worker('C:/t/current/python.exe') as python:
        assert python == 'C:/t/current/python.exe'
    assert managed.events == ['enter', 'leave'] and managed.reservations == ['worker']
