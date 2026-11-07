# app/scrape/sources/picazor.py
"""Picazor scraper: enumeration and direct curl_cffi downloads.

Use impersonate=chrome for the site's Cloudflare JA3/TLS checks. Parse
server-rendered HTML with regex, without a heavy HTML dependency.

Verified site structure: /fr/{creator} lists 24 recent items;
/fr/{creator}/page/{N} lists page N in reverse chronological order;
/fr/{creator}/{index} is a single-media detail page.
300px_{name}.mp4.jpg thumbnails map to /uploads/<path>/{name}.mp4;
300px_{name}.jpg thumbnails map to /uploads/<path>/{name}.jpg.

Public contract: scan(validation) -> (items, error);
download(url, dest_path) -> (ok, final_filename, error).
Neither raises: exceptions become messages."""
import logging
import math
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .base import ResultList
from .gdl import GdlError

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Self-contained constants; no config/settings imports.
# --------------------------------------------------------------------------- #
BASE_URL = "https://picazor.com"
ITEMS_PER_PAGE = 24
# Raised from 60 because server-side /page/N contains many more items.
# Scanning is synchronous, with one Cloudflare request per page, so
# MAX_PAGES limits time (about 1-2 seconds/page). More needs async pagination.
MAX_ITEMS = 300          # Hard cap on items returned by scan().
MAX_PAGES = 14           # garde-fou pagination (14×24=336 ≥ 300 ; ~20-30 s pire cas)
HTTP_TIMEOUT = 30        # Seconds (HTML request).
DOWNLOAD_TIMEOUT = 300   # Seconds (media download).
CHUNK_SIZE = 8192

PLATFORM = "picazor"

# Base headers; curl_cffi handles TLS fingerprinting with impersonate=chrome.
_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Signs of a Cloudflare challenge/block in HTML responses.
_CLOUDFLARE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "cf-challenge",
    "challenge-platform",
    "attention required",
    "checking your browser",
    "__cf_chl",
)

# Listing thumbnail: capture path, name and optional video marker.
_THUMB_RE = re.compile(r'"(/uploads/[^"]+?/)300px_([^"/]+?)(\.mp4)?\.jpg"')
# Full-size media on a detail page.
_DETAIL_VIDEO_RE = re.compile(r'"(/uploads/[^"]+?\.mp4)"')
# Original photo, without an NNNpx_ size prefix.
_DETAIL_PHOTO_RE = re.compile(r'"(/uploads/[^"]+?/)(?!\d+px[_-])([^"/]+?\.jpg)"')


# --------------------------------------------------------------------------- #
# Helpers internes
# --------------------------------------------------------------------------- #
def _looks_like_cloudflare(html: str, status_code: int = 200) -> bool:
    """Heuristically detect a Cloudflare challenge/block response."""
    if status_code in (403, 429, 503):
        return True
    head = (html or "")[:4000].lower()
    return any(marker in head for marker in _CLOUDFLARE_MARKERS)


def _path_stem(upload_path: str) -> str:
    """Filename without extension from an /uploads/... path."""
    filename = upload_path.rstrip("/").rsplit("/", 1)[-1]
    return filename.rsplit(".", 1)[0]


def _parse_picazor_url(url: str) -> dict:
    """Infer Picazor URL type from the raw language/creator/index path.

    Return {type: profile|media|listing|unknown, ...}. More precise than
    ValidationResult.value, which does not expose the detail index."""
    # Special pages: /fr/videos/week, /fr/models/..., /fr/categories/....
    m = re.search(r'picazor\.com/([^/]+)/(videos|models|categories)(?:/([^/?#]+))?', url)
    if m:
        return {"type": "listing", "category": m.group(2), "filter": m.group(3) or "", "url": url}

    # Page N du listing : /fr/{creator}/page/{N}
    m = re.search(r'picazor\.com/([^/]+)/([^/?#]+)/page/(\d+)', url)
    if m:
        return {"type": "profile", "language": m.group(1), "creator": m.group(2),
                "page": int(m.group(3)), "url": url}

    # Single-media detail page: /fr/{creator}/{index}.
    m = re.search(r'picazor\.com/([^/]+)/([^/?#]+)/(\d+)', url)
    if m:
        return {"type": "media", "language": m.group(1), "creator": m.group(2),
                "index": int(m.group(3)), "url": url}

    # Profil (page 1) : /fr/{creator}
    m = re.search(r'picazor\.com/([^/]+)/([^/?#]+)', url)
    if m:
        return {"type": "profile", "language": m.group(1), "creator": m.group(2),
                "page": 1, "url": url}

    return {"type": "unknown", "url": url}


