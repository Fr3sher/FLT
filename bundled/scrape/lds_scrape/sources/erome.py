# app/scrape/sources/erome.py
"""Erome scraper: gallery-dl enumeration and direct curl_cffi downloads.

Erome exposes albums (/a/ID), search (/search?q=) and user profiles (/USER).
The shared gdl.py engine handles message types 3, 6 and -1, including the
extractor-error sentinel that previously hid authentication and 429 failures.

gallery-dl rejects language subdomains such as fr.erome.com. Normalize the
host to www.erome.com while preserving the path and query before delegation.

Public scraping-source API:
    scan(validation) -> (items, error)
    download(url, dest_path) -> (ok, final_filename, error)
Neither raises: exceptions are caught and converted to messages."""
import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from . import gdl

logger = logging.getLogger(__name__)

# Constants are self-contained: no config/settings imports.
BASE = "https://www.erome.com"
MAX_ITEMS = 120          # hard limit on media returned by scan()
MAX_ALBUMS = 8           # bound search/profile recursion time
DOWNLOAD_TIMEOUT = 120   # seconds for media downloads
CHUNK_SIZE = 8192

PLATFORM = "erome"

# Normalize language hosts (fr./de./...) to www.erome.com.
_HOST_RE = re.compile(r'^https?://[^/]*erome\.com', re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Helpers internes
# --------------------------------------------------------------------------- #
def _normalize(url: str) -> str:
    """Use www.erome.com because gallery-dl rejects language subdomains.
    Preserve the path and query; leave non-Erome URLs unchanged."""
    url = (url or "").strip()
    if _HOST_RE.match(url):
        return _HOST_RE.sub(BASE, url, count=1)
    return url


def _ext_from_url(url: str) -> str:
    """Derive a file extension including its dot from the URL; default to .mp4."""
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in (".mp4", ".webm", ".mov", ".m4v", ".jpg", ".jpeg",
               ".png", ".gif", ".webp"):
        return ".jpg" if ext == ".jpeg" else ext
    return ".mp4"


# --------------------------------------------------------------------------- #
# API publique
# --------------------------------------------------------------------------- #
def scan(validation):
    """Enumerate Erome media through the shared gallery-dl engine.

    Normalize language subdomains, then delegate type-3 media, type-6 album
    recursion and type--1 extractor errors. Return (items, error); never raises."""
    try:
        url = getattr(validation, 'original_url', None) or getattr(validation, 'value', '')
        url = _normalize(url)
        if not url:
            return None, "Erome: missing URL."
        items, err = gdl.enumerate(url, platform=PLATFORM,
                                   max_items=MAX_ITEMS, max_albums=MAX_ALBUMS)
        if err:
            # Prefix GdlError without losing .kind. A plain f-string would turn it
            # into an ordinary str, preventing routes from distinguishing 'empty'
            # from other failures.
            return None, gdl.GdlError(f"Erome: {err}", getattr(err, 'kind', None))
        return items, None
    except Exception as e:
        logger.exception("Erome scan: unexpected error")
        return None, f"Erome: unexpected error ({e})."


def download(url, dest_path):
    """Download Erome media (video or image) directly with curl_cffi.

    url is a direct CDN URL, e.g. https://v22.erome.com/.../X_720p.mp4.
    dest_path is the output path without a required extension; the URL determines
    its extension. Write atomically from .tmp to the final path.

    Return (ok: bool, final_filename: str|None, error: str|None). Never raises."""
    try:
        from curl_cffi import requests as cf_requests
    except ImportError:
        return False, None, "Erome needs the 'curl_cffi' package - install the scrape extras (Setup > Install everything)."

    try:
        dest_path = Path(dest_path)

        from lds_sdk.netfetch import validate_public_url as _validate_public_http_url
        ok_url, ssrf_err = _validate_public_http_url(url)
        if not ok_url:
            return False, None, ssrf_err or "Erome: URL blocked (SSRF)."

        try:
            response = cf_requests.get(
                url, impersonate="chrome",
                headers={"Referer": "https://www.erome.com/"},
                timeout=DOWNLOAD_TIMEOUT, stream=True,
            )
        except Exception as e:
            logger.warning("Erome download: request failed %s: %s", url, e)
            return False, None, f"Erome: download failed ({e})."

        status = getattr(response, "status_code", 0)
        content_type = ""
        try:
            content_type = response.headers.get("content-type", "") or ""
        except Exception:
            content_type = ""

        if status in (401, 404, 410):
            return False, None, f"Erome: resource unavailable (HTTP {status})."
        if status in (403, 429, 503):
            return False, None, "Erome: access blocked."
        if status >= 400:
            return False, None, f"Erome: HTTP {status} response."

        # An HTML response is not media.
        if "text/html" in content_type.lower():
            return False, None, "Erome: HTML response instead of media."

        final_ext = _ext_from_url(url)
        final_path = dest_path.with_name(dest_path.name + final_ext) \
            if not dest_path.suffix else dest_path.with_suffix(final_ext)
        tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")

        try:
            final_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

        try:
            with open(tmp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False, None, f"Erome: write error ({e})."

        # An empty file is a failure.
        try:
            if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                tmp_path.unlink(missing_ok=True)
                return False, None, "Erome: downloaded file is empty."
        except OSError:
            return False, None, "Erome: downloaded file is invalid."

        # Renommage atomique .tmp -> final.
        try:
            os.replace(tmp_path, final_path)
        except OSError as e:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False, None, f"Erome: finalization error ({e})."

        return True, final_path.name, None

    except Exception as e:  # garde-fou ultime — ne jamais lever
        logger.exception("Erome download: unexpected error")
        return False, None, f"Erome: unexpected error ({e})."


from .base import Source, Capabilities, Match
from . import registry


class EromeSource(Source):
    name = 'erome'
    priority = 100
    capabilities = Capabilities(can_enumerate_profile=True,
                                media_kinds=frozenset({'video', 'image'}),
                                own_downloader=True)

    def match(self, url):
        from ..validators import url_validator, Platform
        result = url_validator.validate_url(url)
        if result.is_valid and result.platform == Platform.EROME:
            return Match(url=url, validation=result)
        # URLs CDN directes (v*.erome.com) : sous-domaine hors VALID_DOMAINS mais
        # bien sur erome.com → notre downloader curl_cffi (Referer requis).
        if result.platform == Platform.EROME:
            return Match(url=url, validation=None)
        return None

    def scan(self, match):
        return scan(match.validation)

    def download(self, url, dest_base):
        return download(url, dest_base)


registry.register(EromeSource())
