"""🤗 Publish to Hugging Face — the bundled plugin.

A dataset becomes a ``dataset`` repo on the Hub (``publish.py``, moved whole
from the core's ``services/hf_publish.py``): the kept images as metadata-free
PNG copies, their captions with the trigger word, a ``metadata.jsonl`` and a
dataset card — private by default, consent required, the reference photo off
by default. The routes are the ones the screen already calls
(``/api/dataset/<id>/publish-hf…``).

What the core keeps, and why: the ``HF_TOKEN`` secret with its Settings and
Setup fields (gated base downloads and cloud training read the same token),
and the Hub client bricks every publisher shares (``app.utils.hf_hub``: the API
construction, the write-scope preflight, the status scraping, the structured
error) — the cloud lane's custom-base push and storage pre-check draw them too,
and the core cannot borrow them from a plugin.

The one capability this plugin owns is ``hf_publish``: "a token is configured",
network-free (the write-scope check is a live preflight at publish time). The
dataset workspace's Import & export section offers the Hub only while it is
true — and only while this plugin is on.
"""


def _token_configured() -> bool:
    from lds_sdk import config as cfg
    return bool(cfg.secret('HF_TOKEN'))


def register(ctx):
    from .routes import bp
    ctx.register_blueprint(bp, url_prefix='/api')   # the URLs the screen already calls
    ctx.register_probe('hf_publish', _token_configured)
