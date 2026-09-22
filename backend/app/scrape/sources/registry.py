# app/scrape/sources/registry.py
"""Source registry: resolve a URL to its responsible source.

Replace separate dispatch in validators, routes and download_service. Sources
are sorted by descending priority; resolve(url) returns the first truthy Match,
so a dedicated source (priority 100) wins over the universal fallback (0)."""
import logging
from typing import Optional

from .base import Source, Match


logger = logging.getLogger(__name__)


class _Registry:
    def __init__(self):
        self._sources = []  # type: list[Source]

    def register(self, src: Source) -> None:
        self._sources.append(src)

    def all_sources(self) -> list:
        return sorted(self._sources, key=lambda s: s.priority, reverse=True)

    def resolve(self, url: str) -> Optional[Match]:
        for src in self.all_sources():
            try:
                m = src.match(url)
            except Exception as exc:
                logger.warning("Source %r match() raised an exception; skipped: %r",
                               getattr(src, 'name', '?'), exc)
                m = None
            if m is not None:
                m.source = src
                return m
        return None

    def assert_one_universal(self) -> None:
        names = [s.name for s in self._sources]
        if len(names) != len(set(names)):
            raise RuntimeError(f"Scraping sources: duplicate names ({names})")
        universals = [s.name for s in self._sources
                      if getattr(s.capabilities, 'is_universal_fallback', False)]
        if len(universals) != 1:
            raise RuntimeError(
                f"There must be EXACTLY one universal source; found: {universals}")


# Module-level registry populated by imports in sources/__init__.py.
_registry = _Registry()


def register(src: Source) -> None:
    _registry.register(src)


def resolve(url: str) -> Optional[Match]:
    return _registry.resolve(url)


def all_sources():
    return _registry.all_sources()


def assert_one_universal() -> None:
    _registry.assert_one_universal()
