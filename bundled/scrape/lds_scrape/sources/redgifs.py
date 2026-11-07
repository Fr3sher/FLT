# app/scrape/sources/redgifs.py
"""RedGifs profile/niche/video enumeration.

Standalone requests-based port of redgifs_downloader/api/redgifs.py
without the source config/settings. Enumerates videos and thumbnails
only; actual downloads use yt-dlp's RedGifs extractor through
/api/scrape/download, so return watch/<id> URLs.
Only the fixed public api.redgifs.com host is contacted."""
import logging
import threading

import requests

from ..validators import URLType
from .base import ResultList

logger = logging.getLogger(__name__)


class RedGifsAbort(Exception):
    """Raised when _iter_paged stops on HTTP 429/403/5xx, timeout or an
    unrecovered 401 rather than normal page exhaustion. Without this
    signal, scan cannot distinguish an empty profile/niche from a rejected
    page; silently returning used to turn rate limits and server errors
    into legitimate empty results."""

REDGIFS_API_BASE = "https://api.redgifs.com/v2"
REDGIFS_AUTH_URL = f"{REDGIFS_API_BASE}/auth/temporary"
# Fixed User-Agent: temporary JWTs are bound to the authentication request's UA.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
TIMEOUT = 30
MAX_PAGES = 10
MAX_ITEMS = 100


