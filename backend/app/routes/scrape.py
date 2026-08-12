"""Scrape SCAN + THUMB proxy (read-only) — feeds the concept-dataset builder.

Only two endpoints are lifted from the source app's scrape blueprint, and only
their READ-ONLY parts: `/api/scrape/scan` (URL → list of media items via the
ported sources engine, downloads nothing) and `/api/scrape/thumb` (server-side
fetch of a remote thumbnail the browser can't hotlink). The shared download
pool, quota (ScrapeScanLog) and admin/category gates are dropped — this app is a
single local user. The anti-SSRF guards (`_validate_public_http_url`, no-redirect
fetch, content-type + size caps) are KEPT: the server still fetches arbitrary
user-supplied URLs.

Actually pulling the chosen images INTO a dataset is a separate, autonomous path
(`POST /api/dataset/<id>/scrape-import` in routes/datasets.py → svc.scrape_import_urls).
"""
from urllib.parse import urlparse
from io import BytesIO
from pathlib import Path
import hashlib
import os
import threading
from time import time

from flask import Blueprint, request, jsonify, Response
from PIL import Image

from ..scrape.netfetch import _validate_public_http_url

bp = Blueprint('scrape', __name__, url_prefix='/api')

MAX_SCAN_PAGE = 50
MAX_THUMB_BYTES = 12 * 1024 * 1024  # 12 MB
_ALLOWED_THUMB_TYPES = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/avif'}

# A scan-results grid asks for one thumbnail per tile and the frontend fires
# them all at once; each is a live server-side fetch from Instagram's CDN. Firing
# dozens concurrently trips Instagram's anti-bot rate limiter (429/403), which is
# the usual cause of "thumbnails break and never load". Cap simultaneous upstream
# fetches so the live ones get through, and remember which URLs FAILED for a
# short window so reloading the grid doesn't re-hit Instagram for every dead tile
# (which would rate-limit the live ones too).
_UPSTREAM_SEMAPHORE = threading.BoundedSemaphore(16)
_UPSTREAM_TIMEOUT = 15  # s per fetch (was 20)
_FAIL_TTL = 90          # s
_fail_cache = {}
_fail_cache_lock = threading.Lock()


def _is_failed(url):
    with _fail_cache_lock:
        ts = _fail_cache.get(url)
        if ts is None:
            return False
        if time() - ts > _FAIL_TTL:
            del _fail_cache[url]
            return False
        return True


def _mark_failed(url):
    with _fail_cache_lock:
        _fail_cache[url] = time()


# The CDN URL behind /scrape/thumb is often a FULL-RESOLUTION file (an Instagram
# CDN link is a ~1-4 MB JPEG, not a thumbnail). Serving it unchanged means every
# grid tile downloads megabytes and the page crawls the more tiles load. Resize
# stills to a small webp (like the bank thumbs) and cache the result on disk, so
# repeat fetches of the same URL neither re-download from the CDN nor re-resize.
_THUMB_MAX_SIDE = 512
_THUMB_CACHE_TTL = 7 * 24 * 3600  # seconds; CDN links carry an expiry, so cap reuse
_THUMB_CACHE_DIR = None


def _thumb_cache_dir():
    global _THUMB_CACHE_DIR
    if _THUMB_CACHE_DIR is None:
        base = os.environ.get('LDS_DATA_DIR')
        _THUMB_CACHE_DIR = Path(base) if base else Path(__file__).resolve().parents[3] / 'data'
        _THUMB_CACHE_DIR = _THUMB_CACHE_DIR / 'scrape_thumbs'
    return _THUMB_CACHE_DIR


def _thumb_cache_path(url):
    h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]
    return _thumb_cache_dir() / f'{h}.webp'


def _resized_thumb_bytes(url, data):
    """Return (bytes, content_type) for a small cached webp, or (None, None) if
    the source can't be resized (then the caller serves the original)."""
    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception:
        return None, None
    # Animated GIFs: resizing to a still webp would throw the animation away.
    if getattr(im, 'is_animated', False):
        return None, None
    cache = _thumb_cache_path(url)
    try:
        if cache.is_file() and time() - cache.stat().st_mtime < _THUMB_CACHE_TTL:
            return cache.read_bytes(), 'image/webp'
    except Exception:
        pass
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        if im.mode not in ('RGB', 'RGBA'):
            im = im.convert('RGB')
        im.thumbnail((_THUMB_MAX_SIDE, _THUMB_MAX_SIDE), Image.LANCZOS)
        buf = BytesIO()
        im.save(buf, 'WEBP', quality=72)
        out = buf.getvalue()
        try:
            cache.write_bytes(out)
        except Exception:
            pass
        return out, 'image/webp'
    except Exception:
        return None, None


