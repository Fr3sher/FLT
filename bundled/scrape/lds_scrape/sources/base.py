# app/scrape/sources/base.py
"""Shared scraping-source interface with a pluggable registry.

Dependency-free apart from abc/dataclasses/typing to avoid import cycles.
Concrete sources import `validators` lazily in match(), never through this module."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Capabilities:
    """Declare source capabilities so routes and download_service can dispatch
    without knowing the concrete source."""
    can_enumerate_profile: bool = False         # profile/niche/album versus individual media
    needs_auth: bool = False                     # cookies needed (UX hint, not a hard gate)
    media_kinds: frozenset = field(default_factory=lambda: frozenset({'video'}))
    own_downloader: bool = False                 # True: source.download(); False: universal yt-dlp
    polite: bool = False                         # sleep/rate limits (civitai/x/pornpics/...)
    is_universal_fallback: bool = False          # exactly ONE source (priority 0)


@dataclass
class Match:
    """Resolution handle: URL, parsed ValidationResult (None for the universal
    source), and the matching Source assigned by the registry.

    The /scan route sets zero-based `page` for paginated sources' "Load more"
    requests; other sources ignore it. `paginated` lets scan() override the
    source default for a specific URL, such as an individual media item."""
    url: str
    validation: object = None
    source: object = None
    page: int = 0
    paginated: Optional[bool] = None


class ResultList(list):
    """Scraped items with provenance metadata.

    This list subclass preserves compatibility with callers that only need items;
    metadata-aware callers can read its attributes, as with gdl.GdlError and str.
    It is a public source contract alongside Source, Match and Capabilities,
    not a gallery-dl implementation detail. Standalone sources also use it.
    Previously named gdl._ResultList, it now avoids coupling those sources to gdl.

    - `from_albums`: all items came from gdl.enumerate's type-6 album recursion
      rather than top-level media. Recursion is bounded by album count, not page
      offset, so advertising "Load more" for these items would not work. The
      unsupported fallback disables match.paginated for the same reason.
      Standalone RedGifs and Instagram producers leave this False.
    - `partial`: the scan stopped before fully exploring its target, for example
      after exhausting the album time budget, failing on a later RedGifs page,
      or interrupting Instagram iteration. Collected items remain valid but may
      be incomplete. Routes read getattr(items, 'partial', False) without knowing
      the concrete source."""
    from_albums = False
    partial = False


class Source(ABC):
    """A scraping source. match(url) returns a Match for supported URLs, else None.
    scan(match) enumerates media. download(url, dest_base) is called only when
    capabilities.own_downloader is True; otherwise the caller uses yt-dlp."""
    name: str = 'source'
    priority: int = 0
    capabilities: Capabilities = Capabilities()
    paginated: bool = False   # scan() honors match.page; the route exposes "Load more"
    # Access category: 'image' permits non-admins with the scrape feature;
    # 'video' reserves both scan and download for admins. Default to 'video'
    # so new sources fail closed until explicitly classified as 'image'.
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
