# app/scrape/sources/instagram.py
"""Instagram scraper: enumerate profile, post and reel media.

Standalone port of redgifs_downloader/api/instagram.py, limited to this app's
needs. It has no config/settings or global-instance dependency; SCAN_LIMIT and
PROFILE_SCAN_TIMEOUT are local constants. Authentication reuses an on-disk
Instaloader session or imports browser cookies through browser_cookie3.
Authentication, 403, rate-limit and login errors return (None, message).
scan() never raises.

Shared source contract:
    scan(validation) -> (items, error)
    items: list[dict] with at most SCAN_LIMIT entries, or None on error
    error: str|None, containing a short English explanation

Item schema:
    {'url', 'title', 'thumbnail' (str|None), 'type' ('video'|'image'),
     'platform' ('instagram')}

Returned URLs identify stable Instagram post/reel pages accepted by the
yt-dlp download path with browser cookies, rather than expiring signed CDN URLs."""
import time
import logging
from pathlib import Path

from .base import ResultList
from .gdl import GdlError

try:
    import instaloader
    INSTALOADER_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency unavailable
    instaloader = None
    INSTALOADER_AVAILABLE = False

try:
    import browser_cookie3
    BROWSER_COOKIE3_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency unavailable
    browser_cookie3 = None
    BROWSER_COOKIE3_AVAILABLE = False

logger = logging.getLogger(__name__)

# Self-contained constants; no settings reads.
SCAN_LIMIT = 50               # hard limit on returned items
PROFILE_SCAN_TIMEOUT = 60     # seconds: total profile-scan budget
SESSION_TIMEOUT = 10          # seconds: Instaloader session HTTP timeout

# One error message covers Instagram authentication, 403 and rate-limit refusals.
_AUTH_ERROR = "Instagram blocked access (login required / rate-limit)."

# Exception-message fragments indicating anti-bot blocking.
_BLOCK_HINTS = ("429", "403", "forbidden", "too many", "login", "rate", "checkpoint")


# --------------------------------------------------------------------------- #
# Auth — session instaloader + auto-import cookies navigateur.
# --------------------------------------------------------------------------- #
def _detect_session_username():
    """Find an existing Instaloader session file on disk.

    Instaloader stores sessions under ~/.config/instaloader/session-USER.
    Return its associated username, or None if no session is found."""
    try:
        config_dir = Path.home() / ".config" / "instaloader"
        if config_dir.exists():
            for f in config_dir.iterdir():
                if f.name.startswith("session-"):
                    username = f.name[len("session-"):]
                    if username:
                        logger.info("Instagram session detected: %s", username)
                        return username
    except Exception as e:  # pragma: no cover - I/O improbable en test
        logger.debug("Instagram session detection failed: %s", e)
    return None


def _auto_import_browser_cookies(loader):
    """Import Instagram browser cookies, trying Firefox then Chrome.

    Return True when a sessionid login cookie was imported. Never raises;
    return False for any failure."""
    if not BROWSER_COOKIE3_AVAILABLE:
        return False

    for browser_name, browser_fn in (
        ("Firefox", browser_cookie3.firefox),
        ("Chrome", browser_cookie3.chrome),
    ):
        try:
            cookie_list = list(browser_fn(domain_name="instagram.com"))
            if not cookie_list:
                continue
            # The sessionid cookie indicates a logged-in session.
            if not any(c.name == "sessionid" for c in cookie_list):
                logger.debug("%s: cookies found without a sessionid", browser_name)
                continue
            session = loader.context._session
            for cookie in cookie_list:
                session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
            logger.info("Auto-imported %s cookies: %d cookies (sessionid present)",
                        browser_name, len(cookie_list))
            return True
        except Exception as e:
            logger.debug("Auto-import from %s failed: %s", browser_name, e)
            continue
    return False


def _build_loader():
    """Build an Instaloader instance using a session or browser cookies.

    Return the loader even without authentication: Instagram may allow some
    public profiles. Raises if Instaloader is unavailable."""
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
        max_connection_attempts=1,
    )
    # Use a short HTTP timeout so scans cannot hang indefinitely.
    try:
        loader.context._session.timeout = SESSION_TIMEOUT
    except (AttributeError, TypeError) as e:  # pragma: no cover
        logger.debug("Session timeout configuration failed: %s", e)

    # 1) Load an existing Instaloader session if available.
    session_loaded = False
    username = _detect_session_username()
    if username:
        try:
            loader.load_session_from_file(username)
            logger.info("Instagram session loaded: %s", username)
            session_loaded = True
        except Exception as e:
            logger.warning("Instagram session loading failed: %s", e)

    # 2) Otherwise, automatically import browser cookies.
    if not session_loaded and _auto_import_browser_cookies(loader):
        session_loaded = True

    if not session_loaded:
        logger.warning(
            "No Instagram session found (session file or browser cookies). "
            "Private or rate-limited profiles will fail."
        )
    return loader


