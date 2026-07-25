"""✨ Score on a GPU Python you already own.

The trap this feature exists to avoid: an interpreter can have a perfect CUDA
torch and STILL be unable to run the pass, because bank_score_infer.py also
imports open_clip and transformers/timm. Accepting it on `torch.cuda.is_available()`
alone would swap an hour of slow-but-working CPU scoring for an import error an
hour in. So the probe reports every dependency, the refusal names the missing
one, and nothing is ever installed into an environment the app did not build.

No real subprocess runs here: `scoring_python._run_probe` is the single seam.
"""
import json
from unittest.mock import patch

import pytest


def _facts(cuda=True, missing=(), device='NVIDIA GeForce RTX 4090'):
    """Raw probe output for an interpreter, minus `missing` modules."""
    from app.services import scoring_python as sp
    mods = {d['module']: d['module'] not in missing for d in sp.SCORING_DEPS}
    return {'python': '3.11.9', 'modules': mods, 'cuda': cuda,
            'device_name': device if cuda else None, 'torch_version': '2.5.1+cu124'}


@pytest.fixture()
def sp(app):
    """The service with a clean probe cache (it is process-global)."""
    from app.services import scoring_python
    scoring_python.clear_cache()
    yield scoring_python
    scoring_python.clear_cache()


# ── The case this whole feature is about ─────────────────────────────────────

def test_cuda_torch_without_open_clip_is_refused_and_names_the_dependency(sp, app, tmp_path):
    """The most likely real machine: a daily-driver training venv with CUDA
    torch, no OpenCLIP. It must be refused, and the message must say WHICH
    package — 'no' with no noun is what makes a user give up."""
    fake = tmp_path / 'aitoolkit-python'
    fake.write_text('')
    with app.app_context(), \
         patch.object(sp, '_run_probe', lambda p: _facts(cuda=True, missing=('open_clip',))):
        verdict = sp.describe(str(fake), sp.probe(str(fake)))
        assert verdict['status'] == 'incomplete'
        assert verdict['usable'] is False
        assert verdict['cuda'] is True, 'CUDA is real here — the refusal is about the deps'
        assert verdict['missing'] == ['open_clip_torch']
        assert 'OpenCLIP' in verdict['detail'] and 'CUDA' in verdict['detail']
        # The exact command to fix it, pip name (open_clip_torch) not module name.
        assert 'pip install open_clip_torch' in verdict['install_command']
        assert str(fake) in verdict['install_command']

        # …and selecting it changes nothing: we stay on the working CPU setup.
        from app import config as cfg
        with pytest.raises(sp.SelectionError) as err:
            sp.select(str(fake))
        assert 'OpenCLIP' in str(err.value)
        assert err.value.verdict['missing'] == ['open_clip_torch']
        assert (cfg.get('bank_scoring.python') or '') == ''


def test_a_complete_cuda_interpreter_is_accepted_and_lights_the_gpu_capability(sp, app, tmp_path):
    from app import capabilities, config as cfg
    good = tmp_path / 'good-python'
    good.write_text('')
    with app.app_context(), patch.object(sp, '_run_probe', lambda p: _facts(cuda=True)):
        verdict = sp.describe(str(good), sp.probe(str(good)))
        assert verdict['status'] == 'gpu_ready'
        assert verdict['usable'] and verdict['gpu']
        assert verdict['missing'] == []
        assert 'RTX 4090' in verdict['detail']

        result = sp.select(str(good))
        assert result['selected'] == str(good)
        assert cfg.get('bank_scoring.python') == str(good)

        # The pass reads bank_scoring_gpu_available(), so the selection has to
        # reach THAT probe — including dropping its 10-minute cache.
        with patch.object(capabilities, '_import_ok', lambda py, expr, timeout=60: py == str(good)):
            assert capabilities.bank_scoring_gpu_available() is True


def test_a_complete_but_cpu_only_interpreter_is_accepted_and_says_so(sp, app, tmp_path):
    """Selectable — the user may have a reason — but never sold as a speed-up."""
    cpu = tmp_path / 'cpu-python'
    cpu.write_text('')
    with app.app_context(), patch.object(sp, '_run_probe', lambda p: _facts(cuda=False)):
        verdict = sp.describe(str(cpu), sp.probe(str(cpu)))
        assert verdict['status'] == 'cpu_only'
        assert verdict['usable'] is True and verdict['gpu'] is False
        assert 'CPU' in verdict['detail']
        assert sp.select(str(cpu))['selected'] == str(cpu)


