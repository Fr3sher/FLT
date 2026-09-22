# app/scrape/sources/image_sites.py
"""PornPics category-image source for real photos, excluding drawing/anime boorus.

Category/tag/search listings support two modes. Covers (default) returns
the representative thumbnail displayed for each gallery, not necessarily
its first image. Page zero parses HTML; later pages use the site's AJAX
offset/limit endpoint with g_url, t_url_460 and desc. Replace /460/ with
/1280/ for full resolution. This needs one HTTP request per page and no
gallery-dl. Scan full albums uses gallery-dl to enumerate galleries and
then each complete album.

A direct /galleries/ URL always returns the whole album. If cover parsing
fails after a layout change or missing curl_cffi, fall back to gallery-dl
limited to one image per album.

Realbooru/ImageFap were removed for quality/security concerns at the user's
request on 2026-06-27. Motherless was removed earlier because DNS failed."""
from ...timeout_settings import network_timeout
import logging
import re
from urllib.parse import urlparse

from ..validators import Platform
from .base import Capabilities
from .gdl_source import GalleryDlSource
from . import gdl
from . import registry

logger = logging.getLogger(__name__)

# Public content without authentication; images and GIF/video with polite
# limits for large listings. gallery-dl provides downloads (own_downloader).
_PHOTO_CAPS = Capabilities(
    can_enumerate_profile=True,
    polite=True,
    media_kinds=frozenset({'image', 'video'}),
    own_downloader=True,
)

# Scan item cap exceeds gdl's default 120 because full-album mode traverses
# multiple galleries, not just the first. gallery-dl auto-paginates and
# --range 1-N limits the total; metadata-only simulations remain fast.
# Default covers mode is effectively limited to gallery_cap covers per page.
_PHOTO_SCAN_MAX = 400


# Galleries per Load more batch. Category/tag/search pages queue chapters
# (Message.Queue), which --range does not bound: use --chapter-range.
# Otherwise gallery-dl scans hundreds of pages and times out before media
# arrives. Align with gdl.DEFAULT_MAX_ALBUMS; recursion then bounds images
# within each gallery using --range.
_GALLERY_CAP = 8


# --- Covers mode: parse the listing (HTML page 0, then AJAX) -----------------
_COVERS_PER_PAGE = 20     # Site page size (both grid AND AJAX endpoint)

# Listing tile: gallery link followed by a lazy thumbnail. Accept both
# single and double quotes used by different pages; bounded windows must
# never cross into the next tile.
_TILE_RE = re.compile(
    r"class=[\"']rel-link[\"']\s+href=[\"'](?P<href>[^\"']+)[\"']"
    r".{0,600}?data-src=[\"'](?P<thumb>[^\"']+)[\"']"
    r"(?:.{0,300}?\salt=[\"'](?P<alt>[^\"']*)[\"'])?",
    re.S)
_SIZE_SEG_RE = re.compile(r'/(?:300|460)/')


def _full_size(thumb_url):
    """Full-resolution CDN thumbnail URL: replace /300/ or /460/ with /1280/.
    Same image/hash; gallery pages link originals through /1280/."""
    return _SIZE_SEG_RE.sub('/1280/', thumb_url, count=1)


def _listing_html(url):
    """Listing-page HTML (test seam). Raise on network/HTTP failure."""
    from curl_cffi import requests as cf_requests
    r = cf_requests.get(url, impersonate='chrome', timeout=network_timeout(20))
    r.raise_for_status()
    return r.text


def _listing_json(url, offset):
    """Listing AJAX JSON batch (test seam). Offset zero does not return JSON,
    so page zero uses HTML. Raise on failure."""
    from curl_cffi import requests as cf_requests
    r = cf_requests.get(url, params={'limit': _COVERS_PER_PAGE, 'offset': offset},
                        impersonate='chrome', timeout=network_timeout(20),
                        headers={'Accept': 'application/json, text/javascript, */*; q=0.01',
                                 'Referer': url,
                                 'X-Requested-With': 'XMLHttpRequest'})
    r.raise_for_status()
    return r.json()


def _covers_scan(url, page):
    """Listing thumbnails as displayed. Return (items, None), ([], None) when
    pagination ends, or (None, None) to request gallery-dl fallback after
    empty parsing, network failure or missing curl_cffi. Never raises."""
    def item(full, thumb, title):
        return {'url': full, 'title': (title or '')[:200], 'thumbnail': thumb,
                'type': 'image', 'platform': 'pornpics'}
    try:
        items = []
        if page <= 0:
            for m in _TILE_RE.finditer(_listing_html(url)):
                href, thumb = m.group('href'), m.group('thumb')
                if '/galleries/' not in href:      # tile outside the grid (navigation, ads…)
                    continue
                items.append(item(_full_size(thumb), thumb, m.group('alt')))
            return (items, None) if items else (None, None)   # Empty parsing suggests a changed layout: use fallback.
        data = _listing_json(url, offset=page * _COVERS_PER_PAGE)
        if not isinstance(data, list):
            return None, None
        for g in data:
            thumb = g.get('t_url_460') or g.get('t_url')
            if thumb:
                items.append(item(_full_size(thumb), thumb, g.get('desc')))
        return items, None      # An empty list is legitimate here: the listing has ended.
    except Exception as e:
        logger.warning('pornpics covers scan failed (%s) — falling back to gallery-dl', e)
        return None, None


class _PhotoSiteSource(GalleryDlSource):
    priority = 100
    capabilities = _PHOTO_CAPS
    scan_max_items = _PHOTO_SCAN_MAX
    gallery_cap = _GALLERY_CAP
    paginated = True   # Load more: each page is the next gallery batch.
    category = 'image'  # galeries photo → ouvert aux non-admins

    def scan(self, match):
        # Gallery window for zero-based match.page set by /scan: page zero is
        # 1-cap, page one cap+1 through 2*cap. --chapter-range bounds galleries
        # to avoid timeout; raised max_items bounds images within each gallery
        # instead of the default gdl cap of 120.
        page = max(0, getattr(match, 'page', 0) or 0)
        start = page * self.gallery_cap + 1
        end = (page + 1) * self.gallery_cap
        extra = ['--chapter-range', f'{start}-{end}']
        if self.gdl_opts:
            extra = list(self.gdl_opts) + extra
        # include_albums=False uses the cover fallback; normal covers use
        # _covers_scan. Limit to one image per album rather than flooding full
        # albums. Direct gallery URLs are unaffected: per_album only bounds
        # type-6 recursion, not top-level media.
        include_albums = bool(getattr(match, 'include_albums', False))
        return gdl.enumerate(match.url, platform=self.name,
                             max_items=self.scan_max_items,
                             max_albums=self.gallery_cap,
                             cookies=self._cookies(), extra_opts=extra,
                             per_album=None if include_albums else 1)


class PornpicsSource(_PhotoSiteSource):
    name = 'pornpics'
    platform_enum = Platform.PORNPICS
    # Leave gdl_opts=None: scan computes --chapter-range from match.page.
    # Downloads operate on direct image URLs, without chapters.

    def scan(self, match):
        # Default listing covers use page thumbnails without gallery-dl. Full
        # albums, direct gallery URLs or failed cover parsing use inherited
        # _PhotoSiteSource.scan.
        include_albums = bool(getattr(match, 'include_albums', False))
        if not include_albums and '/galleries/' not in urlparse(match.url).path:
            items, err = _covers_scan(match.url, max(0, getattr(match, 'page', 0) or 0))
            if items is not None:
                return items, err
        return super().scan(match)


registry.register(PornpicsSource())
