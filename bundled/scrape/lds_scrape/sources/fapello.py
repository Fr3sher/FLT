# app/scrape/sources/fapello.py
"""Fapello source (fapello.com and language mirrors such as fr./de./es.).

A model page lists the complete set. gallery-dl 1.32.3 natively supports
fapello.com/<model>/ as a queue of posts (Message.Queue, type 6), each carrying
one direct media item (type 3, fapello.com/content/.../xxx.jpg|mp4).
Like PornPics categories, it uses _PhotoSiteSource's --chapter-range pagination
and gdl.enumerate's type-6 recursion to collect post media.

gallery-dl only accepts the canonical (www.)?fapello.com host; language mirrors
return "Unsupported URL". Normalize the host before enumeration. Direct CDN
URLs include extensions, so GalleryDlSource's inherited directlink downloader
is sufficient."""
from urllib.parse import urlparse, urlunparse

from ..validators import Platform
from .image_sites import _PhotoSiteSource
from . import registry


def _canonical_fapello_url(url):
    """Map Fapello language mirrors and www to the canonical fapello.com host.
    Leave non-Fapello URLs unchanged."""
    try:
        p = urlparse(url)
    except Exception:
        return url
    host = (p.hostname or '').lower()
    if host == 'fapello.com' or host.endswith('.fapello.com'):
        # Rebuild the netloc as fapello.com, dropping subdomains, ports and userinfo.
        return urlunparse((p.scheme, 'fapello.com', p.path, p.params, p.query, p.fragment))
    return url


class FapelloSource(_PhotoSiteSource):
    name = 'fapello'
    platform_enum = Platform.FAPELLO
    # Inherit category='image' and mixed-media, own-downloader and polite
    # capabilities from _PhotoSiteSource, as with its other image aggregators.
    # Raise gallery_cap from 8 to 24: each Fapello post contains one media item,
    # whereas a PornPics chapter contains an entire gallery. A page of 24 takes
    # about 15 seconds with sequential gallery-dl subprocesses; page N covers
    # posts 24N+1 through 24N+24.
    gallery_cap = 24

    def scan(self, match):
        # Normalize the host, then delegate chapter-range pagination to
        # _PhotoSiteSource. Downloads already receive canonical CDN URLs from
        # scan results, so they need no further normalization.
        match.url = _canonical_fapello_url(match.url)
        return super().scan(match)


registry.register(FapelloSource())