# ── Failing safe ─────────────────────────────────────────────────────────────

def test_a_path_that_is_not_an_interpreter_degrades_instead_of_exploding(sp, app):
    from app import config as cfg
    with app.app_context():
        # _run_probe returns None for anything that doesn't answer (missing file,
        # broken venv, cold-import timeout) — never a raise.
        verdict = sp.describe('Z:/nope/python.exe', sp.probe('Z:/nope/python.exe'))
        assert verdict['status'] == 'unreachable'
        assert verdict['usable'] is False
        assert verdict['missing'] == [d['pip'] for d in sp.SCORING_DEPS]
        with pytest.raises(sp.SelectionError):
            sp.select('Z:/nope/python.exe')
        assert (cfg.get('bank_scoring.python') or '') == ''


def test_detection_lists_a_broken_candidate_as_a_row_not_an_error(sp, app, client, tmp_path):
    """A candidate that explodes mid-probe must not take the page down."""
    from app import config as cfg
    good = tmp_path / 'good-python'
    good.write_text('')
    with app.app_context():
        cfg.save_config({'bank_scoring': {'python': str(good)}})

    def boom(path):
        raise OSError('the venv is on an unplugged drive')

    with patch.object(sp, '_run_probe', boom):
        res = client.get('/api/scoring-python')
    assert res.status_code == 200
    rows = res.get_json()['interpreters']
    assert rows, 'the configured interpreter is still listed'
    assert all(r['status'] == 'unreachable' for r in rows)


def test_a_forced_rescan_also_drops_the_capability_caches(sp, app, client, tmp_path):
    """A user who just pip-installed a package clicks ↻. If only our own cache is
    dropped, the capability probes keep saying 'not installed' for ten more
    minutes and the fix looks broken."""
    from app import capabilities
    dropped = {'n': 0}
    with patch.object(capabilities, 'clear_import_cache',
                      lambda: dropped.__setitem__('n', dropped['n'] + 1)), \
         patch.object(sp, '_run_probe', lambda p: _facts(cuda=True)):
        client.get('/api/scoring-python')
        assert dropped['n'] == 0, 'a plain read must not invalidate anything'
        client.get('/api/scoring-python?force=1')
        assert dropped['n'] == 1


def test_reverting_to_the_app_default_clears_the_override(sp, app, tmp_path):
    from app import config as cfg
    good = tmp_path / 'good-python'
    good.write_text('')
    with app.app_context(), patch.object(sp, '_run_probe', lambda p: _facts(cuda=True)):
        sp.select(str(good))
        assert cfg.get('bank_scoring.python') == str(good)
        assert sp.select('')['reverted'] is True
        assert (cfg.get('bank_scoring.python') or '') == ''


# ── Candidates & caching ─────────────────────────────────────────────────────

def test_candidates_are_known_interpreters_only_deduplicated_and_existing(sp, app, tmp_path):
    """Known Pythons, not a disk sweep — and never the same one twice."""
    from app import config as cfg
    shared = tmp_path / 'shared-python'
    shared.write_text('')
    with app.app_context():
        cfg.save_config({'bank_scoring': {'python': str(shared)},
                         'aitoolkit': {'dir': str(tmp_path), 'python': str(shared)}})
        rows = sp.candidates()
        paths = [c['path'] for c in rows]
        assert paths.count(str(shared)) == 1, 'one interpreter, one row'
        # The selected interpreter IS the ai-toolkit one here: it must keep the
        # label that says so. "Currently used" is carried by `selected`, and
        # letting it win would hide where the interpreter actually comes from.
        row = next(c for c in rows if c['path'] == str(shared))
        assert row['source'] == 'aitoolkit' and 'ai-toolkit' in row['label']
        sources = {c['source'] for c in rows}
        assert 'app' in sources, "the app's own Python is the way back"
        assert str(tmp_path / 'ghost.exe') not in paths


def test_a_configured_interpreter_the_app_does_not_recognise_is_still_listed(sp, app, tmp_path):
    from app import config as cfg
    stranger = tmp_path / 'conda' / 'python.exe'
    stranger.parent.mkdir()
    stranger.write_text('')
    with app.app_context():
        cfg.save_config({'bank_scoring': {'python': str(stranger)}})
        rows = sp.candidates()
        row = next(c for c in rows if c['path'] == str(stranger))
        assert row['source'] == 'configured'


