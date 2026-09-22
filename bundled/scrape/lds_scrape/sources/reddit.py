# app/scrape/sources/reddit.py
"""Reddit source: keyword searches, subreddits and posts through OAuth.

Since Reddit's 2023 API restrictions, anonymous browsing/search JSON
endpoints and gallery-dl's extractor encounter an anti-bot 403 page.
oauth.reddit.com accepts an anonymous installed_client token using
gallery-dl's public client ID, without an account or registered app.
Query OAuth directly and extract gallery/direct i.redd.it/preview images
from post JSON.

_endpoint_for accepts global /search/?q= searches, subreddit-scoped
/r/<sub>/search/?q= searches with restrict_sr, /r/<sub>[/<sort>] listings,
/user/<name> posts, /r/<sub>/comments/<id>/ posts including galleries,
/r/<sub>/s/<token> mobile share redirects and direct i.redd.it images.

The frontend turns keywords into Reddit search URLs for the ordinary
/scan pipeline; no dedicated route is needed. Token/API requests contact
Reddit hosts only. Image imports use hardened fetching, SSRF checks
and magic-byte validation."""
import logging
import os
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from ..validators import Platform
from .base import Source, Capabilities, Match, ResultList
from .gdl_source import resolve_cookies
from . import registry

logger = logging.getLogger(__name__)

_API_BASE = 'https://oauth.reddit.com'
_TOKEN_URL = 'https://www.reddit.com/api/v1/access_token'
# Descriptive User-Agent, as required by Reddit API rules.
_UA = 'LoRA-Dataset-Studio/1.0 (+https://github.com/perfectgf/lora-dataset-studio)'
# gallery-dl's public installed_client ID enables anonymous device_id
# grants without an account or registered app. Users can override it via
# Settings > Scraping & sources (REDDIT_CLIENT_ID in os.environ) or
# <SCRAPE_COOKIES_DIR>/reddit_client_id.txt when the shared ID is rate-limited.
_GDL_CLIENT_ID = '6N9uN0krSDE-ig'

_HTTP_TIMEOUT = 20
_MAX_429_RETRY_WAIT = 4    # Retry 429 only once, and only when reset is near.
_BATCH_POSTS = 30          # Posts per listing request; each post produces about 1-N images.
_SCAN_MAX = 200            # Items per scan page, keeping payloads bounded.
# Hard cap on sequential listing calls per _walk_items, including both
# skipping and collection. Deep pages in text-heavy subreddits could
# otherwise issue hundreds of requests just to skip already-delivered
# items. Comparable to the old worst case of 51 calls, preserving common
# cases while bounding pathological ones. Mark partial if the budget
# expires before filling the page or exhausting the listing.
#
# The old design also replayed from after=None, so replay is not new
# debt. Cost per item is similar for sparse images and better for gallery
# subreddits, where this design returns 200 rather than 30 items.
_MAX_LISTING_CALLS = 60
_SORTS = frozenset({'hot', 'new', 'top', 'rising', 'controversial', 'best'})
_IMG_EXT = ('.jpg', '.jpeg', '.png', '.webp', '.gif')

# Process-memory token cache (about 24 hours, refreshed before expiry).
# cid identifies the issuing client ID. Settings changes os.environ
# without restart; a changed ID must mint a new token rather than
# continue consuming the old client's quota.
_token_cache = {'value': None, 'exp': 0.0, 'cid': None}

_REDDIT_CAPS = Capabilities(
    can_enumerate_profile=True,
    polite=True,
    media_kinds=frozenset({'image'}),
    own_downloader=True,   # Dedicated hardened downloader; concept imports actually
)                          # download URLs directly through their separate import flow.

# Content types served by Reddit image CDNs, used by download().
_MEDIA_TYPES = frozenset({'image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'})
_CT_EXT = {'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
           'image/webp': '.webp', 'image/gif': '.gif'}


# URL canonicalization: resolve /s/ and redd.it redirects, strip tracking.
_DROP_PARAMS = ('share_id', 'correlation_id', 'ref', 'ref_source', 'rdt')


def _is_reddit_host(host: str) -> bool:
    return host == 'reddit.com' or host.endswith('.reddit.com')


