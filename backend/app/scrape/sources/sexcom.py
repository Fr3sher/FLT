# app/scrape/sources/sexcom.py
"""Sex.com source: adult pinboards with one image per pin, no albums.

Scans have two paths; search results return the image matching the keyword:

- SEARCH/TAG: /pics?search=<term>, /en/pics?search=..., /search/pics?query=...
  and /pics/<tag> use /portal/api/pictures/search, the site's infinite-scroll
  JSON API. It returns 40 pins per page and paging.numberOfPages. Each pin has
  uri and title; imagex1.sx.cdn.live serves the media without cookies. One HTTP
  request per page, no gallery-dl.
- PIN/BOARD/USER: /pin/<id>, /en/pics/<id> and /user/<x>/<board> use gallery-dl's
  native sexcom extractor. Each pin requires a page request, so use a short
  --range window to stay within the scan timeout.

GIFs and videos are outside raster-photo dataset imports. Their URLs receive
an explanatory message rather than an empty scan."""
from ...timeout_settings import network_timeout
import logging
from urllib.parse import parse_qsl, urlparse

from ..validators import Platform
from .base import Source, Capabilities, Match
from . import gdl
from . import registry

logger = logging.getLogger(__name__)

_API_URL = 'https://www.sex.com/portal/api/pictures/search'
_CDN_ROOT = 'https://imagex1.sx.cdn.live'
_PER_PAGE = 40            # API page size used by the site
_GDL_WINDOW = 12          # gallery-dl pins per page (one request per pin)

_SEXCOM_CAPS = Capabilities(
    can_enumerate_profile=True,
    polite=True,
    media_kinds=frozenset({'image'}),
    own_downloader=True,   # direct CDN media URLs; import downloads them itself
)

_MEDIA_TYPES = frozenset({'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'})
_CT_EXT = {'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
           'image/webp': '.webp', 'image/gif': '.gif'}


def _search_params_for(url):
    """Return photo search/tag JSON API parameters, otherwise None for gallery-dl.
    The fields are search, order and sexual-orientation. Return 'wrong-kind' for
    GIF/video searches so callers can explain the restriction. Pure; no network."""
    try:
        p = urlparse(url)
    except Exception:
        return None
    segs = [s for s in p.path.split('/') if s]
    if segs and len(segs[0]) == 2 and segs[0].isalpha():   # language prefix such as /en/
        segs = segs[1:]
    q = dict(parse_qsl(p.query))
    if 'query' in q:                                       # /search/pics?query=…
        q.setdefault('search', q.pop('query'))

    kind = None
    tag = ''
    if len(segs) >= 1 and segs[0] in ('pics', 'gifs', 'videos'):
        kind = segs[0]
        if len(segs) >= 2:
            tag = segs[1]
    elif len(segs) >= 2 and segs[0] == 'search' and segs[1] in ('pics', 'gifs', 'videos'):
        kind = segs[1]
    if kind is None:
        return None
    if tag and tag.isdigit():
        return None            # /pics/<id> is a pin detail page; use gallery-dl
    if kind != 'pics':
        return 'wrong-kind'    # dataset import accepts photos, not GIFs/videos
    search = (q.get('search') or tag.replace('-', ' ')).strip()
    if not search:
        return None            # generic listing without a keyword; use gallery-dl
    return {'search': search,
            'order': q.get('order') or 'likeCount',
            'sexual-orientation': q.get('sexual-orientation') or 'straight'}


def _search_json(params, page):
    """Fetch a JSON search API batch (test seam). Raises on failure."""
    from curl_cffi import requests as cf_requests
    r = cf_requests.get(_API_URL, params={**params, 'page': page, 'limit': _PER_PAGE},
                        impersonate='chrome', timeout=network_timeout(20),
                        headers={'Accept': 'application/json',
                                 'Referer': 'https://www.sex.com/'})
    r.raise_for_status()
    return r.json()


class SexcomSource(Source):
    name = 'sexcom'
    priority = 100
    capabilities = _SEXCOM_CAPS
    paginated = True
    category = 'image'

    def match(self, url):
        from ..validators import url_validator
        if url_validator.detect_platform(url) == Platform.SEXCOM:
            return Match(url=url, validation=None)
        return None

    def scan(self, match):
        try:
            page = max(0, getattr(match, 'page', 0) or 0)
            params = _search_params_for(match.url)
            if params == 'wrong-kind':
                return None, ('Sex.com: only PHOTO searches can be imported '
                              '(replace /gifs or /videos with /pics in the URL).')
            if params is None:
                # Pins, boards and users use gallery-dl: one request per pin,
                # with a short window to stay within the scan timeout.
                start = page * _GDL_WINDOW + 1
                return gdl.enumerate(match.url, platform=self.name,
                                     max_items=_GDL_WINDOW,
                                     image_range=f'{start}-{start + _GDL_WINDOW - 1}')

            data = _search_json(params, page + 1)          # API 1-based
            paging = data.get('paging') or {}
            if page + 1 > int(paging.get('numberOfPages') or 1):
                return [], None                            # end of listing
            items, seen = [], set()
            for pin in data.get('data') or []:
                uri = pin.get('uri')
                if not uri or not isinstance(uri, str):
                    continue
                url = _CDN_ROOT + uri
                if url in seen:
                    continue
                seen.add(url)
                items.append({'url': url,
                              'title': (pin.get('title') or '').strip()[:200],
                              'thumbnail': url, 'type': 'image', 'platform': 'sexcom'})
            return items, None
        except Exception as e:   # safety net: scan() never raises
            logger.warning('sexcom scan failed: %s', e)
            return None, f'Sex.com: scan failed ({e}).'

    def download(self, url, dest_base):
        """Download a CDN image directly with a hardened fetch.
        Concept import downloads URLs itself through _download_scrape_item;
        this method honors the Source contract for other callers."""
        import os
        from ..netfetch import MAX_DRIVER_BYTES, fetch_hardened_bytes
        ok, data, ctype, reason = fetch_hardened_bytes(
            url, allowed_types=_MEDIA_TYPES, max_bytes=MAX_DRIVER_BYTES)
        if not ok or not data:
            return False, None, f'Sex.com: download failed ({reason}).'
        ct = (ctype or '').split(';', 1)[0].strip().lower()
        ext = _CT_EXT.get(ct) or (os.path.splitext(urlparse(url).path)[1].lower() or '.jpg')
        dest_dir = os.path.dirname(dest_base)
        filename = os.path.basename(dest_base) + ext
        try:
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(dest_dir, filename), 'wb') as f:
                f.write(data)
        except OSError as e:
            return False, None, f"Sex.com: write error ({e})."
        return True, filename, None


registry.register(SexcomSource())
