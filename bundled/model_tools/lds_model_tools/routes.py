"""Model-file tools that are pure file-in / file-out work on this machine â€”
the routes of the bundled ``model_tools`` plugin.

No ai-toolkit gate, no ComfyUI gate, no cloud: merging a LoRA into a base reads
two files and writes a third; quantizing a model reads one and writes its fp8
twin. Neither needs a GPU or a training environment, so gating them on either
would refuse the one user who most needs them â€” someone who trained on a rented
machine and only has the weights.

The URLs are the ones the screens already call (``/api/tools/lora-mergeâ€¦``,
``/api/tools/fp8-quantizeâ€¦``): the faÃ§ade registers this blueprint under the
core's ``/api`` prefix. With the plugin off they answer 404 like any absent
route; the one-click fp8 delivery (``/api/tools/fp8-deliverâ€¦``, the dense
lane's) belongs to ``cloud_training`` and binds this plugin's converter on
first use.
"""
from flask import Blueprint, current_app, jsonify, request

from lds_sdk.http import map_error as _map_error

bp = Blueprint('model_tools', __name__)


@bp.get('/tools/model-runtime')
def tools_model_runtime():
    """Owned installation state and a real CPU probe; never install on read."""
    from . import runtime
    return jsonify({'ok': True, **runtime.status(refresh=request.args.get('refresh') == '1')})


# --- Merge a LoRA into a base checkpoint -------------------------------------------
# The step between "I trained a LoRA" and "I have a model to publish". See
# `lora_merge` for what the arithmetic is and why the output says, in its own
# header, that it came from a merge and not from training.

@bp.post('/tools/lora-merge/plan')
def tools_lora_merge_plan():
    """What merging these LoRAs into this base would produce, or WHY it is refused.

    Always 200: the panel disables its button and shows the reason, instead of
    letting the user commit to a 26 GB write and meeting the refusal afterwards.
    Every condition the run needs is decided here â€” see ``lora_merge_job.plan``.
    """
    from . import lora_merge_job
    d = request.get_json(silent=True) or {}
    return jsonify(lora_merge_job.describe(
        d.get('base'), d.get('loras'),
        destination=d.get('destination'),
        destination_dir=d.get('destination_dir'),
        overwrite=bool(d.get('overwrite'))))


@bp.post('/tools/lora-merge')
def tools_lora_merge_start():
    from . import lora_merge_job
    d = request.get_json(silent=True) or {}
    try:
        info = lora_merge_job.start_async(
            current_app._get_current_object(), d.get('base'), d.get('loras'),
            destination=d.get('destination'),
            destination_dir=d.get('destination_dir'),
            overwrite=bool(d.get('overwrite')))
    except Exception as e:                     # noqa: BLE001 â€” mapped, not swallowed
        return _map_error(e)
    return jsonify({'ok': True, **info, 'status': lora_merge_job.status()})


@bp.get('/tools/lora-merge/status')
def tools_lora_merge_status():
    """Where the merge is. Also the place a state stranded by a restart is
    cleared: this is the first thing the panel asks after a reload, so a "merge"
    left running by a process that no longer exists is corrected before it can
    show a progress bar that never moves or refuse the next merge for six hours.
    """
    from . import lora_merge_job
    reconciled = lora_merge_job.reconcile()
    return jsonify({'ok': True, 'reconciled': reconciled,
                    **(lora_merge_job.status() or {})})


@bp.post('/tools/lora-merge/cancel')
def tools_lora_merge_cancel():
    from . import lora_merge_job
    return jsonify({'ok': True, **lora_merge_job.cancel()})


# --- Local fp8 quantization ---------------------------------------------------
# Same conversion as the post-training pod export, started by hand on a model
# already on this machine. No ai-toolkit and no cloud gate: it is a pure
# file-in / file-out operation on the CPU (see fp8_quantize's module note).

@bp.post('/tools/fp8-quantize/plan')
def tools_fp8_quantize_plan():
    """What quantizing this file would produce, or WHY it is refused.

    Always 200: the panel disables its button with the reason instead of showing
    an error toast after a click.
    """
    from . import fp8_quantize
    d = request.get_json(silent=True) or {}
    return jsonify(fp8_quantize.describe(d.get('path')))


@bp.post('/tools/fp8-quantize')
def tools_fp8_quantize_start():
    from . import fp8_quantize
    d = request.get_json(silent=True) or {}
    try:
        info = fp8_quantize.start_async(current_app._get_current_object(),
                                        d.get('path'),
                                        overwrite=bool(d.get('overwrite')))
    except Exception as e:                     # noqa: BLE001 â€” mapped, not swallowed
        return _map_error(e)
    return jsonify({'ok': True, **info, 'status': fp8_quantize.status()})


@bp.get('/tools/fp8-quantize/status')
def tools_fp8_quantize_status():
    from . import fp8_quantize
    return jsonify({'ok': True, **(fp8_quantize.status() or {})})