def _canonical_reddit_url(url: str) -> str:
    """Canonicalize Reddit URLs: resolve /s/ and redd.it redirects on Reddit
    hosts only, force www.reddit.com, strip sharing/tracking parameters
    while keeping content parameters such as t=month and q. Leave non-Reddit
    and direct CDN URLs unchanged. Never raises."""
    try:
        p = urlparse(url)
    except Exception:
        return url
    host = (p.hostname or '').lower()
    is_shortener = host in ('redd.it', 'www.redd.it')   # Exclude i./preview.redd.it CDN URLs.
    if not (_is_reddit_host(host) or is_shortener):
        return url
    if is_shortener or '/s/' in p.path:
        try:
            r = requests.get(url, headers={'User-Agent': _UA}, timeout=10,
                             allow_redirects=True)
            tgt = urlparse(r.url)
            if _is_reddit_host((tgt.hostname or '').lower()):  # anti-redirection exotique
                p = tgt
        except requests.RequestException as e:
            logger.warning('reddit share-link resolve failed (%s) — trying as-is', e)
    keep = [(k, v) for k, v in parse_qsl(p.query)
            if not k.lower().startswith('utm_') and k.lower() not in _DROP_PARAMS]
    return urlunparse(('https', 'www.reddit.com', p.path, '', urlencode(keep), ''))


# Canonical Reddit URL -> OAuth endpoint (pure, testable without networking).
def _endpoint_for(url: str):
    """Map canonical Reddit URL to {api_path, params, kind}, with kind
    listing/post/direct. Return None for unsupported shapes. Direct results
    also carry the CDN URL to return unchanged."""
    try:
        p = urlparse(url)
    except Exception:
        return None
    host = (p.hostname or '').lower()

    # Direct i.redd.it/preview.redd.it or image-extension URLs become one
    # item without an API call.
    if host in ('i.redd.it', 'preview.redd.it', 'external-preview.redd.it') \
            or p.path.lower().endswith(_IMG_EXT):
        return {'api_path': None, 'params': {}, 'kind': 'direct', 'url': url}

    segs = [s for s in p.path.split('/') if s]
    q = dict(parse_qsl(p.query))

    # Post seul (galerie incluse) : /r/<sub>/comments/<id>/… ou /comments/<id>.
    if 'comments' in segs:
        i = segs.index('comments')
        if i + 1 < len(segs):
            return {'api_path': f'/comments/{segs[i + 1]}',
                    'params': {'limit': 1, 'raw_json': 1}, 'kind': 'post'}

    # Global /search or subreddit-scoped /r/<sub>/search.
    is_global_search = segs and segs[-1] == 'search' and not (segs[0] == 'r')
    is_sub_search = len(segs) >= 3 and segs[0] == 'r' and segs[2] == 'search'
    if is_global_search or is_sub_search:
        params = {
            'q': q.get('q', ''),
            'sort': q.get('sort', 'top'),
            't': q.get('t', 'all'),
            'type': 'link',
            'raw_json': 1,
            'include_over_18': 'on',
        }
        if is_sub_search:
            return {'api_path': f'/r/{segs[1]}/search',
                    'params': {**params, 'restrict_sr': 1}, 'kind': 'listing'}
        return {'api_path': '/search', 'params': params, 'kind': 'listing'}

    # User posts: /user/<name> or /u/<name>.
    if len(segs) >= 2 and segs[0] in ('user', 'u'):
        return {'api_path': f'/user/{segs[1]}/submitted',
                'params': {'sort': q.get('sort', 'top'), 't': q.get('t', 'all'),
                           'raw_json': 1}, 'kind': 'listing'}

    # Listing subreddit : /r/<sub> ou /r/<sub>/<tri>.
    if len(segs) >= 2 and segs[0] == 'r':
        sub = segs[1]
        sort = segs[2] if len(segs) >= 3 and segs[2] in _SORTS else 'hot'
        return {'api_path': f'/r/{sub}/{sort}',
                'params': {'t': q.get('t', 'all'), 'raw_json': 1}, 'kind': 'listing'}

    return None


