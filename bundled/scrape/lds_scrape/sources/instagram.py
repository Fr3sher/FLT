# app/scrape/sources/instagram.py
"""Instagram profile/post/reel media scraper.

Standalone port of redgifs_downloader/api/instagram.py, reduced to this
app's needs. No config/settings module or global-instance dependency;
limits are SCAN_LIMIT/PROFILE_SCAN_TIMEOUT constants. Authentication
reuses an on-disk Instaloader session, falling back to browser_cookie3.
Auth/403/rate-limit/login-required failures return a short English error
rather than raising. scan() never raises.

  * pas de dépendance au module `config`/`settings` ni à des instances globales
    (constantes en dur, voir `SCAN_LIMIT` / `PROFILE_SCAN_TIMEOUT`) ;
  * auth réutilisée du projet source : session instaloader détectée sur disque,
    sinon auto-import des cookies du navigateur via `browser_cookie3` ;
  * dégradation gracieuse : Instagram est anti-bot — toute erreur d'auth / 403 /
    rate-limit / login requis renvoie `(None, "<message FR court>")` au lieu de
    lever. `scan()` ne lève JAMAIS.

Contrat (cf. `app/scrape/sources/__init__.py`) :
    scan(validation) -> (items, error)
        items : list[dict] (≤ SCAN_LIMIT) au schéma commun, ou None si erreur ;
        error : str|None (message court FR).

Schéma d'un item :
    { 'url', 'title', 'thumbnail' (str|None), 'type' ('video'|'image'),
      'platform' ('instagram') }

L'`url` renvoyée est l'URL de la PAGE instagram.com (post/reel) : elle est
stable et acceptée par /api/scrape/download (yt-dlp + cookies navigateur), au
contraire des URLs CDN signées qui expirent vite.
"""
import functools
import json
import logging
import os
import time
import urllib.parse
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

try:
    import curl_cffi.requests as cffi_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:  # pragma: no cover - dépendance absente
    cffi_requests = None
    CURL_CFFI_AVAILABLE = False

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constantes (en dur — module autonome, aucune lecture de settings).
# --------------------------------------------------------------------------- #
SCAN_LIMIT = 100              # borne dure sur le nombre d'items retournés
_STALE_CURSOR_SKIP = SCAN_LIMIT * 5  # posts à dépasser avant d'abandonner un curseur périmé
PROFILE_SCAN_TIMEOUT = 120     # secondes — plafond global d'un scan de profil
SESSION_TIMEOUT = 20          # secondes — timeout HTTP de la session instaloader

# One error message covers Instagram authentication, 403 and rate-limit refusals.
_AUTH_ERROR = "Instagram blocked access (login required / rate-limit)."

# Cookie domaines réels capturés une fois depuis le jar requests d'origine
# (le jar curl_cffi n'expose pas les domaines via get_dict). name -> domain.
_CFFI_COOKIE_DOMAINS = {}

# Sous-chaînes signalant un blocage anti-bot dans un message d'exception.
_BLOCK_HINTS = ("429", "403", "forbidden", "too many", "login", "rate", "checkpoint")

# Sous-chaînes signalant un RATE-LIMIT (à distinguer d'un vrai blocage auth) :
# web_profile_info répond 400/401 {"fail": ..., "feedback_required", "Try Again
# Later", "Please wait a few minutes"} quand le compte est throttle. Ce n'est PAS
# un problème de login — c'est un refus anti-bot temporaire.
_THROTTLE_HINTS = (
    "429", "401", "400", "fail", "feedback_required", "try again later",
    "please wait a few minutes", "too many requests", "rate-limit", "rate limit",
    "spam",
)

# Backoff (secondes) entre tentatives d'un fetch de profil throttlé. Progressif :
# 15s, 30s, 60s, 60s — on laisse le throttle refroidir au lieu de marteler.
# Un scan échoué renvoie le message honnête "attends ~10 min" plutôt que le
# trompeur _AUTH_ERROR.
_RETRY_BACKOFFS = (15, 30, 60, 60)


