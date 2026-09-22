# app/scrape/sources/universal.py
"""Universal catch-all source (priority 0): gallery-dl, then yt-dlp on exit 64.
Try gallery-dl's dedicated extractors first. Unsupported URLs (exit code & 64)
fall back to yt-dlp only for vetted allowlisted hosts as interim SSRF protection."""
import logging
import os
import time
from urllib.parse import urlparse

from .base import Source, Capabilities, Match
from . import registry, gdl
from .gdl import GdlError
from .. import netfetch

logger = logging.getLogger(__name__)

# Hosts allowed to reach the generic yt-dlp path as interim SSRF protection.
# Removed Coomer/Kemono/Cyberdrop/Bunkr sources are rejected by validators before
# this source is reached; they must not remain in this allowlist.
VETTED_DOMAINS = (
    'x.com', 'twitter.com', 'tiktok.com',
    'youtube.com', 'youtu.be', 'pornhub.com', 'xvideos.com', 'redgifs.com',
    'vimeo.com', 'dailymotion.com',
)

# Use gallery-dl's shared default enumeration window per page instead of
# maintaining another value that could drift.
MAX_ITEMS = gdl.DEFAULT_MAX_ITEMS

# Global scan budget for this catch-all source's arbitrary hosts. Without a
# limit, pathological album listings could launch nine 60-second subprocesses
# inside one synchronous Flask request.
# Alias gdl.DEFAULT_SCAN_BUDGET_SECONDS: enumerate() applies it to every caller,
# but passing it explicitly documents this exposed caller's dependency on it.
# The budget only bounds album recursion between subprocesses. Initial and
# already-started processes still run, so the real worst case is approximately
# 2 * GDL_TIMEOUT rather than this constant. Do not treat it as a total request
# timeout when changing its value.
SCAN_BUDGET_SECONDS = gdl.DEFAULT_SCAN_BUDGET_SECONDS


def _host_vetted(url):
    host = (urlparse(url).hostname or '').lower()
    if not host:
        return False
    return any(host == d or host.endswith('.' + d) for d in VETTED_DOMAINS)


class UniversalSource(Source):
    name = 'universal'
    priority = 0
    paginated = True
    category = 'image'
    capabilities = Capabilities(is_universal_fallback=True, own_downloader=True,
                                media_kinds=frozenset({'image', 'video'}))

    def match(self, url):
        from ..validators import url_validator, Platform
        # Reject unsafe arbitrary hosts here, before scan() launches gallery-dl.
        # If no source matches, the route returns 400 without starting a subprocess.
        ok, _err = netfetch._validate_public_http_url(url)
        if not ok:
            return None
        result = url_validator.validate_url(url)
        if result.is_valid and result.platform == Platform.GENERIC:
            return Match(url=url, validation=result)
        return None

    def scan(self, match):
        """Enumerate with gallery-dl (about 300 sites). Return direct page media or
        one cover per listed album by default; include_albums ("Scan full albums")
        enables full album recursion."""
        url = match.url
        page = max(0, int(getattr(match, 'page', 0) or 0))
        items, err = gdl.enumerate(
            url, platform='generic', max_items=MAX_ITEMS,
            per_album=None if getattr(match, 'include_albums', False) else 1,
            image_range=f'{page * MAX_ITEMS + 1}-{(page + 1) * MAX_ITEMS}',
            deadline=time.monotonic() + gdl.network_timeout(SCAN_BUDGET_SECONDS))
        if items:
            if getattr(items, 'from_albums', False):
                # Album recursion is bounded by count, never by page offset.
                # image_range only selects top-level media, so advertising "Load more"
                # for recursive results would do nothing. Disable pagination as with
                # the unsupported fallback below.
                match.paginated = False
            if getattr(items, 'partial', False):
                # The recursion time budget expired. Retain valid partial results
                # instead of discarding them for an error after a long scan.
                logger.info("universal scan: budget exhausted, partial result (%s)", url)
            return items, None
        if getattr(err, 'kind', None) == 'unsupported':
            # No gallery-dl extractor: preserve the historical single-media result
            # so vetted hosts can reach yt-dlp.
            match.paginated = False
            return ([{'url': url, 'title': url, 'thumbnail': None,
                      'type': 'video', 'platform': 'generic'}], None)
        # Propagate other errors unchanged, including kind='empty'. Routes handle
        # that kind for every source as success with zero results; authentication,
        # 429, DDoS-Guard and tool failures remain errors, never disguised as empty.
        # The fallback also uses GdlError(kind='empty'): if enumerate() ever returns
        # ([], None), a plain fallback string would incorrectly become a 502.
        return None, err or GdlError("Nothing to scan at this URL.", 'empty')

    def download(self, url, dest_base):
        """Legacy interface without a caller in this app. Actual downloads use
        _download_scrape_item with a hardened item['url'] fetch; see reddit.py."""
        # 1) Try gallery-dl with its dedicated extractor first.
        dest_dir = os.path.dirname(dest_base)
        filename = os.path.basename(dest_base)
        ok, abs_path, err = gdl.download(url, dest_dir, filename)
        if ok and abs_path:
            return True, os.path.basename(abs_path), None
        # 2) For unsupported sites, allow yt-dlp only on vetted hosts as SSRF
        #    protection. Check the classified kind, never the message text.
        if getattr(err, 'kind', None) == 'unsupported':
            if not _host_vetted(url):
                return False, None, "Site not supported (gallery-dl) and host not vetted for yt-dlp."
            return netfetch.download_via_ytdlp(url, dest_base)
        # 3) Propagate gallery-dl authentication/network errors instead of falling back.
        return False, None, err or "Generic download failed."


registry.register(UniversalSource())