def _request_html(url: str):
    """Fetch Picazor HTML with curl_cffi (impersonate=chrome).

    Return (html, error), or (None, message) for Cloudflare blocking/errors.
    Never raises."""
    from lds_sdk.netfetch import validate_public_url as _validate_public_http_url
    ok_url, ssrf_err = _validate_public_http_url(url)
    if not ok_url:
        return None, ssrf_err or "Picazor: URL blocked (SSRF)."

    try:
        from curl_cffi import requests as cf_requests
    except ImportError:
        return None, "Picazor needs the 'curl_cffi' package - install the scrape extras (Setup > Install everything)."

    try:
        response = cf_requests.get(
            url, headers=_HEADERS, impersonate="chrome", timeout=HTTP_TIMEOUT
        )
    except Exception as e:  # Network, TLS, timeout, etc.
        logger.warning("Picazor: request failed %s: %s", url, e)
        return None, f"Picazor: request failed ({e})."

    status = getattr(response, "status_code", 0)
    html = getattr(response, "text", "") or ""

    if _looks_like_cloudflare(html, status):
        return None, "Picazor (Cloudflare) blocked access."
    if status >= 400:
        return None, f"Picazor: HTTP {status} response."

    return html, None


def _parse_listing(html: str, creator: str) -> list:
    """Extract listing media through 300px_ thumbnails."""
    items = []
    seen = set()

    for m in _THUMB_RE.finditer(html):
        path, name, video_marker = m.group(1), m.group(2), m.group(3)
        is_video = video_marker is not None
        ext = ".mp4" if is_video else ".jpg"
        media_url = f"{BASE_URL}{path}{name}{ext}"
        if media_url in seen:
            continue
        seen.add(media_url)

        thumb_suffix = ".mp4.jpg" if is_video else ".jpg"
        items.append({
            "url": media_url,
            "title": f"{creator}_{name}",
            "thumbnail": f"{BASE_URL}{path}300px_{name}{thumb_suffix}",
            "type": "video" if is_video else "image",
            "platform": PLATFORM,
        })

    return items


def _max_media_index(html: str, creator: str) -> int:
    """Maximum /fr/{creator}/{i} link index approximates the media count."""
    indices = [
        int(m.group(1))
        for m in re.finditer(rf'href="/fr/{re.escape(creator)}/(\d+)"', html)
    ]
    return max(indices, default=0)


def _parse_detail(html: str, creator: str) -> list:
    """Extract one detail-page media item, preferring video over photo."""
    m = _DETAIL_VIDEO_RE.search(html)
    if m:
        media_url = f"{BASE_URL}{m.group(1)}"
        return [{
            "url": media_url,
            "title": f"{creator}_{_path_stem(m.group(1))}",
            "thumbnail": f"{media_url}.jpg",
            "type": "video",
            "platform": PLATFORM,
        }]

    m = _DETAIL_PHOTO_RE.search(html)
    if m:
        path, filename = m.group(1), m.group(2)
        media_url = f"{BASE_URL}{path}{filename}"
        return [{
            "url": media_url,
            "title": f"{creator}_{filename.rsplit('.', 1)[0]}",
            "thumbnail": media_url,
            "type": "image",
            "platform": PLATFORM,
        }]

    return []