def _is_throttle(error) -> bool:
    """True si l'exception signale un rate-limit Instagram (pas un vrai blocage auth)."""
    msg = str(error or "").lower()
    return any(h in msg for h in _THROTTLE_HINTS)


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
    except Exception as e:  # pragma: no cover - I/O unlikely in tests
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
                logger.debug("%s: cookies found but no sessionid", browser_name)
                continue
            session = loader.context._session
            for cookie in cookie_list:
                session.cookies.set(cookie.name, cookie.value, domain=cookie.domain)
            logger.info("Auto-imported cookies from %s: %d cookies (sessionid present)",
                        browser_name, len(cookie_list))
            return True
        except Exception as e:
            logger.debug("Auto-import from %s failed: %s", browser_name, e)
            continue
    return False


def _cffi_session_from(session, timeout):
    """Clone un session requests/instaloader vers une session curl_cffi
    (impersonation Chrome) en préservant headers + cookies."""
    c = cffi_requests.Session(impersonate='chrome')
    h = dict(session.headers.items()) if hasattr(session.headers, 'items') else dict(session.headers)
    c.headers.update(h)
    c.headers.setdefault('Connection', 'keep-alive')
    # Cookies : le jar requests itère des objets ; le jar curl_cffi itère des
    # chaînes (pas de .name/.domain) → on passe par get_dict() dans ce cas.
    try:
        ck_iter = list(session.cookies)
    except Exception:
        ck_iter = []
    if ck_iter and not hasattr(ck_iter[0], 'name'):
        for name, value in session.cookies.get_dict().items():
            c.cookies.set(name, value, domain=_CFFI_COOKIE_DOMAINS.get(name, 'www.instagram.com'))
    else:
        for ck in ck_iter:
            c.cookies.set(ck.name, ck.value, domain=ck.domain or _CFFI_COOKIE_DOMAINS.get(ck.name, 'www.instagram.com'))
    c.request = functools.partial(c.request, timeout=timeout)
    return c


def _cffi_copy_session(session, request_timeout):
    """Remplaçant de instaloader.context.copy_session — clone curl_cffi."""
    return _cffi_session_from(session, request_timeout or SESSION_TIMEOUT)


def _csrf_token(session):
    """Lit le jeton csrftoken d'une session, quel que soit le type de cookies.

    requests itère des objets (``c.name``/``c.value``) ; curl_cffi itère des
    chaînes. On passe d'abord par ``cookies.get()`` (disponible dans les deux
    cas), puis on retombe sur l'itération objets si besoin.
    """
    cookies = getattr(session, 'cookies', None)
    get = getattr(cookies, 'get', None)
    if get is not None:
        try:
            token = get('csrftoken')
            if token:
                return token
        except Exception:
            pass
    try:
        return next((c.value for c in cookies
                     if c.name == 'csrftoken' and c.value), '')
    except Exception:
        return ''


def _doc_id_graphql_query(self, doc_id, variables, referer=None):
    """Replacement de InstaloaderContext.doc_id_graphql_query.

    L'original fait ``next(c.value for c in self._session.cookies if c.name…)``
    : avec une session curl_cffi, ``cookies`` itère des chaînes → AttributeError
    ``'str' object has no attribute 'name'`` (le scan échoue sur get_posts()).
    On lit le csrftoken via ``_csrf_token`` et on conserve le reste à l'identique.
    """
    import instaloader.instaloadercontext as ictx
    csrf = _csrf_token(self._session)
    if not csrf:
        self._session.get('https://www.instagram.com/',
                          timeout=self.request_timeout)
        csrf = _csrf_token(self._session)
    with ictx.copy_session(self._session, self.request_timeout) as tmpsession:
        tmpsession.headers.update(self._default_http_header(empty_session_only=True))
        del tmpsession.headers['Connection']
        del tmpsession.headers['Content-Length']
        tmpsession.headers['authority'] = 'www.instagram.com'
        tmpsession.headers['scheme'] = 'https'
        tmpsession.headers['accept'] = '*/*'
        tmpsession.headers['x-csrftoken'] = csrf
        if referer is not None:
            tmpsession.headers['referer'] = urllib.parse.quote(referer)
        variables_json = json.dumps(variables, separators=(',', ':'))
        resp_json = self.get_json(
            'graphql/query',
            params={'variables': variables_json,
                    'doc_id': doc_id,
                    'server_timestamps': 'true'},
            session=tmpsession,
            use_post=True)
    if 'status' not in resp_json:
        self.error("GraphQL response did not contain a \"status\" field.")
    return resp_json


