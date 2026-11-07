# app/scrape/sources/websearch.py
"""Keyword image search on the open web, without an API key or account.

The client builds a DuckDuckGo URL (?q=...&iax=images&kp=...) and posts it to
/api/scrape/scan, preserving the same URL-input contract as other sources.
This source extracts the keyword and queries ddgs, a metasearch library with
multiple backends, allowing degraded service when one backend fails.

Google and Bing image search APIs no longer accept new clients: Google Custom
Search ends on 2027-01-01, and Bing Search retired on 2025-08-11. Requiring
one of those keys would leave new installations without a working source."""
import logging
from urllib.parse import parse_qs, urlsplit

from .base import Source, Capabilities, Match
from . import gdl, registry

logger = logging.getLogger(__name__)

PLATFORM = 'websearch'
# Use the same per-page window as gallery-dl sources by importing the shared
# constant. A copied literal and a comment would not prevent silent drift.
MAX_RESULTS = gdl.DEFAULT_MAX_ITEMS
_HOSTS = frozenset({'duckduckgo.com', 'www.duckduckgo.com'})
_MISSING_DEP = ("Web image search needs the 'ddgs' package: "
                "install the web scraping dependencies in Setup.")


def _images(**kwargs):
    """Call the search library (the single test monkeypatch seam).
    Import lazily: the registry loads every source at startup, so a missing
    optional dependency must not prevent the application from starting."""
    from ddgs import DDGS
    return DDGS().images(**kwargs)


def _safe_https(value):
    """Return a credential-free HTTPS URL or None. Results can come from any
    site, so validate the URL structure here rather than restricting hosts."""
    if not isinstance(value, str) or not value.strip():
        return None
    trimmed = value.strip()
    try:
        parsed = urlsplit(trimmed)
    except ValueError:
        return None
    if (parsed.scheme != 'https' or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        return None
    return trimmed


def _safe_public_url(value):
    """Like _safe_https, but allow HTTP solely for thumbnail URLs.

    The full image downloaded during import remains HTTPS-only. Thumbnails use
    /api/scrape/thumb, whose server fetch already accepts public HTTP(S) URLs and
    serves them from our HTTPS origin without browser mixed content. Many sites
    still expose HTTP thumbnails alongside HTTPS originals; rejecting those
    would force full-image downloads across large result pages."""
    if not isinstance(value, str) or not value.strip():
        return None
    trimmed = value.strip()
    try:
        parsed = urlsplit(trimmed)
    except ValueError:
        return None
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        return None
    return trimmed


def _item(result):
    """Convert a ddgs result to the shared schema, or return None. image is the
    direct media downloaded during import; url is its source page for provenance."""
    if not isinstance(result, dict):
        return None
    image = _safe_https(result.get('image'))
    if not image:
        return None
    title = result.get('title')
    return {
        'url': image,
        'title': title.strip() if isinstance(title, str) else '',
        'thumbnail': _safe_public_url(result.get('thumbnail')) or image,
        'type': 'image',
        'platform': PLATFORM,
        'source_url': _safe_https(result.get('url')),
    }


class WebSearchSource(Source):
    name = 'websearch'
    priority = 100          # takes precedence over the universal fallback at 0
    paginated = True
    category = 'image'
    capabilities = Capabilities(media_kinds=frozenset({'image'}),
                                own_downloader=False, polite=True)

    def match(self, url):
        try:
            parsed = urlsplit(url or '')
        except ValueError:
            return None
        if (parsed.hostname or '').lower() not in _HOSTS:
            return None
        params = parse_qs(parsed.query)
        query = (params.get('q') or [''])[0].strip()
        if not query:
            return None
        m = Match(url=url)
        m.query = query
        # kp is DuckDuckGo's SafeSearch flag: '1' is strict, '-2' disables it
        # (our default). Keep it in the URL to preserve the scan request contract.
        m.safesearch = 'on' if (params.get('kp') or [''])[0] == '1' else 'off'
        return m

    def scan(self, match):
        page = max(0, int(getattr(match, 'page', 0) or 0))
        try:
            results = _images(query=match.query, safesearch=match.safesearch,
                              type_image='photo', max_results=MAX_RESULTS,
                              page=page + 1)
            if results is None:
                # Soft blocking, such as rate limits or filtering, may return None
                # instead of raising. Treating that as an empty list would hide the
                # failure behind a misleading "no results" message.
                return None, "Web image search returned no data (search may be blocked)."
            items = [item for item in (_item(r) for r in results) if item]
        except ImportError:
            return None, _MISSING_DEP
        except Exception as exc:
            # The library does not document its exceptions, but scan() never raises.
            # Report a 429 as a failure rather than "no results". results may be a lazy
            # iterator that performs I/O during iteration, so keep the comprehension
            # inside this try block to catch those failures too.
            logger.warning("websearch: search failed: %r", exc)
            return None, f"Web image search failed ({exc})."
        return items, None


registry.register(WebSearchSource())
