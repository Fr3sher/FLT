# app/scrape/sources/civitai.py
"""Civitai source (civitai.com / civitai.red): image listings by tag or search.

Examples: https://civitai.red/images?tags=5169, https://civitai.com/images?tags=N

gallery-dl 1.32.3 natively supports both domains and sends /images?... to
CivitaiImagesExtractor, which parses tags and uses types=image. Images are
direct media (Message.Url, type 3, image-b2.civitai.com/.../orig), bounded by
--range. "Load more" therefore uses image-range windows: page 0 is 1-100,
page 1 is 101-200, unlike PornPics' gallery queues and --chapter-range.

The tRPC API defaults to browsingLevel 31 (all levels), but serving adult
content requires a Bearer api-key. Since the app uses --ignore-config,
gdl_opts supplies the key through -o api-key=<token>."""
import os

from ..validators import Platform
from .base import Capabilities
from .gdl_source import GalleryDlSource
from . import gdl
from . import registry

# The key resolver is the core's (app/utils/credentials.py): the Studio's
# prompt browser and Setup read the same key, and the core never asks a
# plugin for a value. Re-exported under its historical name.
from lds_sdk.credentials import civitai_api_key  # noqa: F401 — re-export


# Public API content, images and videos, with polite limits for large listings.
# Download directly using hardened curl_cffi: scan results are extensionless CDN
# URLs that gallery-dl rejects (image-b2.civitai.com/.../original).
_CIVITAI_CAPS = Capabilities(
    can_enumerate_profile=True,
    polite=True,
    media_kinds=frozenset({'image', 'video'}),
    own_downloader=True,
)

# Content types served by Civitai's CDN include images and videos/animations.
# Use them for the hardened fetch allowlist and extension mapping, since CDN
# URLs end with /original rather than a file extension.
_CIVITAI_MEDIA_TYPES = frozenset({
    'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'image/avif',
    'video/mp4', 'video/webm', 'video/quicktime',
})
_CT_EXT = {
    'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
    'image/gif': '.gif', 'image/webp': '.webp', 'image/avif': '.avif',
    'video/mp4': '.mp4', 'video/webm': '.webm', 'video/quicktime': '.mov',
}
# fetch_hardened_bytes renvoie un code court (reason) → message FR exploitable.
_FETCH_REASON_MSG = {
    'redirect': 'Civitai: redirect blocked (SSRF guard).',
    'status': 'Civitai: resource unavailable (non-200 HTTP).',
    'type': "Civitai: unexpected media type (neither image nor video).",
    'toolarge': 'Civitai: media too large.',
    'fetch': 'Civitai: CDN request failed.',
    'no_curl': "Civitai needs the 'curl_cffi' package - install the scrape extras (Setup > Install everything).",
    'noimage': "Civitai: content is not a valid image.",
}


def _ext_for(content_type, url):
    """Derive an extension from content type, falling back to the URL or .png.
    Civitai predominantly serves PNG, making it a reasonable final default."""
    ct = (content_type or '').split(';', 1)[0].strip().lower()
    if ct in _CT_EXT:
        return _CT_EXT[ct]
    from urllib.parse import urlparse
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.mp4', '.webm', '.mov'):
        return '.jpg' if ext == '.jpeg' else ext
    return '.png'


class CivitaiSource(GalleryDlSource):
    name = 'civitai'
    platform_enum = Platform.CIVITAI
    priority = 100
    capabilities = _CIVITAI_CAPS
    paginated = True
    page_size = 100   # images per "Load more" batch (tRPC pages contain about 100)
    category = 'image'  # AI images: available to non-admins

    @property
    def gdl_opts(self):
        # Use the Bearer api-key for adult content during scans only; no key means SFW.
        # Downloads bypass gallery-dl and need no key: the CDN serves known media URLs
        # without authentication.
        key = civitai_api_key()
        return ['-o', f'api-key={key}'] if key else None

    def download(self, url, dest_base):
        """Download Civitai media directly with a hardened fetch.

        Scan results are extensionless CDN URLs (image-b2.civitai.com/.../original).
        gallery-dl rejects them with "Unsupported URL" (exit 64): its Civitai extractor
        accepts site pages, while its directlink fallback requires a file extension.
        fetch_hardened_bytes provides SSRF protection, disables redirects and checks
        content type, which determines the extension. download_service._finalize then
        checks magic bytes, applies the non-admin image-only restriction and scans
        for viruses. Non-admins cannot receive video regardless of the extension."""
        from lds_sdk.netfetch import MAX_DRIVER_BYTES, fetch_hardened_bytes
        ok, data, ctype, reason = fetch_hardened_bytes(
            url, allowed_types=_CIVITAI_MEDIA_TYPES, max_bytes=MAX_DRIVER_BYTES)
        if not ok or not data:
            return False, None, _FETCH_REASON_MSG.get(reason, f'Civitai: failed ({reason}).')
        dest_dir = os.path.dirname(dest_base)
        filename = os.path.basename(dest_base) + _ext_for(ctype, url)
        try:
            os.makedirs(dest_dir, exist_ok=True)
            with open(os.path.join(dest_dir, filename), 'wb') as f:
                f.write(data)
        except OSError as e:
            return False, None, f"Civitai: write error ({e})."
        return True, filename, None

    def scan(self, match):
        # Select the requested image window (zero-based match.page, set by /scan).
        # Direct type-3 media use image_range to bound the stream; the default cap of
        # 120 would truncate results, and "Load more" requires an offset window.
        page = max(0, getattr(match, 'page', 0) or 0)
        start = page * self.page_size + 1
        end = (page + 1) * self.page_size
        return gdl.enumerate(match.url, platform=self.name,
                             max_items=self.page_size,
                             image_range=f'{start}-{end}',
                             cookies=self._cookies(), extra_opts=self.gdl_opts)


registry.register(CivitaiSource())
