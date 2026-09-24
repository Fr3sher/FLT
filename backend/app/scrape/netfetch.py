# app/scrape/netfetch.py
"""Scraping network helpers: anti-SSRF validation and yt-dlp execution.

Independent of routes/download_service so both can import them without cycles.
See routes.py for the security context (admin-only access, SSRF)."""
from ..timeout_settings import network_timeout
import sys
import socket
import ipaddress
import subprocess
import tempfile
import shutil
from urllib.parse import urlparse

from flask import current_app

# Only the yt-dlp *video* download path uses this; the concept bridge fetches
# images via fetch_hardened_bytes and never touches it. Our config has no such
# constant, so degrade gracefully instead of breaking the whole import.
try:
    from ..config import COMFYUI_OUTPUT_DIR
except ImportError:  # pragma: no cover - our app resolves the output dir differently
    COMFYUI_OUTPUT_DIR = None

# Download size limit (driver videos do not need more).
MAX_DRIVER_BYTES = 200 * 1024 * 1024  # 200 Mo
# Wall-clock timeout for the yt-dlp subprocess.
DOWNLOAD_TIMEOUT = 180  # seconds
# Internal yt-dlp socket timeout, per network request.
SOCKET_TIMEOUT = 30  # seconds

# Minimum yt-dlp version, raised on 2026-08-18. The old 2024.07.01 floor
# (CVE-2024-38519) was two years and two CVEs behind: CVE-2026-50019
# (cookie leak, fixed in 2026.06.09) and CVE-2026-55404 (command injection
# through --write-link, fixed in 2026.07.04). Warn without blocking; a hard
# version assertion would prevent Flask from starting.
YTDLP_VERSION_FLOOR = (2026, 7, 4)
_version_checked = False

_ffmpeg_checked = None


def _ffmpeg_available():
    """Whether ffmpeg is on PATH (cached). Needed to mux bv*+ba; without it
    yt-dlp cannot merge separate streams."""
    global _ffmpeg_checked
    if _ffmpeg_checked is None:
        _ffmpeg_checked = shutil.which('ffmpeg') is not None
    return _ffmpeg_checked


def _ytdlp_version_tuple():
    """Installed yt-dlp version as (YYYY, M, D), or None if unavailable. Never raises."""
    try:
        import yt_dlp
        parts = str(yt_dlp.version.__version__).split('.')[:3]
        return tuple(int(p) for p in parts)
    except Exception:
        return None


def _check_ytdlp_version():
    """Log one warning if yt-dlp is below the minimum version; return ok: bool.
    Never fatal and never blocks downloads."""
    global _version_checked
    ver = _ytdlp_version_tuple()
    if ver is not None and ver >= YTDLP_VERSION_FLOOR:
        return True
    if not _version_checked:
        _version_checked = True
        try:
            current_app.logger.warning(
                "yt-dlp %s < recommended minimum %s (CVE-2026-50019/55404). "
                "Update: python -m pip install -U yt-dlp",
                ver, YTDLP_VERSION_FLOOR,
            )
        except Exception:
            pass
    return False


