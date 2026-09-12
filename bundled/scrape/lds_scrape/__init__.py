"""Web scraping — the sources engine and its scan routes, as a bundled plugin.

What lives here: the per-platform sources and their registry, the URL
validators, and the two read-only scan endpoints (`/api/scrape/scan`,
`/api/scrape/thumb`). What stays in the core, and why: the hardened fetch
(`app.utils.netfetch`, used by the dataset service, the video bank and the
Civitai browser), the credential resolvers (`app.utils.credentials`), and the
import side — `POST /api/dataset/<id>/scrape-import` and its bank/video-bank
siblings only download URLs the user picked, whichever screen listed them.

The scan routes keep their historical URLs under `/api/` (a plugin may register
any prefix under `/api/`, the access-token gate stands there); the panels that
call them are this plugin's frontend contribution.
"""
__version__ = '1.0.7'


def register(ctx):
    from .probes import PROBES
    from .routes import bp
    ctx.register_blueprint(bp, url_prefix='/api')
    ctx.register_install_action('scrape_extras', label='Install web scraping dependencies',
                                python='app', requirements=ctx.dir / 'requirements.txt')
    for key, fn in PROBES.items():
        ctx.register_probe(key, fn)
