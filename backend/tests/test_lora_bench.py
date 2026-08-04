"""⚖ LoRA bench — pick a downloaded LoRA, read its trigger, sweep its strength.

ComfyUI is never contacted: the enqueue, the preflight and the node probe are
monkeypatched. The LoRA files are REAL (minimal but structurally valid)
safetensors containers written into a real ComfyUI tree, so the pool scanners
and the header reader run for real — the trigger read is the part of this
feature most likely to be wrong on a file nobody anticipated.
"""
import json
import os
import struct

import pytest

LOCAL = 'local'
KREA_CK = 'krea\\civitai_download.safetensors'


def _safetensors(metadata=None, tensors=None):
    """A minimal, structurally valid .safetensors container: 8-byte LE header
    length + JSON header. No weights — every reader in the app reads the header
    only."""
    header = dict(tensors or {})
    if metadata is not None:
        header['__metadata__'] = {str(k): str(v) for k, v in metadata.items()}
    blob = json.dumps(header).encode('utf-8')
    return struct.pack('<Q', len(blob)) + blob


@pytest.fixture()
def comfy(app, tmp_path, monkeypatch):
    """A ComfyUI tree with one downloaded Krea LoRA in models/loras/krea.

    Krea on purpose: its base-model axis falls back to the workflow's wired UNET
    (`[None] + get_krea_models()`), so the run path needs no checkpoint fixture
    and the test stays about the bench.
    """
    from app import config
    base = tmp_path / 'Comfy'
    (base / 'models' / 'loras' / 'krea').mkdir(parents=True)
    with app.app_context():
        config.save_config({'comfyui': {'base_dir': str(base)}})
    return base


def _write_lora(base, rel, metadata=None, tensors=None):
    path = base / 'models' / 'loras' / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_safetensors(metadata, tensors))
    return path


@pytest.fixture()
def quiet_engine(monkeypatch):
    """Neutralise everything that would talk to a GPU or a ComfyUI."""
    from app.services import lora_test_studio as lts
    monkeypatch.setattr(lts, 'gpu_busy_reason', lambda: None)
    monkeypatch.setattr(lts, '_preflight_run', lambda *a, **k: None)
    monkeypatch.setattr(lts, '_target_node_classes', lambda: None)
    monkeypatch.setattr(lts, '_build_cell_workflow', lambda *a, **k: {'1': {}})
    monkeypatch.setattr(lts, '_enqueue_cell',
                        lambda user_id, dataset_id, workflow, prompt, job_id=None,
                        commit=True, **kw: job_id)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_bench_lists_every_lora_including_trained_ones(app, comfy):
    """The opposite of `permanent_lora_candidates`, which skips `lora_*` because
    a trained character LoRA is an AXIS, not an always-on. Here that file is
    exactly what you came to judge — and a downloaded one can be named anything.
    """
    from app.services import lora_bench as bench
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    _write_lora(comfy, 'krea/lora_MyChar_000001000.safetensors')
    with app.app_context():
        names = {e['filename'] for e in bench.list_bench_loras()}
    assert names == {KREA_CK, 'krea\\lora_MyChar_000001000.safetensors'}


def test_empty_state_names_the_folders_to_drop_a_file_into(app, comfy):
    """Someone arriving with a freshly downloaded .safetensors does not know
    where the app looks. "Nothing to show" would be a dead end."""
    from app.services import lora_bench as bench
    with app.app_context():
        payload = bench.bench_payload(LOCAL)
    assert payload['loras'] == []
    hint = payload['folder_hint']
    for folder in ('models/loras/z image', 'models/loras/sdxl', 'models/loras/krea'):
        assert folder in hint


def test_unknown_file_is_refused_with_the_folders_named(app, comfy):
    from app.services import lora_bench as bench
    with app.app_context():
        with pytest.raises(ValueError, match=r'models/loras/krea'):
            bench.resolve_bench_lora('krea\\not_here.safetensors')


def test_a_family_without_a_test_pipeline_says_so_instead_of_failing_obscurely(app, comfy):
    """`family_of_lora` knows flux / flux2klein / anima folders; the Test Studio
    renders none of them. Saying which families qualify beats "not found"."""
    from app.services import lora_bench as bench
    _write_lora(comfy, 'flux/some_flux_lora.safetensors')
    with app.app_context():
        with pytest.raises(ValueError, match=r'FLUX\.1 LoRAs cannot be benched yet'):
            bench.resolve_bench_lora('flux\\some_flux_lora.safetensors')