def _ext_from_content_type(content_type: str, url: str) -> str:
    """File extension from content type, falling back to the URL."""
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    mapping = {
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/quicktime": ".mov",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    if ct in mapping:
        return mapping[ct]
    # Fallback: extension from URL.
    path = urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext in (".mp4", ".webm", ".mov", ".jpg", ".jpeg", ".png", ".gif", ".webp"):
        return ".jpg" if ext == ".jpeg" else ext
    return ".mp4"  # Reasonable Picazor default: most media are videos.


# --------------------------------------------------------------------------- #
# API publique
# --------------------------------------------------------------------------- #
def scan(validation):
    """Enumerate media from a Picazor URL.

    validation is ValidationResult with is_valid/platform/url_type/value/
    original_url. Supports PROFILE (paginated), VIDEO (detail) and LISTING
    (global page). Return (items, error): a common-schema list of at most
    MAX_ITEMS or None, and str|None error. Never raises; exceptions become
    (None, message). Cloudflare blocking returns a clear access error."""
    try:
        url = getattr(validation, "original_url", None) or getattr(validation, "value", "")
        url_type = getattr(validation, "url_type", None)
        url_type_name = getattr(url_type, "name", str(url_type)) if url_type else ""

        parsed = _parse_picazor_url(url)
        creator = parsed.get("creator") or getattr(validation, "value", "") or "picazor"

        # Single media item (detail page).
        if url_type_name == "VIDEO" or parsed["type"] == "media":
            html, err = _request_html(url)
            if err:
                return None, err
            items = _parse_detail(html, creator)
            if not items:
                # A detail page describes a specific media item. If HTTP succeeded but
                # neither video nor photo regex matches, site layout changed and parsing
                # failed to extract existing content. This is a tool error, never a
                # legitimate empty result.
                return None, "Picazor: no media found on the detail page."
            return items[:MAX_ITEMS], None

        # --- Listing global (videos/week, models, ...) --------------------- #
        if url_type_name == "LISTING" or parsed["type"] == "listing":
            html, err = _request_html(url)
            if err:
                return None, err
            items = _parse_listing(html, creator)
            if not items:
                # Successful listing with no 300px_ thumbnails: an empty category/filter
                # is more likely than a changed layout here, unlike detail pages that
                # guarantee one item. Return a legitimate empty result, like GdlError empty.
                return None, GdlError("Picazor: no media found in this listing.", 'empty')
            if len(items) > MAX_ITEMS:
                # Unambiguous truncation: this single parse produced more than MAX_ITEMS.
                # The pre-slice list proves items are discarded, unlike uncertainty
                # about later pages of a profile.
                result = ResultList(items[:MAX_ITEMS])
                result.partial = True
                return result, None
            return items[:MAX_ITEMS], None

        # Paginated profile (default PROFILE case).
        start_page = parsed.get("page", 1)
        all_items = []
        seen = set()
        total_pages = None
        page = start_page
        interrupted = False
        capped = False

        for _ in range(MAX_PAGES):
            page_url = f"{BASE_URL}/fr/{creator}" + (f"/page/{page}" if page > 1 else "")
            html, err = _request_html(page_url)
            if err:
                # Preserve collected items if a later Cloudflare/network request fails,
                # but mark them interrupted/partial rather than presenting a complete
                # profile. Use base.ResultList like RedGifs/Instagram; a plain sliced
                # list would silently hide pagination truncation.
                if all_items:
                    interrupted = True
                    break
                return None, err

            if total_pages is None:
                max_index = _max_media_index(html, creator)
                total_pages = max(1, math.ceil(max_index / ITEMS_PER_PAGE)) if max_index else 1

            page_items = _parse_listing(html, creator)
            if not page_items:
                break

            for it in page_items:
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                all_items.append(it)
                if len(all_items) >= MAX_ITEMS:
                    break

            if len(all_items) >= MAX_ITEMS:
                # At MAX_ITEMS, we cannot tell whether the profile ends exactly here
                # or later pages remain. Mark partial conservatively: an occasional
                # extra warning is preferable to hiding a real limit.
                capped = True
                break
            page += 1
            if page > total_pages:
                break
        else:
            # MAX_PAGES exhausted without a natural-end or MAX_ITEMS break. Since
            # page has not passed total_pages, pages remain beyond the time guard.
            # Report truncation rather than silently returning a complete result.
            capped = True

        if not all_items:
            # All pages exhausted without media: a legitimate empty profile, like
            # GdlError empty. Failure on the first page before any items was already
            # handled by the early return above.
            return None, GdlError("Picazor: no media found for this profile.", 'empty')
        if interrupted or capped:
            result = ResultList(all_items[:MAX_ITEMS])
            result.partial = True
            return result, None
        return all_items[:MAX_ITEMS], None

    except Exception as e:  # garde-fou ultime — ne jamais lever
        logger.exception("Picazor scan: unexpected error")
        return None, f"Picazor: unexpected error ({e})."


def download(url, dest_path):
    """Download Picazor video/image directly through curl_cffi.

    url is direct media or a detail page to resolve first. dest_path has
    no imposed extension; derive it from content type. Write atomically
    through .tmp -> final. Return (ok: bool, final_filename: str|None,
    error: str|None). Never raises."""
    try:
        from curl_cffi import requests as cf_requests
    except ImportError:
        return False, None, "Picazor needs the 'curl_cffi' package - install the scrape extras (Setup > Install everything)."

    try:
        dest_path = Path(dest_path)

        # Resolve Picazor detail-page URLs before downloading media.
        resolved_url = url
        if "/uploads/" not in url and "picazor.com" in url.lower():
            parsed = _parse_picazor_url(url)
            creator = parsed.get("creator", "picazor")
            html, err = _request_html(url)
            if err:
                return False, None, err
            detail = _parse_detail(html, creator)
            if not detail:
                return False, None, "Picazor: media not found on the detail page."
            resolved_url = detail[0]["url"]

        from lds_sdk.netfetch import validate_public_url as _validate_public_http_url
        ok_url, ssrf_err = _validate_public_http_url(resolved_url)
        if not ok_url:
            return False, None, ssrf_err or "Picazor: URL blocked (SSRF)."

        try:
            response = cf_requests.get(
                resolved_url, headers=_HEADERS, impersonate="chrome",
                timeout=DOWNLOAD_TIMEOUT, stream=True,
            )
        except Exception as e:
            logger.warning("Picazor download: request failed %s: %s", resolved_url, e)
            return False, None, f"Picazor: download failed ({e})."

        status = getattr(response, "status_code", 0)
        content_type = ""
        try:
            content_type = response.headers.get("content-type", "") or ""
        except Exception:
            content_type = ""

        if status in (401, 404, 410):
            return False, None, f"Picazor: resource unavailable (HTTP {status})."
        if status == 403 or status == 429 or status == 503:
            return False, None, "Picazor (Cloudflare) blocked access."
        if status >= 400:
            return False, None, f"Picazor: HTTP {status} response."

        # An HTML response is not media (Cloudflare or an error page).
        if "text/html" in content_type.lower():
            return False, None, "Picazor: HTML response instead of media (access blocked?)."

        # Extension finale selon le content-type (fallback : URL).
        final_ext = _ext_from_content_type(content_type, resolved_url)
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
            return False, None, f"Picazor: write error ({e})."

        # An empty file is a failure.
        try:
            if not tmp_path.exists() or tmp_path.stat().st_size == 0:
                tmp_path.unlink(missing_ok=True)
                return False, None, "Picazor: downloaded file is empty."
        except OSError:
            return False, None, "Picazor: downloaded file is invalid."

        # Renommage atomique .tmp -> final.
        try:
            os.replace(tmp_path, final_path)
        except OSError as e:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False, None, f"Picazor: finalization error ({e})."

        return True, final_path.name, None

    except Exception as e:  # garde-fou ultime — ne jamais lever
        logger.exception("Picazor download: unexpected error")
        return False, None, f"Picazor: unexpected error ({e})."


from .base import Source, Capabilities, Match
from . import registry


class PicazorSource(Source):
    name = 'picazor'
    priority = 100
    category = 'image'   # Classified as image by product policy, so available to non-admins.
    capabilities = Capabilities(can_enumerate_profile=True,
                                media_kinds=frozenset({'video', 'image'}),
                                own_downloader=True)

    def match(self, url):
        from ..validators import url_validator, Platform
        result = url_validator.validate_url(url)
        if result.is_valid and result.platform == Platform.PICAZOR:
            return Match(url=url, validation=result)
        # Direct CDN /uploads/... URLs lack the validator's /fr/{creator}/...
        # pattern but still belong to Picazor and need our curl_cffi downloader.
        # Preserve the previous host-based dispatch behavior.
        if result.platform == Platform.PICAZOR:
            return Match(url=url, validation=None)
        return None

    def scan(self, match):
        return scan(match.validation)

    def download(self, url, dest_base):
        return download(url, dest_base)   # curl_cffi existant


registry.register(PicazorSource())