# Extract post images (pure, testable with JSON fixtures).
def _pick_preview(entries, url_key, size_key, fallback):
    """Choose a preview at least about 320 pixels wide for a lightweight grid,
    otherwise the largest available or fallback. entries uses media_metadata
    p dictionaries (u/x/y) or preview resolutions (url/width)."""
    if isinstance(entries, list) and entries:
        for e in entries:
            if e.get(size_key, 0) >= 320 and e.get(url_key):
                return e[url_key]
        if entries[-1].get(url_key):
            return entries[-1][url_key]
    return fallback


def _is_image_url(u: str) -> bool:
    try:
        return urlparse(u).path.lower().endswith(_IMG_EXT)
    except Exception:
        return False


def _items_from_post(p: dict) -> list:
    """Extract direct post images into {url, title, thumbnail, type, platform,
    subreddit}. Return [] when the post has no images."""
    title = (p.get('title') or '')[:200]
    sub = p.get('subreddit') or ''

    def item(u, thumb):
        return {'url': u, 'title': title, 'thumbnail': thumb or u,
                'type': 'image', 'platform': 'reddit', 'subreddit': sub}

    # 1. Galleries: gallery_data orders media IDs; media_metadata holds URLs.
    if p.get('is_gallery') and isinstance(p.get('media_metadata'), dict):
        gd = ((p.get('gallery_data') or {}).get('items')) or []
        order = [it.get('media_id') for it in gd if it.get('media_id')] \
            or list(p['media_metadata'].keys())
        out = []
        for mid in order:
            meta = p['media_metadata'].get(mid) or {}
            if meta.get('e') != 'Image':
                continue
            full = (meta.get('s') or {}).get('u')
            if full:
                out.append(item(full, _pick_preview(meta.get('p'), 'u', 'x', full)))
        if out:
            return out

    # 2. Lien image direct (i.redd.it, imgur single…).
    u = p.get('url_overridden_by_dest') or p.get('url') or ''
    prev = ((p.get('preview') or {}).get('images') or [])
    thumb = _pick_preview(prev[0].get('resolutions'), 'url', 'width', None) if prev else None
    if _is_image_url(u):
        return [item(u, thumb or u)]

    # 3. Fallback: Reddit preview, including thumbnails of external links.
    if prev:
        src = (prev[0].get('source') or {}).get('url')
        if src:
            return [item(src, thumb or src)]
    return []


# OAuth API: anonymous token plus authenticated GET.
def _client_id() -> str:
    """Reddit client ID precedence: environment (including Settings), admin
    file, then gallery-dl's public client ID."""
    env = (os.environ.get('REDDIT_CLIENT_ID') or '').strip()
    if env:
        return env
    path = resolve_cookies('reddit_client_id')   # <SCRAPE_COOKIES_DIR>/reddit_client_id.txt
    if path:
        try:
            val = open(path, encoding='utf-8').read().strip()
            if val:
                return val
        except OSError:
            pass
    return _GDL_CLIENT_ID


def _get_token():
    """Anonymous installed_client OAuth token, cached until about two minutes
    before expiry. Mint again if the client ID changed because tokens use
    the issuing client's quota. Return None on network/auth failure; never raises."""
    now = time.time()
    cid = _client_id()
    if _token_cache['value'] and now < _token_cache['exp'] and _token_cache['cid'] == cid:
        return _token_cache['value']
    try:
        r = requests.post(
            _TOKEN_URL,
            data={'grant_type': 'https://oauth.reddit.com/grants/installed_client',
                  'device_id': 'DO_NOT_TRACK_THIS_DEVICE'},
            auth=(cid, ''), headers={'User-Agent': _UA}, timeout=15)
        r.raise_for_status()
        j = r.json()
    except (requests.RequestException, ValueError) as e:
        logger.warning('reddit token request failed: %s', e)
        return None
    tok = j.get('access_token')
    if tok:
        _token_cache['value'] = tok
        _token_cache['exp'] = now + max(60, int(j.get('expires_in', 3600)) - 120)
        _token_cache['cid'] = cid
    return tok


