"""The reported false-positive CUDA import, without touching a real GPU."""
from contextlib import contextmanager, nullcontext, redirect_stdout
import io
import json
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

pytestmark = pytest.mark.plugins()


@pytest.fixture()
def health(app, monkeypatch):
    from app.services import scoring_python_health as health
    from app.services import scoring_python as sp
    facts = {'modules': {name: True for name in sp._DEP_MODULES},
             'symbols': {f'{mod}:{attr}': True for mod, attr in sp._DEP_ATTRS},
             'python': '3.12.1', 'torch_version': 'test', 'cuda': True}
    monkeypatch.setattr(sp, 'probe', lambda *a, **kw: facts)
    monkeypatch.setattr(health, 'gpu_exclusive_vision_window', lambda **kw: nullcontext())
    return health, facts


def _result(status='passed', **extra):
    payload = {'status': status, 'detail': 'Synthetic checks only',
               'checks': ['convolution', 'attention'], 'cudnn_version': 92000}
    payload.update(extra)
    return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr='')


def test_imports_can_pass_while_calculation_reports_cudnn_mismatch(health, monkeypatch):
    h, facts = health
    assert h.scoring_python.describe('/tmp/ml/python', facts)['status'] == 'gpu_ready'
    assert 'not tested' in h.scoring_python.describe('/tmp/ml/python', facts)['detail']
    error = 'CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH token=' + 'x' * 24
    monkeypatch.setattr(h.subprocess, 'run', lambda *a, **kw: _result('failed', detail=error))
    r = h.check('/tmp/ml/python')
    assert r['status'] == 'failed' and 'SUBLIBRARY_VERSION_MISMATCH' in r['detail']
    assert 'x' * 24 not in r['detail']
    assert h.scoring_python.cfg.get('bank_scoring.python') == ''


def test_cuda_check_owns_window_for_entire_worker_and_uses_bank_environment(health, monkeypatch):
    h, _ = health
    entered = []

    @contextmanager
    def window(**kw):
        entered.append(True)
        try:
            yield
        finally:
            entered.pop()

    def run(argv, **kw):
        assert entered
        assert argv[:3] == ['/tmp/ml/python', '-s', '-c']
        assert argv[-1] == 'cuda'
        assert kw['env']['PYTHONNOUSERSITE'] == '1'
        assert kw['timeout'] == h.CHECK_TIMEOUT
        return _result()

    monkeypatch.setattr(h, 'gpu_exclusive_vision_window', window)
    monkeypatch.setattr(h.subprocess, 'run', run)
    assert h.check('/tmp/ml/python')['status'] == 'passed'
    assert entered == []


def test_busy_gpu_does_not_start_calculation(health, monkeypatch):
    h, _ = health

    @contextmanager
    def busy(**kw):
        raise h.GpuBusyError('training')
        yield

    monkeypatch.setattr(h, 'gpu_exclusive_vision_window', busy)
    monkeypatch.setattr(h.subprocess, 'run', lambda *a, **kw: pytest.fail('must not run'))
    assert h.check('/tmp/ml/python')['status'] == 'busy'


def test_cpu_check_does_not_reserve_or_touch_gpu(health, monkeypatch):
    h, facts = health
    facts['cuda'] = False
    monkeypatch.setattr(h, 'gpu_exclusive_vision_window', lambda **kw: pytest.fail('GPU touched'))
    def run(argv, **kw):
        assert argv[-1] == 'cpu'
        return _result()
    monkeypatch.setattr(h.subprocess, 'run', run)
    assert h.check('/tmp/ml/python')['device'] == 'cpu'


@pytest.mark.parametrize('outcome', ['timeout', 'garbage', 'partial', 'exit'])
def test_no_success_for_unfinished_or_broken_child(health, monkeypatch, outcome):
    h, _ = health
    def run(*a, **kw):
        if outcome == 'timeout':
            raise subprocess.TimeoutExpired('python', 90)
        if outcome == 'garbage':
            return SimpleNamespace(stdout='', stderr='private details', returncode=1)
        r = _result(checks=['convolution'] if outcome == 'partial' else ['convolution', 'attention'])
        if outcome == 'exit':
            r.returncode = 1
        return r
    monkeypatch.setattr(h.subprocess, 'run', run)
    assert h.check('/tmp/ml/python')['status'] == 'failed'