def _impersonate_loader(loader):
    """Remplace la session requests du loader par une session curl_cffi
    (TLS-fingerprint Chrome) et monkeypatche copy_session d'instaloader pour
    que chaque requête GraphQL utilise la même impersonation.

    Doit tourner APRÈS le chargement session/cookies (load_session_from_file
    remplace self._session par une requests.Session neuve). Sans curl_cffi
    installé : no-op, on garde le comportement actuel (requests simple).
    """
    if not CURL_CFFI_AVAILABLE:
        return
    src = loader.context._session
    # Capture les vrais domaines une seule fois depuis le jar requests d'origine.
    try:
        for ck in src.cookies:
            if hasattr(ck, 'name') and ck.domain:
                _CFFI_COOKIE_DOMAINS[ck.name] = ck.domain
    except Exception:
        pass
    loader.context._session = _cffi_session_from(
        src, getattr(loader.context._session, "timeout", SESSION_TIMEOUT)
    )
    import instaloader.instaloadercontext as ictx
    ictx.copy_session = _cffi_copy_session
    ictx.InstaloaderContext.doc_id_graphql_query = _doc_id_graphql_query
    logger.info("Instagram : session curl_cffi (impersonate chrome) active")


class _FastRateController(instaloader.RateController if instaloader else object):
    """Rate-controller qui ne dort jamais 666 s sur un 429.

    ``handle_429`` d'instaloader calcule ``query_waittime`` → 666 s
    (``untracked_next_request_time`` = timestamp de la requête + 666) puis
    appelle ``sleep(666)`` avant CHAQUE tentative, ``max_connection_attempts``
    fois : c'est exactement ce qui pend un scan 13–16 min dès qu'Instagram
    répond 429 (le premier hit, sur le fingerprint TLS non-impersonné, suffit).
    On borne le sleep à ``MAX_BACKOFF`` pour ne jamais bloquer : un 429 est
    retenté tout de suite au lieu d'attendre 11 min.
    """

    MAX_BACKOFF = 30.0  # secondes max de backoff par réponse 429 (wait au lieu de marteler)

    def sleep(self, secs):
        time.sleep(min(secs, self.MAX_BACKOFF))


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
        rate_controller=lambda ctx: _FastRateController(ctx),
        max_connection_attempts=3,
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
            logger.warning("Instagram session load failed: %s", e)

    # 2) Otherwise import browser cookies automatically.
    if not session_loaded and _auto_import_browser_cookies(loader):
        session_loaded = True

    if not session_loaded:
        logger.warning(
            "No Instagram session (neither file nor browser cookies). "
            "Private profiles / rate-limited requests will fail."
        )
    # 3) Impersonation curl_cffi (après chargement session/cookies) :
    #    le TLS-fingerprint Chrome évite le 429 anti-bot d'Instagram.
    try:
        _impersonate_loader(loader)
    except Exception as e:
        logger.warning("Impersonation curl_cffi échouée : %s", e)
    return loader


# --------------------------------------------------------------------------- #
# Curseur de reprise (auto-resume des scans de profil).
#
# Le module est autonome (pas d'import `config`), on résout donc le répertoire
# de données depuis l'environnement : `LDS_DATA_DIR` (le volume monté dans le
# conteneur, cf. docker-compose), sinon `backend/`, sinon un défaut local. Le
# curseur n'est qu'un point de reprise : un `shortcode` (dernier post renvoyé)
# par nom de profil. Jamais levé — tout échec de lecture/écriture est absorbé
# et le scan repart du haut.
# --------------------------------------------------------------------------- #
def _data_dir():
    env = os.environ.get('LDS_DATA_DIR')
    if env:
        return Path(env)
    # Match the pre-v2 cursor location so an existing scan resumes in place.
    return Path(__file__).resolve().parents[4] / 'backend' / 'data'


