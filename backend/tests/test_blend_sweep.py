"""Blend SWEEP: multiple weights per LoRA produce a batch of combinations in one run.
Previously comparing 0.8/0.6 with 0.6/0.8 required separate runs; selections now
carry weights lists and render the Cartesian product. Verify additive
compatibility for legacy weight-only selections, N*M combinations within one
run_id, each REAL submitted graph carrying its own weights, and stack variants
retaining distinct combinations rather than collapsing the run under its first
weights. Plausible images alone cannot prove that distinct weights were used."""

_ST = (b'\x08\x00\x00\x00\x00\x00\x00\x00{"__metadata__":{}}'.ljust(32, b'\x00'))


def _tree(tmp_path, monkeypatch, loras):
    from app import config
    base = tmp_path / 'Comfy'
    lora_dir = base / 'models' / 'loras' / 'z image'
    lora_dir.mkdir(parents=True, exist_ok=True)
    for name in loras:
        (lora_dir / name).write_bytes(_ST)
    unet = base / 'models' / 'unet' / 'z image'
    unet.mkdir(parents=True, exist_ok=True)
    (unet / 'zmodel.safetensors').write_bytes(_ST)
    config.save_config({'comfyui': {'base_dir': str(base)}})
    import app.utils.comfyui as comfyui_utils
    monkeypatch.setattr(comfyui_utils, '_zimage_models_cache', {'data': None, 'timestamp': 0})


def _two_lora_stack(app_ctx_tmp, monkeypatch, capture_workflows=False):
    """(launch, cp_a, cp_b, submitted): a two-LoRA stack ready to launch."""
    from app.services import lora_test_studio as lts, face_dataset_service as svc
    from app.config import LOCAL_USER
    tmp_path = app_ctx_tmp
    name_a, name_b = 'lora_aaa_000002000.safetensors', 'lora_bbb_000001000.safetensors'
    _tree(tmp_path, monkeypatch, [name_a, name_b])
    cp_a = 'z image' + chr(92) + name_a
    cp_b = 'z image' + chr(92) + name_b
    ds_a = svc.create_dataset(LOCAL_USER, 'Alpha', 'aaa')
    ds_b = svc.create_dataset(LOCAL_USER, 'Beta', 'bbb')
    by_ds = {ds_a.id: [{'filename': cp_a}], ds_b.id: [{'filename': cp_b}]}
    monkeypatch.setattr(lts, 'list_test_checkpoints', lambda ds, _f=None: by_ds[ds.id])
    monkeypatch.setattr(lts, 'gpu_busy_reason', lambda: None)
    monkeypatch.setattr(lts, '_active_run_count', lambda *a: 0)
    monkeypatch.setattr(lts, '_preflight_checkpoint_arch', lambda *a, **k: None)
    monkeypatch.setattr(lts, '_preflight_run', lambda *a, **k: None)
    monkeypatch.setattr(lts, '_target_node_classes', lambda: None)
    monkeypatch.setattr(lts, 'permanent_lora_candidates', lambda _f: [])
    submitted = []
    if capture_workflows:
        # Keep _build_cell_workflow real: inspect the submitted graph.
        monkeypatch.setattr(lts, '_enqueue_cell',
                            lambda u, d, wf, p, job_id=None, **k: (submitted.append(wf), job_id)[1])
    else:
        monkeypatch.setattr(lts, '_build_cell_workflow', lambda *a, **k: {'1': {}})
        monkeypatch.setattr(lts, '_enqueue_cell', lambda *a, job_id=None, **k: job_id)

    def launch(sel_a, sel_b, **kw):
        return lts.create_comparison_run(
            LOCAL_USER,
            [{'dataset_id': ds_a.id, 'checkpoint': cp_a, **sel_a},
             {'dataset_id': ds_b.id, 'checkpoint': cp_b, **sel_b}],
            kw.pop('strengths', [1.0]),
            lts.StudioGenSettings(prompt='on a rooftop',
                                  count=kw.pop('count', 1), **kw),
            combine=True)

    return launch, cp_a, cp_b, submitted, ds_a, ds_b


# Additive compatibility.

def test_a_single_weight_per_lora_is_the_run_it_always_was(app, monkeypatch, tmp_path):
    """Legacy weight-only selections still produce one combination and one cell."""
    from app.models import LoraTestImage
    with app.app_context():
        launch, cp_a, cp_b, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weight': 0.9}, {'weight': 0.55}, strengths=[0.6, 0.8, 1.0])
        assert out['created'] == 1
        row = LoraTestImage.query.filter_by(run_id=out['run_id']).one()
        assert row.strength == 0.9
        combined = [m for m in __import__('json').loads(row.extra_loras) if m.get('combined')]
        assert [(m['filename'], m['strength']) for m in combined] == [(cp_b, 0.55)]


def test_an_empty_or_unreadable_weights_list_falls_back_to_the_scalar(app):
    from app.services.lora_test_studio import _combine_weights
    assert _combine_weights({'weight': 0.7}) == [0.7]
    assert _combine_weights({'weight': 0.7, 'weights': []}) == [0.7]
    assert _combine_weights({'weight': 0.7, 'weights': 'nope'}) == [0.7]
    assert _combine_weights({'weight': 0.7, 'weights': ['x', None]}) == [0.7]
    assert _combine_weights({}) == [1.0]
    # Clamp to 0..MAX_LORA_STRENGTH (5.0 since 2026-08-08, formerly 2.0), round to
    # hundredths, and deduplicate in received order.
    assert _combine_weights({'weights': [9, -3, 0.5555, 0.4, 0.4]}) == [5.0, 0.0, 0.56, 0.4]
    # The newly supported range passes through unchanged.
    assert _combine_weights({'weights': [3.4, 5.0]}) == [3.4, 5.0]