def test_a_typed_path_is_probed_even_when_it_is_not_a_known_candidate(sp, app, tmp_path):
    typed = tmp_path / 'conda' / 'python.exe'
    typed.parent.mkdir()
    typed.write_text('')
    with app.app_context(), patch.object(sp, '_run_probe', lambda p: _facts(cuda=True)):
        rows = sp.detect(extra_path=str(typed))['interpreters']
        manual = [r for r in rows if r['source'] == 'manual']
        assert len(manual) == 1 and manual[0]['status'] == 'gpu_ready'


def test_a_rescan_sees_a_dependency_installed_since_the_last_probe(sp, app, tmp_path):
    """Without this the user installs open_clip and the app keeps saying it is
    missing for ten minutes — the exact way a good feature loses trust."""
    py = tmp_path / 'python'
    py.write_text('')
    calls = {'n': 0}

    def evolving(path):
        calls['n'] += 1
        return _facts(cuda=True, missing=('open_clip',) if calls['n'] == 1 else ())

    with app.app_context(), patch.object(sp, '_run_probe', evolving):
        assert sp.describe(str(py), sp.probe(str(py)))['status'] == 'incomplete'
        assert sp.probe(str(py))['modules']['open_clip'] is False   # cached, no new call
        assert calls['n'] == 1
        sp.clear_cache()
        assert sp.describe(str(py), sp.probe(str(py)))['status'] == 'gpu_ready'


def test_an_unreachable_probe_is_never_cached_as_a_fact(sp, app, tmp_path):
    """A cold-import timeout must not freeze a working venv into 'unreachable'."""
    py = tmp_path / 'python'
    py.write_text('')
    calls = {'n': 0}

    def flaky(path):
        calls['n'] += 1
        return None if calls['n'] == 1 else _facts(cuda=True)

    with app.app_context(), patch.object(sp, '_run_probe', flaky):
        assert sp.probe(str(py)) is None
        assert sp.describe(str(py), sp.probe(str(py)))['status'] == 'gpu_ready'


# ── The probe program itself ─────────────────────────────────────────────────

def test_the_probe_program_reports_every_scoring_dependency(sp):
    """Guards the pairing: the code that runs in the child must ask about the
    same module list the verdict renders."""
    for dep in sp.SCORING_DEPS:
        assert f"'{dep['module']}'" in sp._PROBE_CODE or f'"{dep["module"]}"' in sp._PROBE_CODE
    # open_clip is the one that matters and the one a CUDA-only check misses.
    assert 'open_clip' in sp._PROBE_CODE
    assert 'cuda.is_available' in sp._PROBE_CODE


def test_the_probe_program_runs_in_a_real_interpreter(sp):
    """Executed for real, once, against THIS interpreter — a syntax error in the
    generated program would otherwise read as 'every Python on your machine is
    unreachable'. Asserts the SHAPE, never which packages happen to be here."""
    import subprocess
    import sys
    proc = subprocess.run([sys.executable, '-c', sp._PROBE_CODE],
                          capture_output=True, text=True, timeout=sp.PROBE_TIMEOUT)
    assert proc.returncode == 0, proc.stderr
    info = json.loads(proc.stdout.strip().splitlines()[-1])
    assert set(info['modules']) == {d['module'] for d in sp.SCORING_DEPS}
    assert isinstance(info['cuda'], bool)


# ── Route contract ───────────────────────────────────────────────────────────

def test_the_endpoint_refuses_an_incomplete_interpreter_with_the_reason(sp, app, client, tmp_path):
    py = tmp_path / 'python'
    py.write_text('')
    with patch.object(sp, '_run_probe', lambda p: _facts(cuda=True, missing=('open_clip', 'timm'))):
        res = client.post('/api/scoring-python', json={'python': str(py)})
    assert res.status_code == 400
    body = res.get_json()
    assert 'OpenCLIP' in body['error'] and 'timm' in body['error']
    assert body['verdict']['missing'] == ['open_clip_torch', 'timm']
    with app.app_context():
        from app import config as cfg
        assert (cfg.get('bank_scoring.python') or '') == ''