@bp.post('/scrape/scan')
def scrape_scan():
    """List the downloadable media of a URL via the sources registry (read-only).

    Body: {"url": "...", "page": 0, "include_albums": false}. include_albums
    only matters for gallery-listing sources (PornPics category/tag/search):
    false (default) returns one cover per matched gallery, true dives into every
    photo of each gallery. Returns {scannable, platform, url_type, count, items,
    paginated, page, category} (200), {error, suggestions} (400), or {error}
    (502) on a source-level failure. Downloads nothing."""
    data = request.get_json(silent=True) or {}
    url = data.get('url')
    if not url or not isinstance(url, str):
        return jsonify({'error': 'URL missing.'}), 400
    if len(url) > 2048:
        return jsonify({'error': 'URL too long.'}), 400
    # "Load more" pagination (paginable sources): 0-based, hard-capped (deep pages
    # make gallery-dl re-paginate the whole listing → slow + abuse vector).
    try:
        page = int(data.get('page', 0))
    except (TypeError, ValueError):
        page = 0
    page = max(0, min(page, MAX_SCAN_PAGE))

    from ..scrape.validators import url_validator
    result = url_validator.validate_url(url)
    if not result.is_valid:
        return jsonify({'error': result.error or 'invalid URL',
                        'suggestions': result.suggestions}), 400

    from ..scrape.sources import registry  # local import: avoid an import cycle at load
    match = registry.resolve(url)
    if match is None or match.source is None:
        return jsonify({'error': result.error or 'unsupported URL.',
                        'suggestions': result.suggestions or
                        ['Check the URL is a reachable media page.']}), 400

    match.page = page
    match.include_albums = bool(data.get('include_albums'))
    match.fresh = bool(data.get('fresh'))
    items, err = match.source.scan(match)
    # `partial` (cf. gdl.enumerate / base.ResultList) : le budget de temps global a
    # coupé la récursion d'albums avant d'avoir tout exploré — les items présents
    # restent valides, il en manque potentiellement. Lu directement sur `items` :
    # `ResultList` (contrat de source public, app/scrape/sources/base.py — PAS un
    # détail gallery-dl) porte l'attribut sur le retour qu'`enumerate()` produit,
    # que la source le renvoie tel quel (universal.py, gdl_source.py, erome.py,
    # image_sites.py, civitai.py, sexcom.py — TOUTES les sources gdl-backed) sans
    # avoir besoin de le relayer explicitement. redgifs.py et instagram.py ne sont
    # PAS gdl-backed (ports autonomes) mais réutilisent le même `ResultList` pour
    # signaler leurs propres troncatures (page RedGifs refusée après une page
    # réussie, itération Instagram interrompue en cours de route) — même
    # convention, aucun changement ici. Reddit (reddit.py) est elle aussi
    # gdl-backed en apparence seulement — port autonome — mais renvoie désormais
    # un `ResultList` portant `partial` (budget d'appels listing épuisé). Seule
    # une source qui n'implémente réellement aucune notion de troncature
    # (Pexels…) renvoie une liste ordinaire → `getattr` retombe alors sur False.
    partial = bool(getattr(items, 'partial', False))
    # Optional cause of the truncation, when the source can say (see
    # ResultList.partial_reason) — lets the UI phrase 'stopped at the built-in
    # limit' calmly vs 'cut short by a problem'.
    partial_reason = getattr(items, 'partial_reason', None)
    if err and getattr(err, 'kind', None) != 'empty':
        return jsonify({'error': err, 'platform': result.platform.value,
                        'url_type': result.url_type.value}), 502
    if err:
        # kind='empty' : gallery-dl (ou un moteur équivalent) a tourné sans
        # incident et n'a juste rien trouvé — un scan vide réussi, pas une panne
        # (cf. docstring de GdlError, app/scrape/sources/gdl.py). La règle
        # gouvernante de cette vague — un bloc ne doit jamais paraître vide, un
        # résultat vide ne doit jamais paraître en échec — se vérifie ICI, au
        # seul endroit qui voit TOUTES les sources gdl-backed (gdl_source.py,
        # erome.py, image_sites.py, civitai.py, sexcom.py, universal.py) : avant
        # cette vérif, seule UniversalSource honorait la règle, les autres
        # transformaient un « rien ici » légitime en toast d'échec (502).
        items = []
    # Une source peut être généralement paginable tout en résolvant certaines
    # URLs unitaires. scan() peut alors poser un override sur Match, sans que la
    # route connaisse la plateforme concernée.
    paginated = getattr(match, 'paginated', None)
    if paginated is None:
        paginated = getattr(match.source, 'paginated', False)
    # The requested page is clamped above. Never advertise another page once
    # that effective page reaches the hard limit, even if an upstream API says
    # it has more results.
    if page >= MAX_SCAN_PAGE:
        paginated = False
    return jsonify({
        'scannable': True, 'platform': result.platform.value,
        'url_type': result.url_type.value,
        'count': len(items or []), 'items': items or [],
        'paginated': bool(paginated),
        'page': page,
        'category': getattr(match.source, 'category', 'video'),
        # True = the listing was cut short by the scan's time budget before every
        # album/page could be explored: the items shown are valid, but there may
        # be more. Compounds with `from_albums` clearing `paginated` above (cf.
        # gdl.enumerate docstring) — without this flag a truncated result looked
        # exactly like a complete one, with no "Load more" and no hint anything
        # was cut.
        'partial': partial,
        'partialReason': partial_reason,
    })