def _cursor_path():
    return _data_dir() / 'instagram_cursor.json'


def _load_cursor(username):
    try:
        with open(_cursor_path(), 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get(username)
    except Exception as e:
        logger.debug("Lecture curseur Instagram échouée : %s", e)
        return None


def _save_cursor(username, shortcode):
    try:
        path = _cursor_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                data = {}
        data[username] = shortcode
        path.write_text(json.dumps(data), encoding='utf-8')
    except Exception as e:
        logger.debug("Écriture curseur Instagram échouée : %s", e)


# --------------------------------------------------------------------------- #
# Helpers de mapping post -> item(s) du schéma commun.
# --------------------------------------------------------------------------- #
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
def _scan_profile(loader, username, resume_from=None, save_cursor=False):
    """Énumère les SCAN_LIMIT derniers médias d'un profil. Retourne (items, error).

    `resume_from` : shortcode d'un post déjà renvoyé lors d'un scan précédent —
    on continue l'énumération APRÈS lui (auto-resume, pas de re-téléchargement
    des posts déjà collectés). None = scan frais depuis le haut. `save_cursor` :
    si True, on persiste le dernier shortcode renvoyé sur disque pour permettre
    une reprise ultérieure."""
    # Fetch du profil avec retry anti-throttle : web_profile_info répond 400/401
    # "fail"/"feedback_required"/"Try Again Later" quand le compte est rate-limité.
    # On laisse le throttle refroidir (backoff progressif) au lieu de marteler, et
    # on renvoie le message honnête si le refus persiste — jamais le trompeur
    # _AUTH_ERROR qui fait croire à un problème de login.
    profile = None
    attempts = 1 + len(_RETRY_BACKOFFS)
    for attempt in range(attempts):
        try:
            profile = instaloader.Profile.from_username(loader.context, username)
            break
        except instaloader.ProfileNotExistsException:
            return None, f"Instagram profile not found: {username}."
        except instaloader.TooManyRequestsException:
            logger.warning("Instagram rate-limit sur le profil %s", username)
        except Exception as e:
            if _is_throttle(e):
                logger.warning("Instagram rate-limit sur le profil %s : %s",
                               username, e)
            else:
                # ConnectionException / LoginRequired / Forbidden / ... (vrai blocage).
                logger.warning("Chargement profil %s échoué : %s", username, e)
                return None, _AUTH_ERROR
        if attempt < len(_RETRY_BACKOFFS):
            wait = _RETRY_BACKOFFS[attempt]
            logger.warning("Instagram rate-limit %s, nouvelle tentative dans %ds",
                           username, wait)
            time.sleep(wait)
    if profile is None:
        return None, ("Instagram rate-limit: trop de requêtes. "
                      "Attends ~10 min avant de relancer le scan.")

    items = []
    posts_seen = 0
    posts_failed = 0
    timed_out = False
    capped = False
    scan_timeout = PROFILE_SCAN_TIMEOUT
    started = time.time()
    posts_iter = profile.get_posts()
    if resume_from:
        # Avance l'itérateur jusqu'au post curseur (sans le renvoyer : le
        # `break` le consomme, la boucle principale continue après lui). Seul
        # `shortcode` est lu ici (champ node_dict bon marché, aucun appel réseau).
        skipped = 0
        resuming = True
        for post in posts_iter:
            if getattr(post, 'shortcode', None) == resume_from:
                resuming = False
                break
            skipped += 1
            if skipped > _STALE_CURSOR_SKIP:
                break
        if resuming:
            if skipped > _STALE_CURSOR_SKIP:
                # Curseur trop vieux (profil réorganisé / posts supprimés) : on
                # repart proprement du haut plutôt que de boucler dans le vide.
                logger.warning("Curseur Instagram %s périmé, reprise du haut.",
                               resume_from)
                posts_iter = profile.get_posts()
            else:
                # Le profil a moins de posts que le curseur : plus rien à renvoyer.
                posts_iter = iter(())
    try:
        last_shortcode = None
        for post in posts_iter:
            if len(items) >= SCAN_LIMIT:
                # At SCAN_LIMIT we never inspect the next post, so we cannot tell
                # whether the profile ends here or has more items. Mark it partial,
                # accepting a rare false positive for exactly SCAN_LIMIT posts,
                # as with the Picazor limit.
                capped = True
                break
            if time.time() - started > scan_timeout:
                logger.warning("Profile scan timeout for %s (%ds), %d items.",
                               username, scan_timeout, len(items))
                timed_out = True
                break
            posts_seen += 1
            try:
                converted = _items_from_post(post)
            except Exception as e:
                # One broken post must not abort the entire scan.
                logger.debug("Post skipped (%s): %s", username, e)
                posts_failed += 1
                continue
            if not converted:
                # A loaded post without extractable media indicates conversion failure.
                # _items_from_post already isolates attribute errors, so count this as
                # a failed post rather than an ordinary empty result.
                posts_failed += 1
                continue
            last_shortcode = post.shortcode
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
            result.partial_reason = 'interrupted'
            if save_cursor and last_shortcode:
                _save_cursor(username, last_shortcode)
            return result, None
        logger.warning("Profile %s iteration failed: %s", username, e)
        return None, _AUTH_ERROR

    if save_cursor and last_shortcode:
        _save_cursor(username, last_shortcode)

    if not items:
        if timed_out:
            # Instaloader's rate controller sleeps instead of raising, so a
            # throttled profile may hit PROFILE_SCAN_TIMEOUT without any item or
            # exception. Report a failure rather than an empty profile.
            return None, (f"Instagram profile scan timed out after "
                          f"{scan_timeout}s ({posts_seen} post(s) checked, "
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
        # Priority: a timeout or conversion failures are real problems; the
        # plain hard-cap (`capped`) is expected for any profile with more than
        # SCAN_LIMIT posts, so the UI can show it calmly rather than as a fault.
        if timed_out:
            result.partial_reason = 'timed_out'
        elif posts_failed:
            result.partial_reason = 'posts_failed'
        elif capped:
            result.partial_reason = 'capped'
        return result, None
    return items[:SCAN_LIMIT], None


def _scan_single(loader, shortcode, original_url=None):
    """Fetch an individual post/reel and return (items, error)."""
    try:
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
    except instaloader.QueryReturnedNotFoundException:
        return None, f"Instagram post not found: {shortcode}."
    except instaloader.TooManyRequestsException:
        logger.warning("Instagram rate-limit sur le post %s", shortcode)
        return None, ("Instagram rate-limit: trop de requêtes. "
                      "Attends ~10 min avant de relancer.")
    except Exception as e:
        logger.warning("Post %s load failed: %s", shortcode, e)
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


# --------------------------------------------------------------------------- #
# Point d'entrée public.
# --------------------------------------------------------------------------- #
def scan(validation, resume=False, save_cursor=False):
    """Énumère les médias téléchargeables d'une URL Instagram validée.

    `validation` : ValidationResult (champs utilisés : platform, url_type,
    value, original_url). Gère url_type PROFILE / POST / REEL.

    `resume` : pour un PROFILE, reprend l'énumération après le dernier post
    déjà renvoyé (curseur persistant) au lieu de repartir du haut. `save_cursor`
    : si True, on persiste la position de reprise après le scan de profil.

    Retourne (items, error) :
      * items : list[dict] (≤ SCAN_LIMIT) au schéma commun, ou None si erreur ;
      * error : str|None (message court FR).

    Ne lève JAMAIS : toute exception est capturée → (None, "<message>").
    """
    # Import paresseux pour éviter un cycle d'import au chargement du package.
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
            resume_from = _load_cursor(value) if resume else None
            return _scan_profile(loader, value, resume_from=resume_from,
                                 save_cursor=save_cursor)
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
        fresh = bool(getattr(match, 'fresh', False))
        # Un scan de profil est toujours « paginable » : chaque appel continue
        # après le dernier post renvoyé (auto-resume), sauf `fresh` qui repart
        # du haut. On le signale à la route pour que le bouton « Charger plus »
        # reste actif jusqu'au plafond de page.
        match.paginated = True
        return scan(match.validation, resume=not fresh, save_cursor=True)


registry.register(InstagramSource())
