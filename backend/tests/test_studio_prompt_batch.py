"""📝 Batch of prompts — tick several entries of the prompt history, launch once.

Both generation surfaces (the dataset's Test Studio and the canvas panel
« Generate from the board ») show the same saved-prompt history, and both could
only replay ONE of them per launch. Replaying N by firing N launches is not an
option: `_active_run_count` refuses a second run while one is in flight, and the
GPU is serialised anyway. So the batch is an AXIS inside one run — one pass per
ticked prompt, same checkpoints, same settings, same seed.

What is pinned here:

  · the axis helper: nothing ticked behaves EXACTLY like before (one prompt), a
    ticked list is stripped/deduplicated in order, and an unreasonable list is
    refused with its count rather than silently truncated;
  · N ticked prompts produce N DISTINCT submitted workflows, one per prompt —
    asserted on the graphs captured at the queue's door, not on call arguments,
    and on both engines (`create_run` for the Test Studio, `create_comparison_run`
    via `canvas_generate` for the board);
  · both routes forward `prompts` to their engine — a dropped key would degrade a
    batch into a single generation in silence.
"""
import pytest

_ST = (b'\x08\x00\x00\x00\x00\x00\x00\x00{"__metadata__":{}}'
       .ljust(32, b'\x00'))


def _comfy(monkeypatch, reachable=True):
    monkeypatch.setattr('app.capabilities.probe',
                        lambda *a, **k: {'comfyui': {'reachable': reachable}})


def _zimage_tree(tmp_path, monkeypatch, loras):
    """A configured ComfyUI tree holding `loras` (bare file names) + one UNET."""
    from app import config
    base = tmp_path / 'Comfy'
    lora_dir = base / 'models' / 'loras' / 'z image'
    lora_dir.mkdir(parents=True, exist_ok=True)
    for name in loras:
        (lora_dir / name).write_bytes(_ST)
    unet_dir = base / 'models' / 'unet' / 'z image'
    unet_dir.mkdir(parents=True, exist_ok=True)
    (unet_dir / 'zmodel.safetensors').write_bytes(_ST)
    config.save_config({'comfyui': {'base_dir': str(base)}})
    import app.utils.comfyui as comfyui_utils
    monkeypatch.setattr(comfyui_utils, '_zimage_models_cache',
                        {'data': None, 'timestamp': 0})
    return base


def _neutralise_preflights(monkeypatch, lts):
    monkeypatch.setattr(lts, 'gpu_busy_reason', lambda: None)
    monkeypatch.setattr(lts, '_active_run_count', lambda *a: 0)
    monkeypatch.setattr(lts, '_preflight_checkpoint_arch', lambda *a, **k: None)
    monkeypatch.setattr(lts, '_preflight_run', lambda *a, **k: None)
    monkeypatch.setattr(lts, '_target_node_classes', lambda: None)
    monkeypatch.setattr(lts, 'permanent_lora_candidates', lambda _f: [])


# --- the axis itself ---------------------------------------------------------

def test_prompt_axis_empty_selection_is_the_old_single_prompt():
    """Nothing ticked must not be a new code path: the axis is the field's
    prompt, alone — including the None that means "each dataset's identity
    prompt" on the cross-dataset engine."""
    from app.services.lora_test_studio import _prompt_axis
    assert _prompt_axis(None, 'on a rooftop') == ['on a rooftop']
    assert _prompt_axis([], 'on a rooftop') == ['on a rooftop']
    assert _prompt_axis(['  ', ''], 'on a rooftop') == ['on a rooftop']
    assert _prompt_axis(None, None) == [None]


def test_prompt_axis_strips_dedupes_and_keeps_the_ticking_order():
    from app.services.lora_test_studio import _prompt_axis
    assert _prompt_axis([' b ', 'a', 'b', 42, None, 'a'], 'fallback') == ['b', 'a']


def test_prompt_axis_refuses_an_unreasonable_batch_with_its_count():
    """Truncating would render half of what was ticked and look like a success."""
    from app.services.lora_test_studio import _prompt_axis, _MAX_PROMPTS_PER_RUN
    too_many = [f'prompt {i}' for i in range(_MAX_PROMPTS_PER_RUN + 3)]
    with pytest.raises(ValueError) as excinfo:
        _prompt_axis(too_many, 'fallback')
    assert str(_MAX_PROMPTS_PER_RUN) in str(excinfo.value)
    assert str(len(too_many)) in str(excinfo.value)


# --- THE proof, Test Studio side: N prompts -> N distinct workflows -----------