@bp.get('/scrape/thumb')
def scrape_thumb():
    """Thumbnail proxy. Source CDNs block direct hotlinking (referer/CORS) so the
    browser <img> fails; fetch server-side (curl_cffi impersonate=chrome + Referer)
    and restream from our origin. SSRF-guarded (public http(s) only, no redirects),
    content-type restricted to raster, size-capped."""
    url = (request.args.get('url') or '').strip()
    ok, err = _validate_public_http_url(url)
    if not ok:
        return jsonify({'error': err or 'invalid URL'}), 400
    try:
        from curl_cffi import requests as cf_requests
    except ImportError:
        return jsonify({'error': 'curl_cffi unavailable'}), 503
    if _is_failed(url):
        return jsonify({'error': 'thumbnail unavailable (cached)'}), 502
    host = urlparse(url).hostname or ''
    try:
        # allow_redirects=False: only the ALREADY-validated host is fetched. A 3xx
        # toward an internal IP would bypass the upstream SSRF guard (TOCTOU/redirect).
        # The semaphore caps concurrent upstream hits so a big grid doesn't rate-limit
        # itself off Instagram.
        with _UPSTREAM_SEMAPHORE:
            r = cf_requests.get(url, impersonate='chrome', timeout=_UPSTREAM_TIMEOUT,
                                stream=True, allow_redirects=False,
                                headers={'Referer': f'https://{host}/', 'Accept': 'image/*,*/*'})
    except Exception:
        _mark_failed(url)
        return jsonify({'error': 'fetch failed'}), 502
    if 300 <= r.status_code < 400:
        try: r.close()
        except Exception: pass
        _mark_failed(url)
        return jsonify({'error': 'redirect refused'}), 502
    ctype = (r.headers.get('content-type') or '').split(';')[0].strip().lower()
    if r.status_code != 200 or ctype not in _ALLOWED_THUMB_TYPES:
        try: r.close()
        except Exception: pass
        _mark_failed(url)
        return jsonify({'error': 'unsupported type'}), 415
    data = bytearray()
    try:
        for chunk in r.iter_content(8192):
            if not chunk:
                continue
            data += chunk
            if len(data) > MAX_THUMB_BYTES:
                return jsonify({'error': 'thumbnail too large'}), 413
    finally:
        try: r.close()
        except Exception: pass
    # Hardened: no MIME sniffing, inline, locked-down CSP (defense in depth).
    # Still images are resized + cached to a small webp; animated GIFs (and any
    # image that can't be resized) are served as fetched.
    resized, out_ctype = _resized_thumb_bytes(url, bytes(data))
    if resized is not None:
        data = resized
        ctype = out_ctype
    return Response(data, content_type=ctype, headers={
        'Cache-Control': 'public, max-age=86400',
        'X-Content-Type-Options': 'nosniff',
        'Content-Disposition': 'inline; filename="thumb"',
        'Content-Security-Policy': "default-src 'none'; sandbox",
    })
