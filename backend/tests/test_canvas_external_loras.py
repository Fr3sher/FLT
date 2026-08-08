"""🔌 Canvas external LoRA plugin nodes — engine + route contract.

An external LoRA is ANY models/loras file stacked on top of a run's cells via
`external_loras=[{filename, strength}]`. Fail-closed: a filename that does not
resolve under a loras root is a hard error (never a silent skip — the 2026-07
privacy-guard lesson), and the arch preflight covers externals so a wrong-family
file 409s before any row exists."""
import json

import pytest

_ST = (b'\x08\x00\x00\x00\x00\x00\x00\x00{"__metadata__":{}}'
       .ljust(32, b'\x00'))


def _ext_tree(tmp_path, monkeypatch, trigger, externals=()):
    """A configured ComfyUI tree with one trained z-image checkpoint (matching
    `trigger`) plus `externals` (bare file names) dropped at the loras ROOT,
    outside the 'z image' family subfolder — exactly where a Canvas plugin node
    points at an arbitrary models/loras file. Returns (dataset, trained_rel)."""
    from app import config
    from app.services import face_dataset_service as svc
    from app.config import LOCAL_USER
    base = tmp_path / 'Comfy'
    lora_dir = base / 'models' / 'loras' / 'z image'
    lora_dir.mkdir(parents=True, exist_ok=True)
    trained = f'lora_{trigger}_000002000.safetensors'
    (lora_dir / trained).write_bytes(_ST)
    loras_root = base / 'models' / 'loras'
    for name in externals:
        (loras_root / name).write_bytes(_ST)
    unet_dir = base / 'models' / 'unet' / 'z image'
    unet_dir.mkdir(parents=True, exist_ok=True)
    (unet_dir / 'zmodel.safetensors').write_bytes(_ST)
    config.save_config({'comfyui': {'base_dir': str(base)}})
    import app.utils.comfyui as comfyui_utils
    monkeypatch.setattr(comfyui_utils, '_zimage_models_cache',
                        {'data': None, 'timestamp': 0})
    ds = svc.create_dataset(LOCAL_USER, trigger.capitalize(), trigger)
    return ds, 'z image' + chr(92) + trained


def _ext_krea_tree(tmp_path, monkeypatch, trigger, externals=()):
    """Same as `_ext_tree` but for the krea family: the trained checkpoint lives
    under the 'krea' loras subfolder (krea's family-pool scan root), `externals`
    still sit at the loras ROOT — outside ANY family subfolder, exactly what a
    Canvas plugin node points at."""
    from app import config
    from app.services import face_dataset_service as svc
    from app.config import LOCAL_USER
    base = tmp_path / 'Comfy'
    lora_dir = base / 'models' / 'loras' / 'krea'
    lora_dir.mkdir(parents=True, exist_ok=True)
    trained = f'lora_{trigger}_000002000.safetensors'
    (lora_dir / trained).write_bytes(_ST)
    loras_root = base / 'models' / 'loras'
    for name in externals:
        (loras_root / name).write_bytes(_ST)
    config.save_config({'comfyui': {'base_dir': str(base)}})
    ds = svc.create_dataset(LOCAL_USER, trigger.capitalize(), trigger)
    return ds, 'krea' + chr(92) + trained


def _wire(monkeypatch, lts, seen=None):
    """Common plumbing every test below needs: no GPU busy/active-run gate, and
    a `_build_cell_workflow` stub that records the `extra_loras` it was handed
    (the same channel externals ride) instead of talking to ComfyUI."""
    monkeypatch.setattr(lts, 'gpu_busy_reason', lambda: None)
    monkeypatch.setattr(lts, '_active_run_count', lambda *a: 0)

    def fake_build(*a, **k):
        if seen is not None:
            seen['extra_loras'] = k.get('extra_loras')
        return {'1': {}}
    monkeypatch.setattr(lts, '_build_cell_workflow', fake_build)