def test_test_studio_batch_submits_one_workflow_per_ticked_prompt(
        app, monkeypatch, tmp_path):
    """Three ticked prompts on one checkpoint: three cells, three graphs, three
    different encoded texts — and the rows remember which is which."""
    from app.services import lora_test_studio as lts, face_dataset_service as svc
    from app.config import LOCAL_USER
    from app.models import LoraTestImage
    with app.app_context():
        name = 'lora_bat_000002000.safetensors'
        _zimage_tree(tmp_path, monkeypatch, [name])
        ck = 'z image' + chr(92) + name
        ds = svc.create_dataset(LOCAL_USER, 'Batch', 'bat')
        _neutralise_preflights(monkeypatch, lts)
        monkeypatch.setattr(lts, 'list_test_checkpoints',
                            lambda _ds, _family=None: [{'filename': ck}])
        submitted = []

        def capture(user_id, dataset_id, workflow, prompt, job_id=None, **_kw):
            submitted.append(prompt)
            return job_id
        monkeypatch.setattr(lts, '_enqueue_cell', capture)
        monkeypatch.setattr(lts, '_build_cell_workflow',
                            lambda *a, **k: {'1': {'prompt': a[3]}})

        out = lts.create_run(LOCAL_USER, ds.id, [ck], [1.0], prompt='ignored',
                             count=1, prompts=['on a rooftop', 'in the snow', 'at night'])

        assert out['created'] == 3
        assert sorted(submitted) == ['at night', 'in the snow', 'on a rooftop']
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        assert sorted(r.prompt for r in rows) == ['at night', 'in the snow', 'on a rooftop']


def test_test_studio_batch_multiplies_the_existing_axes_not_replaces_them(
        app, monkeypatch, tmp_path):
    """The batch is an axis among the others: 2 prompts x 2 strengths = 4 cells,
    every pairing present exactly once."""
    from app.services import lora_test_studio as lts, face_dataset_service as svc
    from app.config import LOCAL_USER
    from app.models import LoraTestImage
    with app.app_context():
        name = 'lora_mix_000002000.safetensors'
        _zimage_tree(tmp_path, monkeypatch, [name])
        ck = 'z image' + chr(92) + name
        ds = svc.create_dataset(LOCAL_USER, 'Mix', 'mix')
        _neutralise_preflights(monkeypatch, lts)
        monkeypatch.setattr(lts, 'list_test_checkpoints',
                            lambda _ds, _family=None: [{'filename': ck}])
        monkeypatch.setattr(lts, '_enqueue_cell',
                            lambda *a, job_id=None, **k: job_id)
        monkeypatch.setattr(lts, '_build_cell_workflow', lambda *a, **k: {'1': {}})

        out = lts.create_run(LOCAL_USER, ds.id, [ck], [0.8, 1.0], prompt='x',
                             count=1, prompts=['alpha', 'beta'])

        assert out['created'] == 4
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        assert sorted((r.prompt, r.strength) for r in rows) == [
            ('alpha', 0.8), ('alpha', 1.0), ('beta', 0.8), ('beta', 1.0)]


def test_test_studio_without_a_batch_is_byte_for_byte_the_old_run(
        app, monkeypatch, tmp_path):
    """Zero regression for whoever ticks nothing: one cell, the field's prompt."""
    from app.services import lora_test_studio as lts, face_dataset_service as svc
    from app.config import LOCAL_USER
    from app.models import LoraTestImage
    with app.app_context():
        name = 'lora_solo_000002000.safetensors'
        _zimage_tree(tmp_path, monkeypatch, [name])
        ck = 'z image' + chr(92) + name
        ds = svc.create_dataset(LOCAL_USER, 'Solo', 'solo')
        _neutralise_preflights(monkeypatch, lts)
        monkeypatch.setattr(lts, 'list_test_checkpoints',
                            lambda _ds, _family=None: [{'filename': ck}])
        monkeypatch.setattr(lts, '_enqueue_cell',
                            lambda *a, job_id=None, **k: job_id)
        monkeypatch.setattr(lts, '_build_cell_workflow', lambda *a, **k: {'1': {}})

        out = lts.create_run(LOCAL_USER, ds.id, [ck], [1.0], prompt='only this',
                             count=1)

        assert out['created'] == 1
        row = LoraTestImage.query.filter_by(run_id=out['run_id']).one()
        assert row.prompt == 'only this'


# --- THE proof, canvas side --------------------------------------------------

