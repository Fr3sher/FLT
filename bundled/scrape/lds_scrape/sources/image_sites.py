# app/scrape/sources/image_sites.py
"""Category-based photo source: PornPics, excluding anime/drawing boorus.

PornPics offers galleries by category, tag or performer, e.g. /lingerie/ and
/tags/<tag>/. Listings support two scan modes:

- covers (default): return the thumbnail chosen by the site for each gallery,
  rather than its first photo. Page zero reads HTML tiles; later pages use the
  infinite-scroll AJAX endpoint (offset/limit, g_url, t_url_460, desc). Replace
  /460/ with /1280/ for full resolution. One HTTP request per page, no gallery-dl.
- albums ("Scan full albums"): gallery-dl's PornpicsCategoryExtractor enumerates
  each listed gallery and its complete contents.

A direct /galleries/... URL always returns the complete album as top-level
media. If cover parsing fails, silently fall back to gallery-dl capped at one
image per album.

Realbooru and ImageFap were removed on 2026-06-27 for quality/security concerns;
Motherless was removed earlier because its DNS was unreachable."""
import logging
import re
from urllib.parse import urlparse

from ..validators import Platform
from .base import Capabilities
from .gdl_source import GalleryDlSource
from . import gdl
from . import registry

logger = logging.getLogger(__name__)

# Public content without authentication, including images/GIFs/video.
# Use polite limits for large listings and gallery-dl for downloads.
_PHOTO_CAPS = Capabilities(
    can_enumerate_profile=True,
    polite=True,
    media_kinds=frozenset({'image', 'video'}),
    own_downloader=True,
)

# Raise the scan item limit above gdl's default of 120 so "Scan full albums"
# can return a batch of galleries rather than stopping in the first one.
# gallery-dl paginates automatically; --range bounds the total while simulation
# only fetches metadata. Covers mode effectively returns gallery_cap per page.
_PHOTO_SCAN_MAX = 400


# Galleries per "Load more" page. Category/tag/search listings queue galleries
# as gallery-dl chapters, so only --chapter-range, not image-range, bounds them.
# Without this limit, scanning entire categories can time out without media.
# Match gdl.DEFAULT_MAX_ALBUMS: enumerate at most this many galleries, then
# recurse into each with its images bounded by --range.
_GALLERY_CAP = 8


# --- Mode covers : parse du listing (HTML page 0, AJAX ensuite) ---------------
_COVERS_PER_PAGE = 20     # taille de page du site (grille ET endpoint AJAX)

# A listing tile contains a gallery link followed by a lazy-loaded thumbnail.
# Accept single and double quotes; bound each match to avoid crossing tiles.
_TILE_RE = re.compile(
    r"class=[\"']rel-link[\"']\s+href=[\"'](?P<href>[^\"']+)[\"']"
    r".{0,600}?data-src=[\"'](?P<thumb>[^\"']+)[\"']"
    r"(?:.{0,300}?\salt=[\"'](?P<alt>[^\"']*)[\"'])?",
    re.S)
_SIZE_SEG_RE = re.compile(r'/(?:300|460)/')


def _full_size(thumb_url):
    """Convert a CDN thumbnail's /300/ or /460/ segment to full-resolution /1280/.
    Gallery pages link the same image/hash at that size."""
    return _SIZE_SEG_RE.sub('/1280/', thumb_url, count=1)


def _listing_html(url):
    """Fetch listing HTML (test seam). Raises on network or HTTP failure."""
    from curl_cffi import requests as cf_requests
    r = cf_requests.get(url, impersonate='chrome', timeout=20)
    r.raise_for_status()
    return r.text


