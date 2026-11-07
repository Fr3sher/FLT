# app/scrape/sources/civitai.py
"""Civitai source (civitai.com/civitai.red): tag/search image listings.

Examples: https://civitai.red/images?tags=5169 and civitai.com/images?tags=N.
gallery-dl 1.32.3 supports both domains natively, routing /images?...
to CivitaiImagesExtractor with tags parsed and types=image. Images are
direct Message.Url/type-3 items at image-b2.civitai.com/.../orig.
Load more therefore uses --range image windows (1-100, 101-200, etc.),
unlike PornPics gallery queues, which use --chapter-range.

NSFW: tRPC defaults to browsingLevel 31 (all levels), but adult content
requires a Bearer api-key. Because gallery-dl runs with --ignore-config,
pass it through -o api-key=<token> (gdl_opts)."""
import os

from ..validators import Platform
from .base import Capabilities
from .gdl_source import GalleryDlSource, resolve_cookies
from . import gdl
from . import registry

# Legacy local-tool token.txt, used only if neither the environment
# nor the admin cookies directory supplies a key.
_SKILL_TOKEN_PATH = os.path.expanduser('~/.claude/skills/civitai-download/token.txt')


def civitai_api_key():
    """Civitai Bearer API key for NSFW, or None for SFW-only scans.

    Precedence: CIVITAI_API_KEY environment variable, then
    <SCRAPE_COOKIES_DIR>/civitai_api_key.txt, then civitai-download token.txt.
    Read at runtime and never committed."""
    env = (os.environ.get('CIVITAI_API_KEY') or '').strip()
    if env:
        return env
    for path in (resolve_cookies('civitai_api_key'), _SKILL_TOKEN_PATH):
        try:
            if path and os.path.isfile(path):
                val = open(path, encoding='utf-8').read().strip()
                if val:
                    return val
        except OSError:
            pass
    return None


# Public API content, images/videos, with polite limits for large listings.
# Download directly with hardened curl_cffi: scan returns extensionless
# CDN URLs (.../original), which gallery-dl rejects (see download).
_CIVITAI_CAPS = Capabilities(
    can_enumerate_profile=True,
    polite=True,
    media_kinds=frozenset({'image', 'video'}),
    own_downloader=True,
)

# Civitai CDN content types include images and animated videos. Used for
# the hardened fetch allowlist and extension mapping, since CDN URLs end
# with /original rather than a filename extension.
_CIVITAI_MEDIA_TYPES = frozenset({
    'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'image/avif',
    'video/mp4', 'video/webm', 'video/quicktime',
})
_CT_EXT = {
    'image/jpeg': '.jpg', 'image/jpg': '.jpg', 'image/png': '.png',
    'image/gif': '.gif', 'image/webp': '.webp', 'image/avif': '.avif',
    'video/mp4': '.mp4', 'video/webm': '.webm', 'video/quicktime': '.mov',
}
# fetch_hardened_bytes returns a short reason code → actionable English message.
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
    """File extension from content type, falling back to URL extension or .png.
    Civitai mainly serves PNG, making it a reasonable final fallback."""
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
    page_size = 100   # Images per Load more batch (tRPC returns about 100 per page).
    category = 'image'  # images IA → ouvert aux non-admins

    @property
    def gdl_opts(self):
        # Bearer api-key enables NSFW during scans only; absent means SFW.
        # Downloads do not use gallery-dl and need no key: the CDN serves media
        # without authentication once its URL is known.
        key = civitai_api_key()
        return ['-o', f'api-key={key}'] if key else None

    def download(self, url, dest_base):
        """Download Civitai media directly with hardened fetch.

        Scan returns extensionless CDN URLs (.../original). gallery-dl rejects
        these with Unsupported URL/exit 64: its Civitai extractor matches site
        pages and directlink requires a filename extension. fetch_hardened_bytes
        checks SSRF, disables redirects, validates content type and derives the
        extension. download_service._finalize then checks magic bytes, applies
        non-admin image-only restrictions and runs antivirus checks. Non-admins
        therefore cannot receive video regardless of the derived extension."""
        from ..netfetch import MAX_DRIVER_BYTES, fetch_hardened_bytes
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
        # Image window for the requested zero-based match.page, set by /scan.
        # Direct type-3 media uses image_range; the default gdl limit of 120 would
        # cap results instead of advancing the Load more window.
        page = max(0, getattr(match, 'page', 0) or 0)
        start = page * self.page_size + 1
        end = (page + 1) * self.page_size
        return gdl.enumerate(match.url, platform=self.name,
                             max_items=self.page_size,
                             image_range=f'{start}-{end}',
                             cookies=self._cookies(), extra_opts=self.gdl_opts)


registry.register(CivitaiSource())