def test_external_lora_reaches_every_cell(app, tmp_path, monkeypatch):
    """A validated external rides the extra_loras channel: persisted on the
    row JSON AND handed to the workflow builder."""
    from app.config import LOCAL_USER
    from app.services import lora_test_studio as lts
    with app.app_context():
        ds, trained = _ext_tree(tmp_path, monkeypatch, 'ext1',
                                externals=['detail-tweaker.safetensors'])
        seen = {}
        _wire(monkeypatch, lts, seen)

        def fake_persist(img, user_id, dataset_id, prompt, build_workflow):
            build_workflow()
            seen['img'] = img
            return 'job-1'
        monkeypatch.setattr(lts, '_persist_and_enqueue_cell', fake_persist)

        lts.create_comparison_run(
            LOCAL_USER, [{'dataset_id': ds.id, 'checkpoint': trained}], [1.0],
            prompt='p', external_loras=[{'filename': 'detail-tweaker.safetensors',
                                         'strength': 0.7}])
        row_extras = json.loads(seen['img'].extra_loras)
        assert {'filename': 'detail-tweaker.safetensors', 'strength': 0.7,
                'external': True} in row_extras
        # …and the exact same entry was handed to the workflow builder, not just
        # persisted — the two must never diverge (that IS the bug this shape guards).
        assert {'filename': 'detail-tweaker.safetensors', 'strength': 0.7,
                'external': True} in seen['extra_loras']


def test_external_lora_missing_file_is_a_hard_error(app, tmp_path, monkeypatch):
    from app.config import LOCAL_USER
    from app.models import LoraTestImage
    from app.services import lora_test_studio as lts
    with app.app_context():
        ds, trained = _ext_tree(tmp_path, monkeypatch, 'ext2')
        _wire(monkeypatch, lts)
        with pytest.raises(ValueError, match='external LoRA not found'):
            lts.create_comparison_run(
                LOCAL_USER, [{'dataset_id': ds.id, 'checkpoint': trained}], [1.0],
                prompt='p', external_loras=[{'filename': 'ghost.safetensors',
                                             'strength': 1.0}])
        assert LoraTestImage.query.count() == 0


def test_external_lora_wrong_arch_409s_before_any_row(app, tmp_path, monkeypatch):
    """detect_lora_arch monkeypatched to return 'sdxl' for the external in a
    zimage run → StudioArchMismatch, and zero LoraTestImage rows created."""
    from app.config import LOCAL_USER
    from app.models import LoraTestImage
    from app.services import lora_test_studio as lts
    with app.app_context():
        ds, trained = _ext_tree(tmp_path, monkeypatch, 'ext3',
                                externals=['wrong-arch.safetensors'])
        _wire(monkeypatch, lts)
        real_detect = lts.lt.detect_lora_arch

        def fake_detect(path):
            if 'wrong-arch' in str(path):
                return 'sdxl'
            return real_detect(path)
        monkeypatch.setattr(lts.lt, 'detect_lora_arch', fake_detect)

        with pytest.raises(lts.StudioArchMismatch):
            lts.create_comparison_run(
                LOCAL_USER, [{'dataset_id': ds.id, 'checkpoint': trained}], [1.0],
                prompt='p', external_loras=[{'filename': 'wrong-arch.safetensors',
                                             'strength': 1.0}])
        assert LoraTestImage.query.count() == 0


def test_external_strength_clamped_and_defaulted(app, tmp_path, monkeypatch):
    """strength 9 → 2.0; strength 'x' → 1.0; entries deduped by filename."""
    from app.config import LOCAL_USER
    from app.services import lora_test_studio as lts
    with app.app_context():
        ds, trained = _ext_tree(tmp_path, monkeypatch, 'ext4',
                                externals=['a.safetensors', 'b.safetensors'])
        seen = {}
        _wire(monkeypatch, lts, seen)

        def fake_persist(img, user_id, dataset_id, prompt, build_workflow):
            build_workflow()
            seen['img'] = img
            return 'job-1'
        monkeypatch.setattr(lts, '_persist_and_enqueue_cell', fake_persist)

        lts.create_comparison_run(
            LOCAL_USER, [{'dataset_id': ds.id, 'checkpoint': trained}], [1.0],
            prompt='p', external_loras=[
                {'filename': 'a.safetensors', 'strength': 9},
                {'filename': 'a.safetensors', 'strength': 0.3},  # dup, ignored
                {'filename': 'b.safetensors', 'strength': 'x'}])
        row_extras = json.loads(seen['img'].extra_loras)
        assert {'filename': 'a.safetensors', 'strength': 2.0, 'external': True} \
            in row_extras
        assert {'filename': 'b.safetensors', 'strength': 1.0, 'external': True} \
            in row_extras
        assert len([e for e in row_extras if e['filename'] == 'a.safetensors']) == 1