# --- le produit ---------------------------------------------------------------

def test_two_weights_each_launch_four_labelled_combinations_in_one_run(
        app, monkeypatch, tmp_path):
    """2 x 2 = 4 configurations in one run, with EACH cell carrying ITS pair."""
    import json
    from app.models import LoraTestImage
    with app.app_context():
        launch, cp_a, cp_b, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weights': [0.6, 0.8]}, {'weights': [0.4, 1.0]})
        assert out['created'] == 4
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        got = set()
        for r in rows:
            member = [m for m in json.loads(r.extra_loras) if m.get('combined')][0]
            assert member['filename'] == cp_b
            got.add((r.strength, member['strength']))
        assert got == {(0.6, 0.4), (0.6, 1.0), (0.8, 0.4), (0.8, 1.0)}


def test_sweeping_one_lora_pins_the_other_to_its_single_weight(app, monkeypatch, tmp_path):
    import json
    from app.models import LoraTestImage
    with app.app_context():
        launch, _, cp_b, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weights': [0.4, 0.6, 0.8]}, {'weight': 0.9})
        assert out['created'] == 3
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        assert sorted(r.strength for r in rows) == [0.4, 0.6, 0.8]
        for r in rows:
            member = [m for m in json.loads(r.extra_loras) if m.get('combined')][0]
            assert member['strength'] == 0.9


def test_a_sweep_multiplies_with_the_seed_count(app, monkeypatch, tmp_path):
    """The server honors the panel count: configurations times count."""
    with app.app_context():
        launch, _, _, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weights': [0.6, 0.8]}, {'weights': [0.4, 1.0]}, count=2)
        assert out['created'] == 8


# Verify the actual submitted workflow, cell by cell.

def test_every_submitted_workflow_carries_ITS_OWN_pair_of_weights(
        app, monkeypatch, tmp_path):
    """Four combinations submit four graphs, each with TWO chained
    LoraLoaderModelOnly nodes carrying that combination's exact weights. A second
    LoRA incorrectly retaining the first combination's weight would still yield
    plausible images. Inspect the graph, not mock arguments."""
    with app.app_context():
        launch, cp_a, cp_b, submitted, _, _ = _two_lora_stack(
            tmp_path, monkeypatch, capture_workflows=True)
        out = launch({'weights': [0.6, 0.8]}, {'weights': [0.4, 1.0]})
        assert out['created'] == 4 and len(submitted) == 4

        pairs = set()
        for wf in submitted:
            loaders = {nid: n for nid, n in wf.items()
                       if n.get('class_type') == 'LoraLoaderModelOnly'}
            assert len(loaders) == 2, 'a blended cell loads exactly its two LoRAs'
            by_name = {n['inputs']['lora_name']: n for n in loaders.values()}
            assert set(by_name) == {cp_a, cp_b}
            # Chained, not parallel: one loader feeds the other.
            fed = [n for n in loaders.values() if n['inputs']['model'][0] in loaders]
            assert len(fed) == 1
            pairs.add((by_name[cp_a]['inputs']['strength_model'],
                       by_name[cp_b]['inputs']['strength_model']))
            # Triggers remain injected into EVERY sweep cell.
            texts = [n['inputs'].get('text') for n in wf.values()
                     if isinstance(n.get('inputs', {}).get('text'), str)]
            assert any(t.startswith('aaa, bbb, on a rooftop') for t in texts)

        assert pairs == {(0.6, 0.4), (0.6, 1.0), (0.8, 0.4), (0.8, 1.0)}


# --- la vue pile ---------------------------------------------------------------

def test_the_stack_view_shows_one_variant_per_combination_not_one_per_run(
        app, monkeypatch, tmp_path):
    """stack_variants formerly grouped by run because each run had one combination.
    Sweeps carry N combinations: grouping by run alone would collapse them under
    the first cell's weights."""
    from app.services import lora_test_studio as lts
    from app.models import LoraTestImage
    with app.app_context():
        launch, cp_a, cp_b, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weights': [0.6, 0.8]}, {'weights': [0.4, 1.0]})
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).order_by(
            LoraTestImage.id).all()
        variants = lts.stack_variants(out['run_id'], rows)
        assert len(variants) == 4, 'four combinations, four columns'
        assert all(v['active'] for v in variants), 'they are all the run being viewed'
        vectors = {tuple(w['weight'] for w in v['weights']) for v in variants}
        assert vectors == {(0.6, 0.4), (0.6, 1.0), (0.8, 0.4), (0.8, 1.0)}
        # Each variant names both LoRAs in stack order.
        for v in variants:
            assert [w['filename'] for w in v['weights']] == [cp_a, cp_b]


def test_a_single_combination_run_still_reads_as_exactly_one_variant(
        app, monkeypatch, tmp_path):
    """Grouping by weight vector must not split previously unified variants."""
    from app.services import lora_test_studio as lts
    from app.models import LoraTestImage
    with app.app_context():
        launch, _, _, _, _, _ = _two_lora_stack(tmp_path, monkeypatch)
        out = launch({'weight': 0.9}, {'weight': 0.55}, count=3)
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        assert len(rows) == 3            # Three seeds, ONE combination.
        variants = lts.stack_variants(out['run_id'], rows)
        assert len(variants) == 1
        assert len(variants[0]['cells']) == 3