# ---------------------------------------------------------------------------
# The trigger word — the trap this feature exists to avoid
# ---------------------------------------------------------------------------

def test_trigger_is_prefilled_from_the_files_metadata(app, comfy):
    from app.services import lora_bench as bench
    _write_lora(comfy, 'krea/civitai_download.safetensors',
                metadata={'ss_output_name': 'zoeydoll'})
    with app.app_context():
        out = bench.read_lora_trigger(KREA_CK)
    assert out['trigger'] == 'zoeydoll' and out['source'] == 'metadata'
    assert out['readable'] is True


def test_a_generic_output_name_is_not_offered_as_a_trigger(app, comfy):
    """kohya writes the RUN name here. "last" is not an activation word, and
    prefilling it would look like an answer."""
    from app.services import lora_bench as bench
    _write_lora(comfy, 'krea/civitai_download.safetensors',
                metadata={'ss_output_name': 'last'})
    with app.app_context():
        out = bench.read_lora_trigger(KREA_CK)
    assert out['trigger'] == '' and out['source'] is None


def test_frequent_tags_are_suggestions_and_never_a_prefill(app, comfy):
    """The most frequent tag of a character LoRA is routinely `1girl`. Filling
    the trigger with it would produce exactly the false verdict — a grid of
    unaffected images blamed on the LoRA — that this feature prevents."""
    from app.services import lora_bench as bench
    _write_lora(comfy, 'krea/civitai_download.safetensors',
                metadata={'ss_tag_frequency': json.dumps(
                    {'10_zoey': {'1girl': 40, 'zoeydoll': 38, 'smile': 12}})})
    with app.app_context():
        out = bench.read_lora_trigger(KREA_CK)
    assert out['trigger'] == '' and out['source'] is None      # nothing guessed
    assert [c['tag'] for c in out['candidates']][:2] == ['1girl', 'zoeydoll']
    assert out['candidates'][0]['count'] == 40


def test_an_unreadable_file_reports_unknown_rather_than_raising(app, comfy):
    from app.services import lora_bench as bench
    path = comfy / 'models' / 'loras' / 'krea' / 'civitai_download.safetensors'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'not a safetensors file at all')
    with app.app_context():
        out = bench.read_lora_trigger(KREA_CK)
    assert out['readable'] is False and out['trigger'] == '' and out['candidates'] == []


# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------

def test_launching_without_a_trigger_is_refused_until_confirmed(app, comfy, quiet_engine):
    """We neither guess a trigger (false verdict) nor block the launch (a style
    LoRA genuinely has none) — we ask."""
    from app.services import lora_bench as bench
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    with app.app_context():
        with pytest.raises(ValueError, match=r'no activation word given'):
            bench.create_bench_run(LOCAL, KREA_CK, strengths=[0.8])
        out = bench.create_bench_run(LOCAL, KREA_CK, strengths=[0.8],
                                     no_trigger=True, prompt='a street at night')
    assert out['created'] == 1


def test_an_external_lora_runs_although_no_trigger_match_selects_it(app, comfy, quiet_engine):
    """THE unlock. `list_test_checkpoints` matches a file against the dataset's
    trigger, so a downloaded LoRA — carrying someone else's trigger — can never
    be selected that way. The bench passes it explicitly, after proving it is a
    real entry of its family's pool."""
    from app.models import LoraTestImage
    from app.services import lora_bench as bench
    from app.services import lora_test_studio as lts
    _write_lora(comfy, 'krea/civitai_download.safetensors',
                metadata={'ss_output_name': 'zoeydoll'})
    with app.app_context():
        ds = bench.ensure_bench_dataset(LOCAL, 'zoeydoll')
        assert [c['filename'] for c in lts.list_test_checkpoints(ds, 'krea')] == []
        out = bench.create_bench_run(LOCAL, KREA_CK, strengths=[0.4, 0.6, 0.8, 1.0],
                                     trigger='zoeydoll', prompt='a portrait')
        rows = LoraTestImage.query.filter_by(run_id=out['run_id']).all()
    assert out['created'] == 4 and len(rows) == 4
    assert {r.strength for r in rows} == {0.4, 0.6, 0.8, 1.0}
    assert {r.checkpoint for r in rows} == {KREA_CK}
    assert {r.seed for r in rows} == {out['seed']}          # fixed seed
    assert {r.prompt for r in rows} == {'a portrait'}       # fixed prompt