def test_canvas_batch_submits_one_workflow_per_ticked_prompt(
        app, monkeypatch, tmp_path):
    """Same guarantee on the board's engine, where a run may span datasets: two
    ticked checkpoints x three ticked prompts = six graphs, each prompt appearing
    once per checkpoint."""
    from app.services import cloud_training as ct, lora_test_studio as lts
    from app.services import face_dataset_service as svc
    from app.config import LOCAL_USER
    from app.models import LoraTestImage
    with app.app_context():
        name_a, name_b = 'lora_ca_000002000.safetensors', 'lora_cb_000001000.safetensors'
        _zimage_tree(tmp_path, monkeypatch, [name_a, name_b])
        cp_a = 'z image' + chr(92) + name_a
        cp_b = 'z image' + chr(92) + name_b
        ds_a = svc.create_dataset(LOCAL_USER, 'Ca', 'ca')
        ds_b = svc.create_dataset(LOCAL_USER, 'Cb', 'cb')
        by_ds = {ds_a.id: [{'filename': cp_a}], ds_b.id: [{'filename': cp_b}]}
        _neutralise_preflights(monkeypatch, lts)
        monkeypatch.setattr(lts, 'list_test_checkpoints',
                            lambda ds, _family=None: by_ds[ds.id])
        submitted = []

        def capture(user_id, dataset_id, workflow, prompt, job_id=None, **_kw):
            submitted.append((dataset_id, prompt))
            return job_id
        monkeypatch.setattr(lts, '_enqueue_cell', capture)
        monkeypatch.setattr(lts, '_build_cell_workflow', lambda *a, **k: {'1': {}})

        out = ct.canvas_generate(
            LOCAL_USER,
            [{'dataset_id': ds_a.id, 'checkpoint': cp_a, 'record_id': 11, 'step': 2000},
             {'dataset_id': ds_b.id, 'checkpoint': cp_b, 'record_id': 22, 'step': 1000}],
            strengths=[1.0], count=1,
            prompts=['on a rooftop', 'in the snow', 'at night'])

        assert out['created'] == 6
        assert sorted(submitted) == sorted(
            [(ds.id, p) for ds in (ds_a, ds_b)
             for p in ('on a rooftop', 'in the snow', 'at night')])
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        # One run, one seed: the batch compares prompts, it does not reseed them.
        assert len({r.run_seed for r in rows}) == 1


def test_canvas_batch_without_prompts_still_falls_back_per_dataset(
        app, monkeypatch, tmp_path):
    """No batch AND no common prompt: each cell keeps its own dataset's identity
    prompt — the historical behaviour the axis must not have swallowed."""
    from app.services import cloud_training as ct, lora_test_studio as lts
    from app.services import face_dataset_service as svc
    from app.config import LOCAL_USER
    from app.models import LoraTestImage
    with app.app_context():
        name_a, name_b = 'lora_da_000002000.safetensors', 'lora_db_000001000.safetensors'
        _zimage_tree(tmp_path, monkeypatch, [name_a, name_b])
        cp_a = 'z image' + chr(92) + name_a
        cp_b = 'z image' + chr(92) + name_b
        ds_a = svc.create_dataset(LOCAL_USER, 'Da', 'da')
        ds_b = svc.create_dataset(LOCAL_USER, 'Db', 'db')
        by_ds = {ds_a.id: [{'filename': cp_a}], ds_b.id: [{'filename': cp_b}]}
        _neutralise_preflights(monkeypatch, lts)
        monkeypatch.setattr(lts, 'list_test_checkpoints',
                            lambda ds, _family=None: by_ds[ds.id])
        monkeypatch.setattr(lts, '_enqueue_cell',
                            lambda *a, job_id=None, **k: job_id)
        monkeypatch.setattr(lts, '_build_cell_workflow', lambda *a, **k: {'1': {}})

        out = ct.canvas_generate(
            LOCAL_USER,
            [{'dataset_id': ds_a.id, 'checkpoint': cp_a},
             {'dataset_id': ds_b.id, 'checkpoint': cp_b}],
            strengths=[1.0], count=1)

        assert out['created'] == 2
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
        prompts = {r.dataset_id: r.prompt for r in rows}
        assert 'da' in prompts[ds_a.id] and 'db' in prompts[ds_b.id]


# --- both routes forward the key ---------------------------------------------

def test_canvas_route_forwards_the_prompt_batch(client, monkeypatch):
    _comfy(monkeypatch)
    seen = {}

    def fake(user_id, selections, **kwargs):
        seen.update(kwargs)
        return {'created': 3, 'seed': 7, 'count': 1, 'run_id': 'r1', 'ids': []}

    monkeypatch.setattr('app.services.cloud_training.canvas_generate', fake)
    resp = client.post('/api/train/canvas/generate', json={
        'selections': [{'dataset_id': 1, 'checkpoint': 'a.safetensors'}],
        'prompts': ['one', 'two', 'three']})
    assert resp.status_code == 200
    assert seen['prompts'] == ['one', 'two', 'three']


def test_test_studio_route_forwards_the_prompt_batch(client, monkeypatch):
    _comfy(monkeypatch)
    seen = {}

    def fake(user_id, dataset_id, checkpoints, strengths, **kwargs):
        seen.update(kwargs)
        return {'created': 2, 'seed': 7, 'count': 1, 'run_id': 'r1', 'ids': []}

    monkeypatch.setattr('app.services.lora_test_studio.create_run', fake)
    resp = client.post('/api/dataset/1/lora-test/run', json={
        'checkpoints': ['a.safetensors'], 'strengths': [1.0],
        'prompts': ['one', 'two']})
    assert resp.status_code == 200
    assert seen['prompts'] == ['one', 'two']