# Map posts to shared-schema items.
def _post_page_url(shortcode):
    """Return the stable post/reel page URL accepted by yt-dlp downloads."""
    return f"https://www.instagram.com/p/{shortcode}/"


def _items_from_post(post, original_url=None):
    """Convert an instaloader.Post into shared-schema items.

    A GraphSidecar carousel can yield multiple media items. Isolate attribute
    access failures so one does not discard the entire post. When supplied,
    original_url takes precedence, preserving a user-provided /reel/ versus /p/."""
    items = []
    try:
        shortcode = post.shortcode
    except Exception:
        return items

    page_url = original_url or _post_page_url(shortcode)

    try:
        typename = post.typename
    except Exception:
        typename = None

    # Carousel: multiple image and/or video slides.
    if typename == "GraphSidecar":
        try:
            nodes = list(post.get_sidecar_nodes())
        except Exception:
            nodes = []
        for idx, node in enumerate(nodes):
            try:
                is_video = bool(node.is_video)
                thumbnail = node.display_url
            except Exception:
                continue
            items.append({
                "url": page_url,
                "title": f"Post {shortcode} (slide {idx + 1})",
                "thumbnail": thumbnail,
                "type": "video" if is_video else "image",
                "platform": "instagram",
            })
        return items

    # Single post: one image or video.
    try:
        is_video = bool(post.is_video)
        thumbnail = post.url
    except Exception:
        is_video = False
        thumbnail = None

    items.append({
        "url": page_url,
        "title": ("Reel " if is_video else "Post ") + str(shortcode),
        "thumbnail": thumbnail,
        "type": "video" if is_video else "image",
        "platform": "instagram",
    })
    return items


def _looks_like_block(exc):
    """Return whether the exception indicates anti-bot blocking (auth/403/rate limit)."""
    msg = str(exc).lower()
    return any(hint in msg for hint in _BLOCK_HINTS)


# --------------------------------------------------------------------------- #
# Scans par type d'URL.
# --------------------------------------------------------------------------- #
def _scan_profile(loader, username):
    """Enumerate the latest SCAN_LIMIT profile media and return (items, error)."""
    try:
        profile = instaloader.Profile.from_username(loader.context, username)
    except instaloader.ProfileNotExistsException:
        return None, f"Instagram profile not found: {username}."
    except Exception as e:
        # ConnectionException / LoginRequired / Forbidden / TooManyRequests / ...
        logger.warning("Profile %s loading failed: %s", username, e)
        return None, _AUTH_ERROR

    items = []
    posts_seen = 0
    posts_failed = 0
    timed_out = False
    capped = False
    started = time.time()
    try:
        for post in profile.get_posts():
            if len(items) >= SCAN_LIMIT:
                # At SCAN_LIMIT we never inspect the next post, so we cannot tell
                # whether the profile ends here or has more items. Mark it partial,
                # accepting a rare false positive for exactly SCAN_LIMIT posts,
                # as with the Picazor limit.
                capped = True
                break
            if time.time() - started > PROFILE_SCAN_TIMEOUT:
                logger.warning("Timeout scan profil %s (%ds), %d items.",
                               username, PROFILE_SCAN_TIMEOUT, len(items))
                timed_out = True
                break
            posts_seen += 1
            try:
                converted = _items_from_post(post)
            except Exception as e:
                # One broken post must not abort the entire scan.
                logger.debug("Skipped post (%s): %s", username, e)
                posts_failed += 1
                continue
            if not converted:
                # A loaded post without extractable media indicates conversion failure.
                # _items_from_post already isolates attribute errors, so count this as
                # a failed post rather than an ordinary empty result.
                posts_failed += 1
                continue
            for item in converted:
                items.append(item)
                if len(items) >= SCAN_LIMIT:
                    # The same cap was reached within a carousel: apply the same
                    # conservative partial-result policy.
                    capped = True
                    break
    except Exception as e:
        # Paginated iteration failed, commonly due to a mid-scan rate limit.
        if items:
            # Keep useful collected items, but mark the interrupted scan partial.
            # base.ResultList carries this metadata to routes without requiring
            # source-specific handling.
            logger.warning("Profile %s iteration interrupted after %d items: %s",
                           username, len(items), e)
            result = ResultList(items[:SCAN_LIMIT])
            result.partial = True
            return result, None
        logger.warning("Profile %s iteration failed: %s", username, e)
        return None, _AUTH_ERROR

    if not items:
        if timed_out:
            # Instaloader's rate controller sleeps instead of raising, so a
            # throttled profile may hit PROFILE_SCAN_TIMEOUT without any item or
            # exception. Report a failure rather than an empty profile.
            return None, (f"Instagram profile scan timed out after "
                          f"{PROFILE_SCAN_TIMEOUT}s ({posts_seen} post(s) checked, "
                          f"no media collected): {username}.")
        if posts_failed:
            # Posts were present but every conversion failed, often after an
            # Instagram layout change. This is a systematic failure, not an empty
            # profile.
            return None, (f"Instagram: {posts_failed} post(s) found for {username} "
                          f"but none could be read (layout change?).")
        # Iteration completed without an exception, timeout or failed post.
        # This is a legitimately empty public profile: use the same 'empty'
        # kind as gdl.GdlError.
        return None, GdlError(f"No media found for profile {username}.", 'empty')

    if timed_out or posts_failed or capped:
        # Timeouts, individual conversion failures or SCAN_LIMIT can leave an
        # incomplete scan. Preserve valid items and mark ResultList.partial so
        # routes do not present truncated results as complete.
        result = ResultList(items[:SCAN_LIMIT])
        result.partial = True
        return result, None
    return items[:SCAN_LIMIT], None


