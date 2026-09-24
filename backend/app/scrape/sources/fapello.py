# app/scrape/sources/fapello.py
"""Fapello source, including language mirrors (fr./de./es.).

gallery-dl 1.32.3 supports model pages natively. A model page queues
posts (Message.Queue/type 6), each with one direct type-3 image/video.
Like PornPics categories, use _PhotoSiteSource and --chapter-range;
gdl.enumerate recursion collects media from each post.

gallery-dl only accepts canonical fapello.com (optionally www), so
normalize language hosts before enumeration. Direct CDN URLs already
have extensions and use its directlink extractor; the inherited
GalleryDlSource downloader suffices without a separate direct fetch."""
from urllib.parse import urlparse, urlunparse

from ..validators import Platform
from .image_sites import _PhotoSiteSource
from . import registry


def _canonical_fapello_url(url):
    """Map Fapello language mirrors and www to canonical fapello.com, which
    gallery-dl recognizes. Leave other hosts unchanged."""
    try:
        p = urlparse(url)
    except Exception:
        return url
    host = (p.hostname or '').lower()
    if host == 'fapello.com' or host.endswith('.fapello.com'):
        # Rebuild netloc as fapello.com, dropping subdomain, port and userinfo.
        return urlunparse((p.scheme, 'fapello.com', p.path, p.params, p.query, p.fragment))
    return url


class FapelloSource(_PhotoSiteSource):
    name = 'fapello'
    platform_enum = Platform.FAPELLO
    # Inherit category=image and image/video, own_downloader and polite
    # capabilities from _PhotoSiteSource, like other mixed-content image sources.
    # Raise gallery_cap from 8 to 24: each Fapello post has just one media item,
    # whereas a PornPics chapter has dozens. This makes Load more useful while
    # keeping sequential gallery-dl subprocesses near 15 seconds per batch.
    # Page N contains posts 24N+1 through 24N+24.
    gallery_cap = 24

    def scan(self, match):
        # Normalize the host, then delegate chapter-range pagination to
        # _PhotoSiteSource. Downloads already use canonical CDN URLs from scan
        # and need no normalization.
        match.url = _canonical_fapello_url(match.url)
        return super().scan(match)


registry.register(FapelloSource())
