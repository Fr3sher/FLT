"""Pins lds_scrape.probes.dependencies() against bundled/scrape/requirements.txt.

A package added to the requirements file and forgotten in the probe's module
tuple reads as "installed" the moment the ALREADY-probed modules happen to be
present — the Web images tab lights up green and fails on the first real
search instead. That is exactly the gap `ddgs` (2026-08) and `yt_dlp` shipped
with: both are imported/invoked by the scrape stack, both were declared in
bundled/scrape/requirements.txt, neither was in the probe tuple. This test makes a
repeat of that omission fail the suite instead of shipping quietly.
"""
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from lds_scrape import probes

_ROOT = Path(__file__).resolve().parents[2]
_REQ = _ROOT / 'bundled' / 'scrape' / 'requirements.txt'

# bundled/scrape/requirements.txt PyPI name -> the module name it installs under.
# find_spec() probes the IMPORT name, not the PyPI name, so this mapping is
# what lets the test compare the two lists at all.
_PYPI_TO_IMPORT = {
    'gallery-dl': 'gallery_dl',
    'instaloader': 'instaloader',
    'yt-dlp': 'yt_dlp',
    'curl_cffi': 'curl_cffi',
    'brotli': 'brotli',
    'beautifulsoup4': 'bs4',
    'cloudscraper': 'cloudscraper',
    'lxml': 'lxml',
    'ddgs': 'ddgs',
    'browser-cookie3': 'browser_cookie3',
}

# Declared in bundled/scrape/requirements.txt but never imported directly anywhere
# under lds_scrape/sources/** — verified by grep, not assumed. brotli is transitive
# decompression support for curl_cffi/yt-dlp; bs4/cloudscraper/lxml ride along
# unused today (picazor.py parses by regex on purpose — see its module
# docstring). Nothing in our own code raises ImportError over their absence,
# so they are not a probe gap. New entries must be justified here explicitly,
# not silently swallowed by this set.
_NOT_DIRECTLY_IMPORTED = {'brotli', 'bs4', 'cloudscraper', 'lxml'}
# Instagram can reuse a saved Instaloader session without this optional browser
# cookie reader. Its explicit availability gate is covered below.
_OPTIONAL_SESSION_HELPERS = {'browser_cookie3'}


def _requirements_import_names():
    names = []
    for line in _REQ.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        pypi_name = re.split(r'[<>=!~\[]', line, maxsplit=1)[0].strip()
        assert pypi_name in _PYPI_TO_IMPORT, (
            f'{pypi_name!r} was added to bundled/scrape/requirements.txt but this test does '
            'not know its import name yet: add it to _PYPI_TO_IMPORT here, and to '
            "lds_scrape.probes.dependencies()'s module tuple (or to _NOT_DIRECTLY_IMPORTED with a "
            'reason, if the scrape stack never imports it directly).'
        )
        names.append(_PYPI_TO_IMPORT[pypi_name])
    return names


def _probed_modules():
    """What lds_scrape.probes.dependencies() actually asks find_spec about — behavior, not
    a regex over its source, so a rewrite of the function still gets caught."""
    seen = []
    real_find_spec = __import__('importlib.util', fromlist=['find_spec']).find_spec

    def spy(name, *a, **k):
        seen.append(name)
        return real_find_spec(name, *a, **k)

    with patch('importlib.util.find_spec', side_effect=spy):
        probes.dependencies()
    return set(seen)


def test_requirements_file_names_are_all_accounted_for():
    """Fails loudly (not silently) the moment an unmapped package lands in
    bundled/scrape/requirements.txt, instead of that package quietly slipping past
    both lists below."""
    assert _requirements_import_names(), 'bundled/scrape/requirements.txt must not go empty'


@pytest.mark.plugins('scrape')
def test_every_directly_imported_scrape_requirement_is_probed(app):
    required = _requirements_import_names()
    probed = _probed_modules()
    for module in required:
        if module in _NOT_DIRECTLY_IMPORTED | _OPTIONAL_SESSION_HELPERS:
            continue
        assert module in probed, (
            f'{module!r} is declared in bundled/scrape/requirements.txt and imported by the '
            'scrape stack, but lds_scrape.probes.dependencies() does not check for it — an install '
            'missing only this package would still read "scrape deps OK".'
        )


def test_missing_browser_cookie_helper_preserves_other_scrape_sources(monkeypatch):
    from lds_scrape.sources import instagram
    monkeypatch.setattr(instagram, "BROWSER_COOKIE3_AVAILABLE", False)
    monkeypatch.setattr(instagram, "browser_cookie3", None)
    assert instagram._auto_import_browser_cookies(object()) is False