def _scan_single(loader, shortcode, original_url=None):
    """Fetch an individual post/reel and return (items, error)."""
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
    except instaloader.QueryReturnedNotFoundException:
        return None, f"Instagram post not found: {shortcode}."
    except Exception as e:
        logger.warning("Post %s loading failed: %s", shortcode, e)
        return None, _AUTH_ERROR

    try:
        items = _items_from_post(post, original_url=original_url)
    except Exception as e:
        logger.warning("Post %s conversion failed: %s", shortcode, e)
        return None, _AUTH_ERROR

    if not items:
        # A valid loaded post/reel has at least one media item. An empty list
        # here means every protected attribute/conversion attempt failed.
        # Report a conversion failure rather than a legitimate empty result.
        return None, f"No usable media for {shortcode}."
    return items[:SCAN_LIMIT], None


# Public entry point.
def scan(validation):
    """Enumerate downloadable media from a validated Instagram URL.

    validation uses platform, url_type, value and original_url. Supported URL
    types are PROFILE, POST and REEL. Return (items, error), where items is a
    shared-schema list of at most SCAN_LIMIT entries or None, and error is a
    short English message or None. Catch all exceptions; never raises."""
    # Import lazily to avoid a package-initialization cycle.
    from ..validators import URLType

    if not INSTALOADER_AVAILABLE:
        return None, "Instagram scraping needs the 'instaloader' package - install the scrape extras (Setup > Install everything)."

    try:
        url_type = getattr(validation, "url_type", None)
        value = getattr(validation, "value", None)
        original_url = getattr(validation, "original_url", None)

        if not value:
            return None, "Invalid Instagram URL (target not found)."

        try:
            loader = _build_loader()
        except Exception as e:
            logger.warning("Instagram loader creation failed: %s", e)
            return None, _AUTH_ERROR

        if url_type == URLType.PROFILE:
            return _scan_profile(loader, value)
        if url_type in (URLType.POST, URLType.REEL):
            return _scan_single(loader, value, original_url=original_url)

        return None, f"Unsupported Instagram URL type: {getattr(url_type, 'value', url_type)}."

    except Exception as e:
        # Final safety net: scan() must never propagate an exception.
        logger.warning("Unexpected Instagram scan error: %s", e)
        if _looks_like_block(e):
            return None, _AUTH_ERROR
        return None, "Instagram scan error."


from .base import Source, Capabilities, Match
from . import registry


class InstagramSource(Source):
    name = 'instagram'
    priority = 100
    category = 'image'   # product classification: available to non-admins
    capabilities = Capabilities(can_enumerate_profile=True, needs_auth=True, own_downloader=False)

    def match(self, url):
        from ..validators import url_validator, Platform
        result = url_validator.validate_url(url)
        if result.is_valid and result.platform == Platform.INSTAGRAM:
            return Match(url=url, validation=result)
        return None

    def scan(self, match):
        return scan(match.validation)


registry.register(InstagramSource())