def test_external_lora_reaches_the_real_krea_graph(app, tmp_path, monkeypatch):
    """Fix-round regression: Krea's family-pool allowlist (scan of the 'krea'
    loras subfolder only) must NOT re-filter externals validated upstream.
    Before the fix `apply_krea_lora_test_settings` built `allowed` from
    `allowed_loras` alone when it was given (the studio's real call always
    gives it), so `inject_krea_loras` silently dropped every external whose
    file lives outside krea/ — persisted on the row with `external: True`,
    never mounted in the graph. Only `_enqueue_cell` is replaced here; the
    workflow is the REAL one `_build_cell_workflow` produces (same doctrine
    as test_canvas_blend.py's 'THE proof' test) — no other stub can mask a
    regression in that graph."""
    from app.config import LOCAL_USER
    from app.services import lora_test_studio as lts
    with app.app_context():
        ds, trained = _ext_krea_tree(tmp_path, monkeypatch, 'kext',
                                     externals=['outside-krea.safetensors'])
        monkeypatch.setattr(lts, 'gpu_busy_reason', lambda: None)
        monkeypatch.setattr(lts, '_active_run_count', lambda *a: 0)
        monkeypatch.setattr(lts, '_preflight_run', lambda *a, **k: None)
        monkeypatch.setattr(lts, '_target_node_classes', lambda: None)
        monkeypatch.setattr(lts, 'permanent_lora_candidates', lambda _f: [])
        submitted = []

        def capture(user_id, dataset_id, workflow, prompt, job_id=None, **_kw):
            submitted.append(workflow)
            return job_id
        monkeypatch.setattr(lts, '_enqueue_cell', capture)

        lts.create_comparison_run(
            LOCAL_USER, [{'dataset_id': ds.id, 'checkpoint': trained}], [1.0],
            prompt='p', external_loras=[{'filename': 'outside-krea.safetensors',
                                         'strength': 0.6}])
        assert len(submitted) == 1
        wf = submitted[0]
        loaders = {nid: n for nid, n in wf.items()
                   if n.get('class_type') == 'LoraLoaderModelOnly'}
        assert ('outside-krea.safetensors', 0.6) in {
            (n['inputs']['lora_name'], n['inputs']['strength_model'])
            for n in loaders.values()}


# --- routes forward external_loras ------------------------------------------

def _comfy(monkeypatch):
    monkeypatch.setattr('app.capabilities.probe',
                        lambda *a, **k: {'comfyui': {'reachable': True}})


def test_canvas_route_forwards_external_loras(client, monkeypatch):
    """POST /api/train/canvas/generate with external_loras forwards the
    parameter untouched to the engine."""
    _comfy(monkeypatch)
    seen = {}

    def fake(user_id, selections, **kwargs):
        seen['external_loras'] = kwargs.get('external_loras')
        return {'created': 1, 'seed': 7, 'count': 1, 'run_id': 'r1', 'ids': []}

    monkeypatch.setattr('app.services.cloud_training.canvas_generate', fake)
    r = client.post('/api/train/canvas/generate', json={
        'selections': [{'dataset_id': 1, 'checkpoint': 'z image\\a.safetensors'}],
        'external_loras': [{'filename': 'detail.safetensors', 'strength': 0.6}]})
    assert r.status_code == 200
    assert seen['external_loras'] == [{'filename': 'detail.safetensors', 'strength': 0.6}]


def test_studio_route_forwards_external_loras(client, monkeypatch):
    """POST /api/studio/run with external_loras forwards the parameter
    untouched to the engine."""
    _comfy(monkeypatch)
    seen = {}

    def fake(user_id, selections, strengths, **kwargs):
        seen['external_loras'] = kwargs.get('external_loras')
        return {'created': 1, 'seed': 7, 'count': 1, 'run_id': 'r1', 'ids': []}

    monkeypatch.setattr('app.services.lora_test_studio.create_comparison_run', fake)
    r = client.post('/api/studio/run', json={
        'selections': [{'dataset_id': 1, 'checkpoint': 'z image\\a.safetensors'}],
        'strengths': [1.0],
        'external_loras': [{'filename': 'detail.safetensors', 'strength': 0.6}]})
    assert r.status_code == 200
    assert seen['external_loras'] == [{'filename': 'detail.safetensors', 'strength': 0.6}]
