# app/scrape/sources/__init__.py
"""Source-specific scrapers enumerate media from profiles, niches and listings.

Each module exposes scan(validation_result) -> (items, error), where items
is a list of shared-schema dictionaries:
    {'url', 'title', 'thumbnail', 'type' ('video'|'image'), 'platform', ...}
Actual downloads use /api/scrape/download with yt-dlp or a dedicated strategy."""
# Register sources explicitly; priority determines order.
# To add a source, create sources/<name>.py as a base.Source subclass with
# match(), scan(), optional download(), and a registry.register(...) call,
# then import it here. Avoid silent or nondeterministic pkgutil imports.
from . import registry   # noqa: F401  (exposes and initializes the registry first)
from . import redgifs    # noqa: F401
from . import instagram  # noqa: F401
from . import picazor    # noqa: F401
from . import erome      # noqa: F401
# Removed dump/leak sites are explicitly rejected by validators.py;
# Coomer/Kemono/Bunkr/Cyberdrop have no sources to register.
from . import x          # noqa: F401
from . import tiktok     # noqa: F401
from . import image_sites  # noqa: F401  (PornPics: category-based photos)
from . import civitai     # noqa: F401  (.com/.red: AI images by tag)
from . import fapello     # noqa: F401  (model pages and language mirrors)
from . import reddit       # noqa: F401  (keyword search through the OAuth API)
from . import sexcom      # noqa: F401  (keyword search through the site's API)
from . import pexels      # noqa: F401  (official API; key required)
from . import websearch   # noqa: F401  (DuckDuckGo keyword image search)
from . import universal  # noqa: F401

# Require exactly one universal source and unique names. Fail at startup
# rather than silently dispatching to the wrong source.
registry.assert_one_universal()
