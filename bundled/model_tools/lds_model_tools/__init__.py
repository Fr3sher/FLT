"""🧰 Model tools — the bundled plugin.

Two tools that are pure file-in / file-out work on this machine, moved whole
from the core: the manual fp8 quantization of a full-precision model
(``fp8_quantize.py`` — the same conversion the post-training pod export runs,
started by hand on a file already here, in the managed Model tools CPU engine
or an explicit ``quantize.python`` override) and the LoRA merge
(``lora_merge.py``, the self-contained arithmetic run as a script in that same
interpreter, and ``lora_merge_job.py``, the plan / start / status / cancel
around it). Their routes are the ones the screens already call
(``/api/tools/lora-merge…``, ``/api/tools/fp8-quantize…``).

What the core keeps, and why: ``services/fp8_export.py`` — the exporter CLI
the cloud lane ships to the pod as source text, and the fp8 arithmetic its
storage forecasts read; and the ``quantize`` config section, owned here and read
by the core's config loader like every section. The ``cloud_training`` plugin
owns the dense lane's one-click fp8 delivery (``fp8_local_delivery.py``,
``/api/tools/fp8-deliver…``), which binds this plugin's converter on first use.
"""


def register(ctx):
    from . import runtime
    from .routes import bp
    runtime.register(ctx)
    ctx.register_blueprint(bp, url_prefix='/api')   # the URLs the screens already call
