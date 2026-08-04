"""⚖ LoRA bench blueprint: sweep the strength of a LoRA you downloaded.

Read routes (`/loras`, `/trigger`, `/status`) stay reachable with ComfyUI
offline, like the Studio's — a run history must never go dark. Only `/run`
enqueues, so only `/run` is gated on the ComfyUI probe.

Run lifecycle (status polling, cancel, resume) deliberately has NO route here:
a bench run is a Test Studio run, and `/api/studio/run/<run_id>/…` already owns
it. Duplicating those endpoints is how the two surfaces would start to disagree.
"""
from flask import Blueprint, jsonify, request

from ..config import LOCAL_USER
from ..services import lora_bench as bench
from ._common import (_map_error, _require_comfyui, _require_no_stalled_comfyui,
                      _studio_arch_mismatch_response, _studio_missing_response)

bp = Blueprint('bench', __name__, url_prefix='/api/bench')


@bp.get('/status')
def bench_status():
    """Everything the page needs on load: pickable files, where to drop new
    ones, past runs, and — with `?run=<run_id>` — that run's live cells."""
    return jsonify(bench.bench_payload(LOCAL_USER, run_id=request.args.get('run')))


@bp.get('/trigger')
def bench_trigger():
    """What the FILE says about its activation word — read from its safetensors
    header. `?filename=` in LoraLoader form."""
    try:
        return jsonify(bench.read_lora_trigger(request.args.get('filename')))
    except Exception as e:
        return _map_error(e)


@bp.post('/run')
def bench_run():
    gate = _require_comfyui()
    if gate:
        return gate
    gate = _require_no_stalled_comfyui()
    if gate:
        return gate
    d = request.get_json(silent=True) or {}
    try:
        res = bench.create_bench_run(
            LOCAL_USER, d.get('filename'), strengths=d.get('strengths'),
            trigger=d.get('trigger'), prompt=d.get('prompt'), seed=d.get('seed'),
            no_trigger=d.get('no_trigger') is True)
    except Exception as e:
        from ..services.lora_test_studio import StudioArchMismatch, StudioAssetsMissing
        if isinstance(e, StudioArchMismatch):   # wrong-arch file → actionable 409
            return _studio_arch_mismatch_response(e)
        if isinstance(e, StudioAssetsMissing):  # models/nodes absent → actionable 409
            return _studio_missing_response(e)
        return _map_error(e)
    return jsonify({'ok': True, **{k: res[k] for k in
                                   ('created', 'seed', 'run_id', 'dataset_id',
                                    'family', 'filename', 'label', 'prompt',
                                    'strengths')}})


@bp.post('/clear')
def bench_clear():
    """Drop the bench history. Keeps the scratch row itself — see
    `lora_bench.clear_bench_history` for why deleting it would be worse."""
    return jsonify({'ok': True, 'deleted': bench.clear_bench_history(LOCAL_USER)})