def test_the_sweep_is_capped_and_deduplicated(app, comfy, quiet_engine):
    from app.services import lora_bench as bench
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    with app.app_context():
        out = bench.create_bench_run(LOCAL, KREA_CK, strengths=[0.8, 0.8, 1.0],
                                     no_trigger=True, prompt='p')
        assert out['strengths'] == [0.8, 1.0] and out['created'] == 2
        with pytest.raises(ValueError, match=r'at most 8 strengths'):
            bench.create_bench_run(LOCAL, KREA_CK, no_trigger=True, prompt='p',
                                   strengths=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9])


def test_a_bench_cell_can_be_voted_on_and_the_score_comes_back(app, client, comfy,
                                                               quiet_engine, monkeypatch):
    """The whole point of the grid: 👍/👎 on a cell, and the aggregate that
    decides the ★. The vote rides the Studio's own route and its own
    `cell_scores` — the scratch dataset holds every bench run, so the score is
    per (file, strength) ACROSS runs, which is the bench's real question."""
    from app.models import LoraTestImage
    from app.routes import bench as bench_routes
    from app.services import lora_bench as bench
    monkeypatch.setattr(bench_routes, '_require_comfyui', lambda **k: None)
    monkeypatch.setattr(bench_routes, '_require_no_stalled_comfyui', lambda: None)
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    with app.app_context():
        out = bench.create_bench_run(LOCAL, KREA_CK, strengths=[0.6, 1.0],
                                     no_trigger=True, prompt='p')
        rows = sorted(LoraTestImage.query.filter_by(run_id=out['run_id']).all(),
                      key=lambda r: r.strength)
        for r in rows:                      # a cell is only judgeable once rendered
            r.status, r.filename = 'done', f'{r.id}.png'
        from app.extensions import db
        db.session.commit()
        liked = rows[0].id

    assert client.post(f'/api/dataset/lora-test/image/{liked}/rate',
                       json={'rating': 1}).status_code == 200
    scores = client.get('/api/bench/status').get_json()['scores']
    at = {s['strength']: s for s in scores if s['checkpoint'] == KREA_CK}
    assert at[0.6]['likes'] == 1 and at[0.6]['voted'] == 1
    assert at[1.0]['voted'] == 0
    # Under three votes the score is flagged, not presented as a ranking.
    assert at[0.6]['low_confidence'] is True


# ---------------------------------------------------------------------------
# The GPU guard, in BOTH directions
# ---------------------------------------------------------------------------

def test_a_dataset_run_in_flight_blocks_a_bench_run(app, comfy, quiet_engine):
    """The per-dataset guard cannot see across datasets, so the bench uses the
    GLOBAL one: a bench run competes for the same GPU as any dataset run."""
    from app.extensions import db
    from app.models import LoraTestImage
    from app.services import face_dataset_service as svc
    from app.services import lora_bench as bench
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    with app.app_context():
        other = svc.create_dataset(LOCAL, 'Alice', 'alice')
        db.session.add(LoraTestImage(dataset_id=other.id, checkpoint='krea\\x.safetensors',
                                     strength=1.0, seed=1, run_seed=1, run_id='c' * 32,
                                     status='pending'))
        db.session.commit()
        with pytest.raises(ValueError, match=r'a test run is already in progress'):
            bench.create_bench_run(LOCAL, KREA_CK, no_trigger=True, prompt='p',
                                   strengths=[0.8])