class RedGifsClient:
    """Minimal RedGifs API client: temporary token and enumeration."""

    def __init__(self):
        self._token = None
        self._lock = threading.Lock()
        self._session = requests.Session()

    def _headers(self, video_id=None, auth=True):
        h = {
            "Accept": "application/json, text/plain, */*",
            "User-Agent": USER_AGENT,
            "Referer": "https://www.redgifs.com/",
            "Origin": "https://www.redgifs.com",
            "Content-Type": "application/json",
        }
        if video_id:
            # x-customheader is required for /gifs/{id}; otherwise 401 despite the token.
            h["x-customheader"] = f"https://www.redgifs.com/watch/{video_id}"
        if auth and self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def get_token(self):
        with self._lock:
            if self._token:
                return self._token
        try:
            r = self._session.get(REDGIFS_AUTH_URL, headers=self._headers(auth=False), timeout=TIMEOUT)
            r.raise_for_status()
            token = (r.json() or {}).get('token')
        except Exception as e:
            logger.warning(f"[redgifs] failed to obtain token: {e}")
            return None
        if token:
            with self._lock:
                self._token = token
            return token
        return None

    def _reset_token(self):
        with self._lock:
            self._token = None

    def _get(self, url, video_id=None):
        """Authenticated GET returning JSON. Raise HTTPError for non-2xx status."""
        r = self._session.get(url, headers=self._headers(video_id=video_id), timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()

    def get_single_video(self, video_id):
        url = f"{REDGIFS_API_BASE}/gifs/{video_id}"
        try:
            data = self._get(url, video_id=video_id)
        except requests.HTTPError as e:
            if getattr(e.response, 'status_code', None) == 401:
                self._reset_token()
                if self.get_token():
                    try:
                        data = self._get(url, video_id=video_id)
                    except Exception:
                        return None
                else:
                    return None
            else:
                return None
        except Exception:
            return None
        return (data or {}).get('gif')

    def _iter_paged(self, url_for_page, state=None):
        """Iterate with a page-to-URL function, refreshing tokens on 401.

        Normal exhaustion (empty page or final page) returns without error.
        Rejected pages raise RedGifsAbort so callers can distinguish completion
        from interruption.

        If MAX_PAGES expires while page < total_pages, set optional caller-owned
        state['capped']=True before ending. Otherwise this time guard would
        silently truncate, like the MAX_ITEMS issue in _consume_paged."""
        page = 1
        token_retries = 0
        while page <= MAX_PAGES:
            url = url_for_page(page)
            try:
                data = self._get(url)
            except requests.HTTPError as e:
                status = getattr(e.response, 'status_code', None)
                if status == 401 and token_retries < 2:
                    token_retries += 1
                    self._reset_token()
                    if self.get_token():
                        continue  # Retry the same page.
                    raise RedGifsAbort("RedGifs: token refresh failed after 401.") from e
                raise RedGifsAbort(f"RedGifs: HTTP {status}.") from e
            except Exception as e:
                raise RedGifsAbort(f"RedGifs: {e}") from e

            gifs = (data or {}).get('gifs') or []
            if not gifs:
                return
            for gif in gifs:
                yield gif

            total_pages = (data or {}).get('pages', 1) or 1
            if page >= total_pages:
                return
            page += 1
        # The while loop exhausted MAX_PAGES rather than returning above.
        # page never reached total_pages, so pages remain.
        if state is not None:
            state['capped'] = True

    def iter_user(self, username, state=None):
        return self._iter_paged(
            lambda p: f"{REDGIFS_API_BASE}/users/{username}/search?order=new&page={p}",
            state=state)

    def iter_niche(self, niche, state=None):
        return self._iter_paged(
            lambda p: f"{REDGIFS_API_BASE}/niches/{niche}/gifs?page={p}",
            state=state)


# Shared instance for this single-user, admin-only feature.
client = RedGifsClient()


def _item_from_gif(gif):
    gid = gif.get('id', '') or ''
    urls = gif.get('urls', {}) or {}
    return {
        'url': f"https://www.redgifs.com/watch/{gid}",
        'title': gid or 'redgif',
        'thumbnail': urls.get('thumbnail') or urls.get('poster'),
        'type': 'video',
        'platform': 'redgifs',
        'duration': gif.get('duration', 0),
    }


def _consume_paged(gen, items, state=None):
    """Drain _iter_paged into items, bounded by MAX_ITEMS.

    Return True for any truncation: RedGifsAbort, the item cap before normal
    exhaustion, or state['capped'] from the page cap. At the item cap we
    cannot know whether the profile ended exactly there, so report partial
    conservatively, as Picazor does. Return False only on clean exhaustion
    without any of those signals."""
    try:
        for gif in gen:
            items.append(_item_from_gif(gif))
            if len(items) >= MAX_ITEMS:
                return True
    except RedGifsAbort:
        return True
    return bool(state.get('capped')) if state is not None else False


def scan(validation):
    """Enumerate RedGifs URL media; return (items, error).

    validation is ValidationResult with PROFILE/NICHE/VIDEO and a
    username/niche/id value. Bound to MAX_ITEMS; never raises."""
    try:
        if not client.get_token():
            return None, "RedGifs: could not obtain a token (Cloudflare / rate-limit?)."

        ut = validation.url_type
        value = validation.value
        items = []
        state = {}

        if ut == URLType.PROFILE:
            truncated = _consume_paged(client.iter_user(value, state=state), items, state)
        elif ut == URLType.NICHE:
            truncated = _consume_paged(client.iter_niche(value, state=state), items, state)
        elif ut == URLType.VIDEO:
            gif = client.get_single_video(value)
            if not gif:
                return None, "RedGifs video not found (or token expired)."
            items.append(_item_from_gif(gif))
            return items, None
        else:
            return None, "Unsupported RedGifs URL type."

        if truncated:
            if items:
                # Items collected before a rejected page or item/page cap form a partial
                # result, not a failure. Reuse base.ResultList.partial so routes/scrape.py
                # can inspect it without source-specific changes. Previously a 429 on
                # page two, or a cap without network failure, silently appeared complete.
                result = ResultList(items[:MAX_ITEMS])
                result.partial = True
                return result, None
            # Zero items plus truncation can only be RedGifsAbort here: the item
            # cap and capped state require prior media. This is a real blocking/
            # rate-limit failure, not an empty profile that should return HTTP 200.
            return None, "RedGifs: rate-limited or blocked while listing (try again shortly)."

        # Empty PROFILE/NICHE after clean exhaustion means the account/niche has
        # no public videos: a valid empty result like GdlError empty, not a tool
        # failure/502. VIDEO remains a real error in its dedicated branch above.
        return items, None
    except Exception as e:  # garde-fou : ne jamais propager
        logger.warning(f"[redgifs] scan error: {e}")
        return None, "RedGifs scan error."


from .base import Source, Capabilities, Match
from . import registry


class RedgifsSource(Source):
    name = 'redgifs'
    priority = 100
    capabilities = Capabilities(can_enumerate_profile=True, own_downloader=False)

    def match(self, url):
        from ..validators import url_validator, Platform
        result = url_validator.validate_url(url)
        if result.is_valid and result.platform == Platform.REDGIFS:
            return Match(url=url, validation=result)
        return None

    def scan(self, match):
        return scan(match.validation)   # Delegate to the existing scan(validation).


registry.register(RedgifsSource())
