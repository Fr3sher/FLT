# app/scrape/sources/base.py
"""Common scraping source interface for the pluggable registry.

Uses only abc/dataclasses/typing to avoid import cycles. Concrete sources
import validators lazily inside match(), never in this module."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Capabilities:
    """Declare source capabilities so routes/download_service can dispatch
    without knowing the concrete source."""
    can_enumerate_profile: bool = False         # Profile/niche/album versus a single media item.
    needs_auth: bool = False                     # Cookies needed (a UX hint, not a hard requirement).
    media_kinds: frozenset = field(default_factory=lambda: frozenset({'video'}))
    own_downloader: bool = False                 # True=source.download() ; False=yt-dlp universel
    polite: bool = False                         # sleep/limit-rate (civitai/x/pornpics/…)
    is_universal_fallback: bool = False          # Exactly ONE source, with priority 0.


@dataclass
class Match:
    """Resolution handle: URL, parsed ValidationResult (None for the universal
    source), and matching Source assigned by the registry.

    The /scan route sets zero-based page for Load more on paginated sources
    (Source.paginated); other sources ignore it. paginated lets scan()
    override the default for a specific URL, such as a single media item
    from a source that also supports listings."""
    url: str
    validation: object = None
    source: object = None
    page: int = 0
    paginated: Optional[bool] = None


class ResultList(list):
    """Scraping result items carrying provenance metadata, like GdlError
    subclassing str. Existing list consumers keep working; interested callers
    can inspect the attributes.

    This is a public source contract, like Source/Match/Capabilities, rather
    than a gallery-dl detail. Independent RedGifs and Instagram sources also
    use it to report truncation. It formerly lived as the private
    gdl._ResultList, coupling those consumers unnecessarily to gallery-dl.

    from_albums is true only when every item came from gdl.enumerate type-6
    album recursion rather than top-level media. That recursion is limited
    by max_albums, not page offsets, so advertising Load more would request
    an unused window. The unsupported fallback disables pagination for the
    same reason. RedGifs/Instagram always leave this false.

    partial marks a scan interrupted before completion: album recursion
    time budget exhausted, a RedGifs page rejected after a successful one,
    or interrupted Instagram iteration. Collected items remain valid but
    may be incomplete. routes/scrape.py reads getattr(items, 'partial', False)
    without knowing the concrete source."""
    from_albums = False
    partial = False


class Source(ABC):
    """Scraping source: match(url) returns Match for supported URLs, else None.
    scan(match) enumerates media. download(url, dest_base) is called only
    with capabilities.own_downloader; other callers use yt-dlp."""
    name: str = 'source'
    priority: int = 0
    capabilities: Capabilities = Capabilities()
    paginated: bool = False   # scan() honors match.page → the route exposes "Load more"
    # Access category: image is open to non-admins with the scrape feature;
    # video is admin-only for both scans and downloads. Default to video
    # (fail closed) until a new source is explicitly classified as image.
    category: str = 'video'

    @abstractmethod
    def match(self, url: str) -> Optional[Match]:
        ...

    @abstractmethod
    def scan(self, match: Match) -> tuple[list, Optional[str]]:
        """Return (items: list, error: str|None). Never raises."""
        ...

    def download(self, url: str, dest_base: str) -> tuple[bool, Optional[str], Optional[str]]:
        """Return (ok: bool, filename: str|None, error: str|None).
        Unsupported by default; sources with own_downloader=False use yt-dlp."""
        raise NotImplementedError(f"{self.name} has no dedicated downloader")