def test_a_bench_run_in_flight_blocks_a_dataset_run(app, comfy, quiet_engine):
    """The mirror the design spec did not ask for, and the one that would have
    failed silently: two runs sharing a GPU just look slow."""
    from app.extensions import db
    from app.models import LoraTestImage
    from app.services import face_dataset_service as svc
    from app.services import lora_bench as bench
    from app.services import lora_test_studio as lts
    with app.app_context():
        ds = bench.ensure_bench_dataset(LOCAL, 'zoeydoll')
        db.session.add(LoraTestImage(dataset_id=ds.id, checkpoint=KREA_CK, strength=0.8,
                                     seed=1, run_seed=1, run_id='d' * 32, status='pending'))
        other = svc.create_dataset(LOCAL, 'Alice', 'alice')
        db.session.commit()
        with pytest.raises(ValueError, match=r'a LoRA bench run is already in progress'):
            lts.create_run(LOCAL, other.id, ['krea\\x.safetensors'], [1.0], prompt='p')


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def test_status_route_publishes_the_picker_and_the_hint(app, client, comfy):
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    body = client.get('/api/bench/status').get_json()
    assert [e['filename'] for e in body['loras']] == [KREA_CK]
    assert body['dataset_id'] is None and body['runs'] == []
    assert body['default_strengths'] == [0.4, 0.6, 0.8, 1.0]
    assert 'models/loras/krea' in body['folder_hint']


def test_status_route_refuses_to_show_a_run_that_is_not_a_bench(app, client, comfy):
    """`?run=` is user input and a Studio run's id is just as valid a string.
    Rendering one here would score another dataset's grid against the bench's
    aggregates — two different runs displayed as one."""
    from app.extensions import db
    from app.models import LoraTestImage
    from app.services import face_dataset_service as svc
    from app.services import lora_bench as bench
    with app.app_context():
        bench.ensure_bench_dataset(LOCAL, 'zoeydoll')
        other = svc.create_dataset(LOCAL, 'Alice', 'alice')
        db.session.add(LoraTestImage(dataset_id=other.id, checkpoint='krea\\x.safetensors',
                                     strength=1.0, seed=1, run_seed=1, run_id='f' * 32,
                                     status='done', filename='a.png', prompt='p'))
        db.session.commit()
    body = client.get('/api/bench/status', query_string={'run': 'f' * 32}).get_json()
    assert body['run'] is None
    # …and the Studio's own route still shows it, because that is where it lives.
    assert client.get('/api/studio/run/%s/status' % ('f' * 32)).status_code == 200


def test_trigger_route_reads_the_header(app, client, comfy):
    _write_lora(comfy, 'krea/civitai_download.safetensors',
                metadata={'ss_output_name': 'zoeydoll'})
    body = client.get('/api/bench/trigger', query_string={'filename': KREA_CK}).get_json()
    assert body['trigger'] == 'zoeydoll' and body['family'] == 'krea'


def test_run_route_refuses_a_missing_trigger_with_400(app, client, comfy, quiet_engine,
                                                     monkeypatch):
    from app.routes import bench as bench_routes
    monkeypatch.setattr(bench_routes, '_require_comfyui', lambda **k: None)
    monkeypatch.setattr(bench_routes, '_require_no_stalled_comfyui', lambda: None)
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    r = client.post('/api/bench/run', json={'filename': KREA_CK, 'strengths': [0.8]})
    assert r.status_code == 400
    assert 'activation word' in r.get_json()['error']


def test_run_route_launches_and_reports_the_run(app, client, comfy, quiet_engine,
                                                monkeypatch):
    from app.routes import bench as bench_routes
    monkeypatch.setattr(bench_routes, '_require_comfyui', lambda **k: None)
    monkeypatch.setattr(bench_routes, '_require_no_stalled_comfyui', lambda: None)
    _write_lora(comfy, 'krea/civitai_download.safetensors')
    r = client.post('/api/bench/run', json={'filename': KREA_CK, 'trigger': 'zoeydoll',
                                            'strengths': [0.6, 1.0], 'prompt': 'a portrait'})
    assert r.status_code == 200
    body = r.get_json()
    assert body['ok'] and body['created'] == 2 and len(body['run_id']) == 32
    assert body['strengths'] == [0.6, 1.0] and body['family'] == 'krea'

    # …and the run is polled through the STUDIO's own lifecycle route: the bench
    # deliberately owns no second status/cancel/resume endpoint.
    status = client.get(f"/api/bench/status").get_json()
    assert [r_['run_id'] for r_ in status['runs']] == [body['run_id']]
    poll = client.get(f"/api/studio/run/{body['run_id']}/status")
    assert poll.status_code == 200 and len(poll.get_json()['cells']) == 2