def _ip_is_blocked(ip):
    """Whether `ip` (ipaddress) targets non-public network space.

    Unwrap IPv4-mapped IPv6 and 6to4 before classification to block private
    IPv4 addresses encoded as IPv6."""
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
    return (ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _resolve_public_ips(host, port):
    """Resolve `host` and validate EVERY IP. Return (frozenset[str], error).

    Any non-public IP returns (None, message). Called only once during
    _validate_public_http_url, not again before spawning gallery-dl/yt-dlp.
    See that function for the resulting DNS-rebinding window."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return None, "Host not found (DNS)."
    except Exception:
        return None, "Could not resolve host."

    ips = set()
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return None, "Invalid IP address."
        if _ip_is_blocked(ip):
            return None, "This URL points to an internal network address (blocked)."
        ips.add(str(ip))
    if not ips:
        return None, "Host not found (DNS)."
    return frozenset(ips), None


def _validate_public_http_url(url):
    """Validate that `url` is public HTTP(S), as an anti-SSRF check.

    Reject other schemes and hosts resolving to non-public addresses:
    loopback, private, link-local, reserved, multicast and IPv4-mapped IPv6.
    Return (ok: bool, error: str|None).

    The host is resolved and classified only once. These IPs are not retained
    or reused: gallery-dl/yt-dlp perform their own DNS lookup when connecting.
    DNS rebinding between the lookups, or redirects followed by those tools
    to internal IPs, are not intercepted here. No lookup occurs immediately
    before spawn. Closing this window requires an external egress proxy
    validating each connection or an OS firewall blocking private ranges
    for the process; netfetch.py alone cannot guarantee this."""
    if not url or not isinstance(url, str):
        return False, "Missing URL."
    url = url.strip()
    if len(url) > 2048:
        return False, "URL too long."
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL."
    if parsed.scheme not in ('http', 'https'):
        return False, "Only http(s) URLs are allowed."
    host = parsed.hostname
    if not host:
        return False, "URL without a valid host."

    _ips, err = _resolve_public_ips(host, parsed.port or (443 if parsed.scheme == 'https' else 80))
    if err:
        return False, err
    return True, None


def _download_with_ytdlp(url, dest_template):
    """Run `python -m yt_dlp` in a subprocess. Return (ok, error)."""
    _check_ytdlp_version()   # Non-blocking warning if the version is too old
    if _ffmpeg_available():
        fmt_args = ['-f', 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b',
                    '--merge-output-format', 'mp4']
    else:
        fmt_args = ['-f', 'best[ext=mp4]/mp4/best']   # Legacy single stream (no muxing).
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--ignore-config',          # Never load yt-dlp.conf (blocks planted exec/--netrc-cmd options).
        '--no-playlist',
        '--no-warnings',
        '--quiet',
        '--no-part',
        '--no-continue',
        '--max-filesize', str(MAX_DRIVER_BYTES),
        '--socket-timeout', str(network_timeout(SOCKET_TIMEOUT)),
        *fmt_args,
        '-o', dest_template,
        '--', url,
    ]
    quarantine = None
    try:
        quarantine = tempfile.mkdtemp(prefix='scrape_ytdlp_')
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=network_timeout(DOWNLOAD_TIMEOUT),
            cwd=quarantine,   # Isolated cwd: planted files such as ffmpeg.exe cannot land in COMFYUI_OUTPUT_DIR.
        )
    except subprocess.TimeoutExpired:
        return False, "Download timed out."
    except FileNotFoundError:
        current_app.logger.error("yt-dlp introuvable (python -m yt_dlp).")
        return False, "yt-dlp not available on the server."
    except Exception as e:
        current_app.logger.error(f"yt-dlp launch failed: {e}")
        return False, "Internal download error."
    finally:
        if quarantine:
            shutil.rmtree(quarantine, ignore_errors=True)

    if result.returncode != 0:
        # Do not return raw stderr (it can leak paths); log it only.
        current_app.logger.warning(
            f"yt-dlp failed (rc={result.returncode}) for {url[:120]}: "
            f"{(result.stderr or '')[:500]}"
        )
        return False, "Download failed (unsupported or unavailable URL)."
    return True, None


def _looks_like_image(path):
    """Whether `path` starts with a known raster signature (jpg/png/bmp/gif/webp/avif).
    Exclude SVG, which can contain scripts. MIME types/extensions can be forged."""
    try:
        with open(path, 'rb') as f:
            head = f.read(32)
    except OSError:
        return False
    if len(head) < 12:
        return False
    if head[:3] == b'\xff\xd8\xff':                       # jpeg
        return True
    if head[:8] == b'\x89PNG\r\n\x1a\n':                  # png
        return True
    if head[:2] == b'BM':                                  # bmp
        return True
    if head[:4] == b'GIF8':                               # gif
        return True
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':     # webp
        return True
    if head[4:8] == b'ftyp' and head[8:12] in (b'avif', b'avis'):  # avif
        return True
    return False


def _looks_like_video(path):
    """Whether `path` starts with a known video signature
    (mp4/mov/m4v, mkv/webm, avi, gif, mpeg PS/ES/TS).

    Local counterpart of the source app video validator. Importing its missing
    upload module used to raise ImportError on every real call, hidden by
    upstream test mocks. Inspect only header bytes, since extensions and
    content types can be forged.

    Note: ftyp includes the whole ISO-BMFF family, including AVIF/HEIC, and
    GIF8 is also a raster signature. This therefore accepts AVIF and GIF as
    video. Maintaining a complete image-brand list is impractical; callers
    that also accept images must test images FIRST (_validate_media_file)."""
    try:
        with open(path, 'rb') as f:
            head = f.read(512)   # 512 bytes cover the three TS sync bytes at offsets 0, 188 and 376.
    except OSError:
        return False
    if len(head) < 12:
        return False
    if head[4:8] == b'ftyp':                              # mp4 / mov / m4v / 3gp (ISO-BMFF)
        return True
    if head[:4] == b'\x1a\x45\xdf\xa3':                   # EBML : mkv / webm
        return True
    if head[:4] == b'RIFF' and head[8:12] == b'AVI ':     # avi
        return True
    if head[:4] == b'GIF8':                               # gif
        return True
    if head[:4] in (b'\x00\x00\x01\xba',                  # mpeg program stream (pack header)
                    b'\x00\x00\x01\xb3'):                 # mpeg-1/2 video (sequence header)
        return True
    # MPEG-TS has no header magic, but a 0x47 sync byte every 188 bytes.
    # One 0x47 proves nothing (any file starting with G); require three.
    if len(head) > 376 and head[0] == 0x47 and head[188] == 0x47 and head[376] == 0x47:
        return True
    return False


import os as _os
import glob as _glob


def download_via_ytdlp(url, dest_base):
    """Download with yt-dlp into the dest_base directory; keep the first valid video.
    Return (ok, filename|None, error|None). Never raises."""
    dest_dir = _os.path.dirname(dest_base)
    uid = _os.path.basename(dest_base)
    _os.makedirs(dest_dir, exist_ok=True)
    dest_template = _os.path.join(dest_dir, f'{uid}.%(ext)s')
    ok, err = _download_with_ytdlp(url, dest_template)
    if not ok:
        for stray in _glob.glob(_os.path.join(dest_dir, f'{uid}.*')):
            try: _os.remove(stray)
            except OSError: pass
        return False, None, err
    produced = sorted(_glob.glob(_os.path.join(dest_dir, f'{uid}.*')))
    final = None
    for p in produced:
        if final is None and _looks_like_video(p):
            final = p
        else:
            try: _os.remove(p)
            except OSError: pass
    if final is None:
        return False, None, "The downloaded file is not a valid video."
    return True, _os.path.basename(final), None


def fetch_hardened_bytes(url, *, allowed_types, max_bytes, require_image_magic=False):
    """Fetch a media URL into memory with the same security checks as /thumb.

    Return (ok, data|None, ctype|None, reason), where reason is a short code
    (redirect/status/type/toolarge/fetch/noimage/no_curl) for counting skips.

    Guarantees matching /thumb:
    - The caller must already have validated the URL with _validate_public_http_url.
    - Use curl_cffi impersonate=chrome and a Referer from the source host.
    - Disable redirects: any 3xx fails, preventing redirect bypass of SSRF checks.
    - Restrict content type to allowed_types (callers never allow image/svg+xml).
    - Cap bytes while streaming, before reading the entire body.
    - With require_image_magic, require a known raster signature as well, so
      non-admins receive real images rather than disguised HTML/SVG/executables."""
    try:
        from curl_cffi import requests as cf_requests
    except ImportError:
        return False, None, None, 'no_curl'
    host = urlparse(url).hostname or ''
    try:
        r = cf_requests.get(url, impersonate='chrome', timeout=network_timeout(20), stream=True,
                            allow_redirects=False,
                            headers={'Referer': f'https://{host}/', 'Accept': '*/*'})
    except Exception as e:
        try:
            current_app.logger.warning(f"fetch_hardened_bytes failed {url[:120]}: {e}")
        except Exception:
            pass
        return False, None, None, 'fetch'
    if 300 <= r.status_code < 400:
        try: r.close()
        except Exception: pass
        return False, None, None, 'redirect'
    ctype = (r.headers.get('content-type') or '').split(';')[0].strip().lower()
    if r.status_code != 200 or ctype not in allowed_types:
        try: r.close()
        except Exception: pass
        return False, None, None, ('status' if r.status_code != 200 else 'type')
    data = bytearray()
    try:
        for chunk in r.iter_content(8192):
            if not chunk:
                continue
            data += chunk
            if len(data) > max_bytes:
                try: r.close()
                except Exception: pass
                return False, None, None, 'toolarge'
    finally:
        try: r.close()
        except Exception: pass
    # Validate raster magic bytes: an image/* content type can be forged.
    if require_image_magic and not _bytes_look_like_image(bytes(data[:32])):
        return False, None, None, 'noimage'
    return True, bytes(data), ctype, 'ok'


# Raster signatures accepted from in-memory bytes, mirroring the file-based
# _looks_like_image. Exclude SVG, which can contain scripts.
def _bytes_look_like_image(head):
    if len(head) < 12:
        return False
    if head[:3] == b'\xff\xd8\xff':                       # jpeg
        return True
    if head[:8] == b'\x89PNG\r\n\x1a\n':                  # png
        return True
    if head[:2] == b'BM':                                  # bmp
        return True
    if head[:4] == b'GIF8':                               # gif
        return True
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':     # webp
        return True
    if head[4:8] == b'ftyp' and head[8:12] in (b'avif', b'avis'):  # avif
        return True
    return False


def _validate_media_file(path, *, allow_image=True):
    """Validate real media using magic bytes.

    Return (ok, kind), with kind in {video, image} on success, else (False, None).
    Reject HTML/SVG/ZIP/executables/shortcuts regardless of URL extension.
    allow_image=False accepts videos only (the SCAIL driver path)."""
    # Test images BEFORE videos: _looks_like_video matches all ftyp (including
    # AVIF) and GIF8 signatures. Without this order, AVIF/GIF images become video.
    # Pinned by test_netfetch_video_magic.py.
    if _looks_like_image(path):
        return (True, 'image') if allow_image else (False, None)
    # Hardened local video validation (mp4/mov/webm/mkv/avi/gif/mpeg).
    if _looks_like_video(path):
        return True, 'video'
    return False, None