@pytest.mark.parametrize('profile,endpoint', [('scoring', 'scoring'), ('semantic', 'semantic'),
                                            ('watermark_detect', 'watermark')])
def test_explicit_check_route_and_bad_input(client, monkeypatch, profile, endpoint):
    from app.services import scoring_python_health as h
    calls = []
    def check(path, prof):
        calls.append((path, prof))
        return {'status': 'busy', 'detail': 'Busy'}
    monkeypatch.setattr(h, 'check', check)
    url = f'/api/{endpoint}-python/check'
    assert client.get(url).status_code == 405
    assert client.post(url, json=[]).status_code == 400
    assert client.post(url, json={'python': ['not a path']}).status_code == 400
    assert not calls
    r = client.post(url, json={'python': '/tmp/ml/python'})
    assert r.status_code == 409 and calls == [('/tmp/ml/python', profile)]


def test_detection_names_effective_and_managed_without_calculation(app, monkeypatch):
    from app import config as cfg, setup_installer
    from app.services import scoring_python as sp
    monkeypatch.setattr(setup_installer, '_bank_scoring_env_python', lambda: '/tmp/managed/python')
    monkeypatch.setattr(sp, 'candidates', lambda p: [])
    monkeypatch.setattr(sp, 'nvidia_present', lambda: True)
    cfg.save_config({'bank_scoring': {'python': '/tmp/borrowed/python'}})
    r = sp.detect(profile='semantic')
    assert r['selected'] == ''
    assert r['effective_python'] == '/tmp/borrowed/python'
    assert r['managed_python'] == '/tmp/managed/python' and not r['uses_managed']


@pytest.mark.parametrize('mismatch_at', [None, 'convolution', 'cudnn_attention'])
def test_actual_child_program_with_fake_torch(health, monkeypatch, mismatch_at):
    """Execute the shipped child, including the forced cuDNN attention branch."""
    h, _ = health
    torch = ModuleType('torch')
    nn = ModuleType('torch.nn')
    functional = ModuleType('torch.nn.functional')
    attention = ModuleType('torch.nn.attention')
    forced = []
    torch.__version__ = 'synthetic'
    torch.backends = SimpleNamespace(cudnn=SimpleNamespace(version=lambda: 92000))
    torch.set_num_threads = lambda n: None
    torch.float16, torch.float32 = 'half', 'float'
    torch.inference_mode = nullcontext
    torch.ones = lambda *a, **kw: object()
    torch.isfinite = lambda value: SimpleNamespace(all=lambda: True)
    torch.cuda = SimpleNamespace(synchronize=lambda: None)
    def conv(*args):
        if mismatch_at == 'convolution':
            raise RuntimeError('CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH')
        return object()
    def sdpa(*args):
        if forced and mismatch_at == 'cudnn_attention':
            raise RuntimeError('CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH')
        return object()
    @contextmanager
    def kernel(backends):
        forced.append(True)
        try:
            yield
        finally:
            forced.pop()
    functional.conv2d = conv
    functional.scaled_dot_product_attention = sdpa
    attention.SDPBackend = SimpleNamespace(CUDNN_ATTENTION='cudnn')
    attention.sdpa_kernel = kernel
    torch.nn, nn.functional, nn.attention = nn, functional, attention
    for mod in (torch, nn, functional, attention):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)
    monkeypatch.setattr(sys, 'argv', ['check', 'cuda'])
    out = io.StringIO()
    with redirect_stdout(out):
        exec(compile(h._CHECK_CODE, '<calculation-check>', 'exec'), {})
    result = json.loads(out.getvalue())
    assert result['status'] == ('failed' if mismatch_at else 'passed')
    if mismatch_at:
        assert 'SUBLIBRARY_VERSION_MISMATCH' in result['detail']
    else:
        assert result['checks'] == ['convolution', 'attention', 'cudnn_attention']