def _listing_json(url, offset):
    """Fetch an AJAX listing batch (test seam). Offset zero is not JSON, so
    page zero uses HTML instead. Raises on failure."""
    from curl_cffi import requests as cf_requests
    r = cf_requests.get(url, params={'limit': _COVERS_PER_PAGE, 'offset': offset},
                        impersonate='chrome', timeout=20,
                        headers={'Accept': 'application/json, text/javascript, */*; q=0.01',
                                 'Referer': url,
                                 'X-Requested-With': 'XMLHttpRequest'})
    r.raise_for_status()
    return r.json()


def _covers_scan(url, page):
    """Return listing thumbnails as (items, None), or ([], None) at pagination end.
    Return (None, None) to request gallery-dl fallback after empty parsing,
    network failure or missing curl_cffi. Never raises."""
    def item(full, thumb, title):
        return {'url': full, 'title': (title or '')[:200], 'thumbnail': thumb,
                'type': 'image', 'platform': 'pornpics'}
    try:
        items = []
        if page <= 0:
            for m in _TILE_RE.finditer(_listing_html(url)):
                href, thumb = m.group('href'), m.group('thumb')
                if '/galleries/' not in href:      # tuile hors grille (nav, pubs…)
                    continue
                items.append(item(_full_size(thumb), thumb, m.group('alt')))
            return (items, None) if items else (None, None)   # empty parse: changed layout; fall back
        data = _listing_json(url, offset=page * _COVERS_PER_PAGE)
        if not isinstance(data, list):
            return None, None
        for g in data:
            thumb = g.get('t_url_460') or g.get('t_url')
            if thumb:
                items.append(item(_full_size(thumb), thumb, g.get('desc')))
        return items, None      # [] legitimately marks the end of the listing
    except Exception as e:
        logger.warning('pornpics covers scan failed (%s) — falling back to gallery-dl', e)
        return None, None


class _PhotoSiteSource(GalleryDlSource):
    priority = 100
    capabilities = _PHOTO_CAPS
    scan_max_items = _PHOTO_SCAN_MAX
    gallery_cap = _GALLERY_CAP
    paginated = True   # "Load more" requests the next gallery batch
    category = 'image'  # photo galleries are available to non-admins

    def scan(self, match):
        # Select the gallery window for zero-based match.page, set by /scan:
        # page 0 is 1-cap, page 1 is cap+1 through 2*cap. --chapter-range bounds
        # gallery enumeration, while the raised max_items/--range bounds images
        # per gallery instead of stopping at gdl's default 120.
        page = max(0, getattr(match, 'page', 0) or 0)
        start = page * self.gallery_cap + 1
        end = (page + 1) * self.gallery_cap
        extra = ['--chapter-range', f'{start}-{end}']
        if self.gdl_opts:
            extra = list(self.gdl_opts) + extra
        # Without include_albums, this is the covers fallback; the normal path
        # is _covers_scan. Limit each album to one image rather than returning all
        # its contents. Direct gallery URLs contain top-level media, which the
        # per_album limit does not affect.
        include_albums = bool(getattr(match, 'include_albums', False))
        return gdl.enumerate(match.url, platform=self.name,
                             max_items=self.scan_max_items,
                             max_albums=self.gallery_cap,
                             cookies=self._cookies(), extra_opts=extra,
                             per_album=None if include_albums else 1)


class PornpicsSource(_PhotoSiteSource):
    name = 'pornpics'
    platform_enum = Platform.PORNPICS
    # Leave gdl_opts unset: scan() computes --chapter-range from match.page.
    # Downloads use direct image URLs and therefore have no chapters.

    def scan(self, match):
        # Default listing scans read page thumbnails without gallery-dl.
        # Full-album scans, direct gallery URLs and failed cover parsing use
        # the inherited gallery-dl implementation.
        include_albums = bool(getattr(match, 'include_albums', False))
        if not include_albums and '/galleries/' not in urlparse(match.url).path:
            items, err = _covers_scan(match.url, max(0, getattr(match, 'page', 0) or 0))
            if items is not None:
                return items, err
        return super().scan(match)


registry.register(PornpicsSource())