class RedditRateLimited(Exception):
    """Reddit 429: temporary quota exhaustion (about 1000 requests/10 minutes
    per IP and client). Carries reset seconds if known for actionable errors."""
    def __init__(self, reset_seconds=None):
        self.reset_seconds = reset_seconds
        super().__init__('reddit rate limited')


def _reset_seconds(resp):
    """Quota reset seconds from Retry-After, otherwise x-ratelimit-reset.
    Return None if unreadable."""
    for key in ('retry-after', 'x-ratelimit-reset'):
        val = resp.headers.get(key)
        if val:
            try:
                return max(0, int(float(val)))
            except (TypeError, ValueError):
                pass
    return None


def _api_get(api_path: str, params: dict, token: str) -> dict:
    """Authenticated GET to oauth.reddit.com. Raise HTTPError/RequestException,
    caught by scan. Refresh once on 401 for an expired token; retry 429 once
    only when reset is within _MAX_429_RETRY_WAIT. Otherwise raise
    RedditRateLimited for an actionable scan error."""
    def _do(tok):
        return requests.get(_API_BASE + api_path, params=params,
                            headers={'User-Agent': _UA, 'Authorization': f'Bearer {tok}'},
                            timeout=_HTTP_TIMEOUT)
    r = _do(token)
    if r.status_code == 401:
        _token_cache['exp'] = 0.0            # force refresh
        tok2 = _get_token()
        if tok2:
            r = _do(tok2)
    if r.status_code == 429:
        wait = _reset_seconds(r)
        if wait is not None and wait <= _MAX_429_RETRY_WAIT:  # blip transitoire → 1 retry
            time.sleep(wait + 1)
            r = _do(_token_cache['value'] or token)
        if r.status_code == 429:
            raise RedditRateLimited(_reset_seconds(r))
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# La source
# ---------------------------------------------------------------------------
class RedditSource(Source):
    name = 'reddit'
    priority = 100
    capabilities = _REDDIT_CAPS
    # Load more uses _walk_items: page N resumes at item N*_SCAN_MAX in the
    # replayed listing, never a fixed after cursor tied to a post batch.
    # _MAX_LISTING_CALLS bounds each request.
    paginated = True
    category = 'image'        # recherche d'images → ouvert aux non-admins

    def match(self, url):
        from ..validators import url_validator
        if url_validator.detect_platform(url) == Platform.REDDIT:
            return Match(url=url, validation=None)
        return None

    def _walk_items(self, ep, token, skip, limit):
        """Walk the cursor-paginated listing from the start, convert posts as they
        arrive and deduplicate URLs across the full stream. Skip previously
        delivered items, then collect at most limit.

        Skipping must happen per item, not post/batch: one gallery can contain
        about 20 images and 30 posts can exceed the limit. The old post-batch
        cap discarded the rest when the next page advanced after. Replaying
        the ordered stream and skipping items resumes exactly where the cap
        cut, even inside a gallery.

        Return (items, exhausted, budget_hit). exhausted means no cursor remains
        after the last batch; no next page is useful. budget_hit means the call
        cap was reached before limit or exhaustion; items are valid but this
        page may be incomplete. The caller sets ResultList.partial."""
        after = None
        seen = set()
        skipped = 0
        items = []
        for _ in range(_MAX_LISTING_CALLS):
            params = dict(ep['params'])
            params['limit'] = _BATCH_POSTS
            if after:
                params['after'] = after
            listing = (_api_get(ep['api_path'], params, token) or {}).get('data', {})
            children = listing.get('children', []) or []
            after = listing.get('after')
            for ch in children:
                data = ch.get('data') if isinstance(ch, dict) else None
                if not isinstance(data, dict):
                    continue
                for it in _items_from_post(data):
                    if it['url'] in seen:
                        continue
                    seen.add(it['url'])
                    if skipped < skip:
                        skipped += 1
                        continue
                    items.append(it)
                    if len(items) >= limit:
                        # Return at limit without checking after. A page ending exactly at the
                        # limit can therefore leave Load more active for one empty request.
                        # Deliberate: hiding remaining items would be worse, and avoiding that
                        # requires an extra lookahead API call on every successful page.
                        return items, False, False
            if not after:
                return items, True, False   # Listing exhausted: nothing more to load.
        return items, False, True           # Call budget exhausted; page may be incomplete.

    def _fetch_post(self, ep, token):
        """Fetch one post: /comments/<id> returns [postListing, commentsListing].
        Use the first child of the first listing."""
        data = _api_get(ep['api_path'], ep['params'], token)
        if isinstance(data, list) and data:
            return (data[0].get('data', {}) or {}).get('children', []) or []
        return []

    def scan(self, match):
        try:
            url = _canonical_reddit_url(match.url)
            ep = _endpoint_for(url)
            if not ep:
                return None, ('Reddit: unrecognized URL (subreddit, search, '
                              'post or share link expected).')
            if ep['kind'] == 'direct':
                return [{'url': ep['url'], 'title': '', 'thumbnail': ep['url'],
                         'type': 'image', 'platform': 'reddit'}], None
            if ep['kind'] == 'listing' and 'q' in ep['params'] and not ep['params']['q'].strip():
                return None, 'Reddit: missing search keyword.'

            token = _get_token()
            if not token:
                return None, 'Reddit: API authentication failed (try again).'

            if ep['kind'] == 'post':
                children = self._fetch_post(ep, token)
                items, seen = [], set()
                for ch in children:
                    data = ch.get('data') if isinstance(ch, dict) else None
                    if not isinstance(data, dict):
                        continue
                    for it in _items_from_post(data):
                        if it['url'] not in seen:
                            seen.add(it['url'])
                            items.append(it)
                            if len(items) >= _SCAN_MAX:
                                # Single posts are bounded by Reddit's gallery limit of at most 20
                                # images, well below _SCAN_MAX. Retain this guard for a consistent
                                # bounded-payload contract.
                                break
                return items, None

            # Listing page indexes _SCAN_MAX-sized item windows, not post batches.
            # _walk_items explains exact continuation, including within galleries.
            page = max(0, getattr(match, 'page', 0) or 0)
            items, exhausted, budget_hit = self._walk_items(ep, token, page * _SCAN_MAX, _SCAN_MAX)
            if exhausted:
                match.paginated = False   # Nothing more to load: hide Load more.
            elif budget_hit and len(items) < _SCAN_MAX:
                # Call budget expired before filling the page. A deeper page would
                # skip more against the same budget and cannot do better, so Load more
                # would guarantee an empty click at full API cost. Keep partial for
                # the warning banner; hide only the button.
                match.paginated = False
            result = ResultList(items)
            result.partial = budget_hit
            return result, None
        except RedditRateLimited as e:
            wait = f' Try again in ~{e.reset_seconds}s.' if e.reset_seconds else ' Try again in a minute.'
            return None, ('Reddit is temporarily rate-limiting requests (shared quota '
                          '~1000 requests / 10 min).' + wait)
        except requests.RequestException as e:
            return None, f'Reddit: network error ({e}).'
        except Exception as e:   # Defensive guard: scan() never raises.
            logger.exception('reddit scan')
            return None, f'Reddit: unexpected error ({e}).'

    def download(self, url, dest_base):
        """Download a Reddit image directly with hardened fetch. Concept imports
        actually fetch URLs themselves through _download_scrape_item; this
        method honors the Source contract for other callers."""
        from lds_sdk.netfetch import MAX_DRIVER_BYTES, fetch_hardened_bytes
        ok, data, ctype, reason = fetch_hardened_bytes(
            url, allowed_types=_MEDIA_TYPES, max_bytes=MAX_DRIVER_BYTES)
        if not ok or not data:
            return False, None, f'Reddit: download failed ({reason}).'
        ct = (ctype or '').split(';', 1)[0].strip().lower()
        ext = _CT_EXT.get(ct) or (os.path.splitext(urlparse(url).path)[1].lower() or '.jpg')
        dest_dir = os.path.dirname(dest_base)
        filename = os.path.basename(dest_base) + ext
        try:
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(dest_dir, filename), 'wb') as f:
                f.write(data)
        except OSError as e:
            return False, None, f"Reddit: write error ({e})."
        return True, filename, None


registry.register(RedditSource())
