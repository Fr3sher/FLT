"""The 🚩 watermark detector, on a GPU Python the machine already has.

The Setup install pins the app-managed environment into
``watermark_detect.python`` — an environment built with CPU torch on purpose —
so on a machine WITH a card the scan ran on the CPU forever and nothing said
so. The fix is the picker Score and the SigLIP 2 index already have, driven by
a third :class:`InterpreterProfile`.

Load-bearing contracts, asserted below:

* the watermark list really differs from Score's (no open_clip/timm — the most
  common borrowed venv, ComfyUI's, must not be refused for packages the
  detector never imports);
* BOTH cascade halves are demanded as symbols — a transformers that imports
  but lacks ``AutoModelForZeroShotObjectDetection`` dies at locator load;
* selecting writes ONLY ``watermark_detect.python``; reverting clears only it;
* with nothing selected the pass runs where ``detector_python()`` lands
  (Score's interpreter, then the app's own) and ``default_python`` says so.

No real subprocess runs here: `scoring_python._run_probe` is the single seam.
"""
from unittest.mock import patch

import pytest


def _facts(cuda=True, missing=(), siglip_cls=True, dino_cls=True):
    from app.services import scoring_python as sp
    mods = {m: m not in missing for m in sp._DEP_MODULES}
    return {'python': '3.12.9', 'modules': mods,
            'symbols': {
                'transformers:Siglip2Model': True,
                'transformers:SiglipForImageClassification': bool(siglip_cls),
                'transformers:AutoModelForZeroShotObjectDetection': bool(dino_cls),
            },
            'cuda': cuda,
            'device_name': 'NVIDIA GeForce RTX 4090' if cuda else None,
            'torch_version': '2.9.1+cu128'}


@pytest.fixture()
def sp(app):
    from app.services import scoring_python
    scoring_python.clear_cache()
    yield scoring_python
    scoring_python.clear_cache()


def test_an_interpreter_score_refuses_can_still_run_the_detector(sp, app, tmp_path):
    """A ComfyUI venv: CUDA torch, transformers, Pillow — no open_clip, no
    timm, no numpy even. Score refuses it; the detector never imports any of
    the three and must not."""
    py = tmp_path / 'python'
    py.write_text('')
    facts = _facts(cuda=True, missing=('open_clip', 'timm', 'numpy'))
    assert sp.describe(str(py), facts, 'scoring')['status'] == 'incomplete'
    verdict = sp.describe(str(py), facts, 'watermark_detect')
    assert verdict['status'] == 'gpu_ready'
    assert verdict['usable'] is True and verdict['gpu'] is True
    assert verdict['profile'] == 'watermark_detect'
    assert [d['module'] for d in verdict['deps']] == ['torch', 'transformers', 'PIL']


@pytest.mark.parametrize('siglip_cls,dino_cls', [(False, True), (True, False)])
def test_a_transformers_missing_either_cascade_half_is_refused(
        sp, app, tmp_path, siglip_cls, dino_cls):
    """Both halves or nothing: the ranker class and the locator class come from
    the same package but different transformers vintages, and a module-name
    probe cannot tell them apart. The repair line carries the version floor."""
    py = tmp_path / 'python'
    py.write_text('')
    verdict = sp.describe(
        str(py), _facts(cuda=True, siglip_cls=siglip_cls, dino_cls=dino_cls),
        'watermark_detect')
    assert verdict['status'] == 'incomplete'
    assert verdict['missing'] == ['transformers']
    assert '"transformers>=4.40"' in verdict['install_command']
    # The semantic profile, which demands a different symbol, is unaffected.
    assert sp.describe(str(py), _facts(cuda=True, siglip_cls=siglip_cls,
                                       dino_cls=dino_cls),
                       'semantic')['status'] == 'gpu_ready'


def test_selecting_writes_only_the_watermark_key(sp, app, tmp_path):
    from app import config as cfg
    py = tmp_path / 'gpu-python'
    py.write_text('')
    score_py = r'D:\score\python.exe'
    with app.app_context():
        cfg.save_config({'bank_scoring': {'python': score_py},
                         'watermark_detect': {'python': ''}})
        with patch.object(sp, '_run_probe', lambda p: _facts(cuda=True)):
            result = sp.select(str(py), profile='watermark_detect')
        assert result['selected'] == str(py)
        assert cfg.get('watermark_detect.python') == str(py)
        assert cfg.get('bank_scoring.python') == score_py
        # The resolver the pass actually calls lands on the choice.
        from app.services import watermark_detector
        assert watermark_detector.detector_python() == str(py)


def test_reverting_clears_only_the_watermark_key(sp, app):
    from app import config as cfg
    with app.app_context():
        cfg.save_config({'bank_scoring': {'python': r'D:\score\python.exe'},
                         'watermark_detect': {'python': r'D:\borrowed\python.exe'}})
        assert sp.select('', profile='watermark_detect')['reverted'] is True
        assert (cfg.get('watermark_detect.python') or '') == ''
        assert cfg.get('bank_scoring.python') == r'D:\score\python.exe'


def test_default_python_mirrors_the_detector_fallback(sp, app):
    """detector_python() falls back to Score's interpreter before the app's
    own; the picker's "currently running in" line must answer the same."""
    import sys
    from app import config as cfg
    with app.app_context():
        cfg.save_config({'bank_scoring': {'python': r'D:\score\python.exe'},
                         'watermark_detect': {'python': ''}})
        assert sp.default_python('watermark_detect') == r'D:\score\python.exe'
        cfg.save_config({'bank_scoring': {'python': ''}})
        assert sp.default_python('watermark_detect') == sys.executable


def test_scores_interpreter_is_offered_as_a_one_click_row(sp, app, tmp_path):
    from app import config as cfg
    score_py = tmp_path / 'score-python'
    score_py.write_text('')
    with app.app_context():
        cfg.save_config({'bank_scoring': {'python': str(score_py)},
                         'watermark_detect': {'python': ''}})
        rows = sp.candidates('watermark_detect')
    entry = next(r for r in rows if r['source'] == 'scoring')
    assert entry['path'] == str(score_py)


def test_the_endpoint_lists_and_selects_under_the_watermark_key(sp, app, client, tmp_path):
    from app import config as cfg
    py = tmp_path / 'python'
    py.write_text('')
    with patch.object(sp, '_run_probe', lambda p: _facts(cuda=True)):
        listing = client.get('/api/watermark-python').get_json()
        assert listing['profile'] == 'watermark_detect'
        res = client.post('/api/watermark-python', json={'python': str(py)})
    assert res.status_code == 200
    assert res.get_json()['profile'] == 'watermark_detect'
    with app.app_context():
        assert cfg.get('watermark_detect.python') == str(py)


def test_the_endpoint_refuses_a_locatorless_transformers_with_the_reason(
        sp, app, client, tmp_path):
    py = tmp_path / 'python'
    py.write_text('')
    with patch.object(sp, '_run_probe', lambda p: _facts(cuda=True, dino_cls=False)):
        res = client.post('/api/watermark-python', json={'python': str(py)})
    assert res.status_code == 400
    body = res.get_json()
    assert body['verdict']['missing'] == ['transformers']
    with app.app_context():
        from app import config as cfg
        assert (cfg.get('watermark_detect.python') or '') == ''
