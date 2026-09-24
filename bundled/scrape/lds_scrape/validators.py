# app/scrape/validators.py
"""Scraping URL validation: platform and URL-type detection.

A near-identical port of redgifs_downloader/api/validators.py using only the
standard library, with no network dependencies. Detect RedGifs, Instagram
and Picazor; delegate other HTTP(S) domains to yt-dlp (Platform.GENERIC)."""
import re
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import unquote, urlparse


class Platform(Enum):
    REDGIFS = "redgifs"
    INSTAGRAM = "instagram"
    PICAZOR = "picazor"
    EROME = "erome"
    # These dump/leak platforms were deliberately removed. Retain the four
    # members only so detect_platform() can recognize their hosts and
    # validate_url() can explicitly name and reject them (_REMOVED_PLATFORMS).
    # No source, scan or download may handle them.
    COOMER = "coomer"
    KEMONO = "kemono"
    BUNKR = "bunkr"
    CYBERDROP = "cyberdrop"
    X = "x"
    TIKTOK = "tiktok"
    # Category-based photo site enumerated through gallery-dl; anime/drawing boorus are out of scope.
    PORNPICS = "pornpics"
    # Civitai (.com/.red): image listings by tag/search, e.g. /images?tags=5169.
    # Direct images are enumerated through gallery-dl.
    CIVITAI = "civitai"
    # Fapello and its language mirrors: each model page queues posts containing
    # one direct media item each, enumerated through gallery-dl.
    FAPELLO = "fapello"
    # Reddit: subreddits, posts and /s/ share links, including amateur photos
    # such as outfit checks and photo dumps for style/concept datasets.
    REDDIT = "reddit"
    # Sex.com: adult pinboards, with one image per pin. Keyword search uses
    # the site's JSON API; pins and boards use gallery-dl.
    SEXCOM = "sexcom"
    # Pexels: SFW search, accessible collections and photos through the official
    # API (PEXELS_API_KEY required). Profiles are not exposed.
    PEXELS = "pexels"
    GENERIC = "generic"   # any other HTTP(S) URL, delegated to yt-dlp
    UNKNOWN = "unknown"


# Removed dump/leak platforms are explicitly rejected by validate_url()
# before source resolution. Never route these members to any dedicated or
# generic scan/download implementation.
_REMOVED_PLATFORMS = frozenset({
    Platform.COOMER, Platform.KEMONO, Platform.BUNKR, Platform.CYBERDROP,
})


class URLType(Enum):
    PROFILE = "profile"
    VIDEO = "video"
    POST = "post"
    REEL = "reel"
    NICHE = "niche"
    LISTING = "listing"
    UNKNOWN = "unknown"


@dataclass
class ValidationResult:
    is_valid: bool
    platform: Platform
    url_type: URLType
    value: str               # username, video_id, etc.
    original_url: str
    error: Optional[str] = None
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to JSON-safe API response data."""
        return {
            'is_valid': self.is_valid,
            'platform': self.platform.value,
            'url_type': self.url_type.value,
            'value': self.value,
            'original_url': self.original_url,
            'error': self.error,
            'suggestions': self.suggestions,
        }


@dataclass(frozen=True)
class PexelsRoute:
    """A strictly recognized public Pexels route.

    value retains the public segment for ValidationResult; api_value holds the
    decoded, validated value sent to the API. Only localized searches carry an
    api_locale parameter."""
    kind: str
    value: str
    api_value: str
    api_locale: Optional[str] = None


_PEXELS_SEARCH_ROUTES = {
    None: ('search', None),
    'en-us': ('search', 'en-US'),
    'fr-fr': ('chercher', 'fr-FR'),
}


def parse_pexels_path(path: str) -> Optional[PexelsRoute]:
    """Parse only public routes that map to the Pexels API.

    Accepted localized prefixes are deliberately limited to tested variants.
    Unknown routes or locales never become fallback searches."""
    if not isinstance(path, str) or not re.fullmatch(
            r'/[^/]+(?:/[^/]+){1,2}/?', path):
        return None

    parts = path[1:-1] if path.endswith('/') else path[1:]
    segments = parts.split('/')
    locale = segments.pop(0) if segments[0] in _PEXELS_SEARCH_ROUTES else None
    if len(segments) != 2:
        return None

    route_name, public_value = segments
    if re.search(r'%(?![0-9A-Fa-f]{2})', public_value):
        return None
    decoded_value = unquote(public_value)
    if (not decoded_value.strip()
            or any(char in decoded_value for char in ('/', '\\'))
            or any(ord(char) < 32 or ord(char) == 127 for char in decoded_value)):
        return None

    expected_search, api_locale = _PEXELS_SEARCH_ROUTES[locale]
    if route_name == expected_search:
        return PexelsRoute('search', public_value, decoded_value, api_locale)

    if route_name == 'collections':
        if not re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', decoded_value):
            return None
        collection_id = decoded_value.rsplit('-', 1)[-1]
        return PexelsRoute('collection', public_value, collection_id)

    if route_name == 'photo':
        match = re.fullmatch(
            r'(?:[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*-)?(\d+)', decoded_value)
        if match:
            return PexelsRoute('photo', public_value, match.group(1))

    return None


class URLValidator:
    """Validateur d'URLs : plateforme + type + valeur extraite."""

    PATTERNS = {
        Platform.REDGIFS: {
            "user": [
                r'redgifs\.com/users/([^/?]+)',
                r'redgifs\.com/@([^/?]+)',
            ],
            "video": [
                r'redgifs\.com/watch/([^/?]+)',
                r'redgifs\.com/([a-zA-Z]+)$',
            ],
            "niche": [
                r'redgifs\.com/niches/([^/?]+)',
            ],
        },
        Platform.INSTAGRAM: {
            "profile": [
                r'instagram\.com/([^/?]+)/?$',
                r'instagram\.com/([^/?]+)/reels',
            ],
            "post": [
                r'instagram\.com/p/([^/?]+)',
                r'instagram\.com/([^/]+)/p/([^/?]+)',
            ],
            "reel": [
                r'instagram\.com/reel/([^/?]+)',
                r'instagram\.com/([^/]+)/reel/([^/?]+)',
            ],
        },
        Platform.PICAZOR: {
            # /fr/{creator}/{N} is the detail page for media N, not a listing.
            "profile": [
                r'picazor\.com/([^/]+)/([^/?]+)/page/(\d+)',
                r'picazor\.com/([^/]+)/([^/?]+)/?$',
            ],
            "video": [
                r'picazor\.com/([^/]+)/([^/?]+)/(\d+)/?$',
            ],
            "listing": [
                r'picazor\.com/([^/]+)/(videos|models)/([^/]+)',
            ],
        },
        Platform.EROME: {
            # An album contains media; a search lists albums.
            "listing": [
                r'erome\.com/a/([^/?#]+)',
                r'erome\.com/search\?',
            ],
            # /{user} is a profile page listing that user's albums.
            "profile": [
                r'erome\.com/([^/?#]+)/?$',
            ],
        },
    }

    VALID_DOMAINS = {
        Platform.REDGIFS: ['redgifs.com', 'www.redgifs.com'],
        Platform.INSTAGRAM: ['instagram.com', 'www.instagram.com'],
        Platform.PICAZOR: ['picazor.com', 'www.picazor.com'],
        Platform.EROME: ['erome.com', 'www.erome.com', 'fr.erome.com'],
        Platform.X: ['x.com', 'twitter.com', 'www.x.com', 'www.twitter.com', 'mobile.twitter.com'],
        Platform.TIKTOK: ['tiktok.com', 'www.tiktok.com', 'vm.tiktok.com'],
        Platform.PORNPICS: ['pornpics.com', 'www.pornpics.com'],
        Platform.SEXCOM: ['sex.com', 'www.sex.com'],
        Platform.CIVITAI: ['civitai.com', 'www.civitai.com', 'civitai.red', 'www.civitai.red'],
        Platform.PEXELS: ['pexels.com', 'www.pexels.com'],
        # Removed sources have no VALID_DOMAINS entries: validate_url() rejects
        # Coomer/Kemono/Cyberdrop/Bunkr first. _HOST_PLATFORMS still recognizes them
        # so the refusal can name the platform.
    }

    # Domaines reconnus par host (host == d ou host.endswith('.'+d)).
    _HOST_PLATFORMS = [
        ('redgifs.com', Platform.REDGIFS),
        ('instagram.com', Platform.INSTAGRAM),
        ('picazor.com', Platform.PICAZOR),
        ('erome.com', Platform.EROME),
        # Recognize removed sources only to return a named refusal rather than
        # an unknown-URL message or a silent fallback to the generic scraper.
        ('coomer.st', Platform.COOMER), ('coomer.su', Platform.COOMER),
        ('coomer.party', Platform.COOMER), ('coomer.cr', Platform.COOMER),
        ('kemono.cr', Platform.KEMONO), ('kemono.su', Platform.KEMONO),
        ('kemono.party', Platform.KEMONO),
        ('cyberdrop.me', Platform.CYBERDROP), ('cyberdrop.cr', Platform.CYBERDROP),
        ('cyberdrop.to', Platform.CYBERDROP),
        ('x.com', Platform.X), ('twitter.com', Platform.X),
        ('tiktok.com', Platform.TIKTOK),
        ('pornpics.com', Platform.PORNPICS),
        ('sex.com', Platform.SEXCOM),
        ('civitai.com', Platform.CIVITAI),
        ('civitai.red', Platform.CIVITAI),
        ('pexels.com', Platform.PEXELS),
        # Match fapello.com and language mirrors with endswith('.fapello.com').
        # Omit VALID_DOMAINS to allow those mirrors; the source normalizes the host
        # before calling gallery-dl.
        ('fapello.com', Platform.FAPELLO),
        # Match Reddit subdomains and redd.it (shortener and i.redd.it CDN).
        # As with Fapello, omit VALID_DOMAINS; the source canonicalizes to
        # www.reddit.com, including resolving /s/ share links.
        ('reddit.com', Platform.REDDIT),
        ('redd.it', Platform.REDDIT),
    ]

    @staticmethod
    def detect_platform(url: str) -> Platform:
        host = (urlparse(url).hostname or '').lower()
        if not host:
            return Platform.UNKNOWN
        # Removed Bunkr hosts rotate TLDs. Require 'bunkr' in the second-level
        # label (labels[-2]), e.g. bunkr.cr or bunkrr.su, to reject deceptive hosts
        # such as bunkr.cr.evil.com. Recognition only enables a named refusal;
        # it must never route to a scan or download.
        labels = host.split('.')
        if len(labels) >= 2 and labels[-2].startswith('bunkr'):
            return Platform.BUNKR
        for domain, platform in URLValidator._HOST_PLATFORMS:
            if host == domain or host.endswith('.' + domain):
                return platform
        return Platform.UNKNOWN

    @classmethod
    def validate_url(cls, url: str) -> ValidationResult:
        url = (url or "").strip()

        if not url.startswith(('http://', 'https://')):
            if '.' in url and url:
                url = f"https://{url}"
            else:
                return ValidationResult(
                    is_valid=False, platform=Platform.UNKNOWN, url_type=URLType.UNKNOWN,
                    value="", original_url=url,
                    error="Invalid URL: must start with http:// or https://",
                    suggestions=["Add https:// at the start of the URL"],
                )

        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return ValidationResult(
                    is_valid=False, platform=Platform.UNKNOWN, url_type=URLType.UNKNOWN,
                    value="", original_url=url, error="Invalid URL format",
                )
        except Exception as e:
            return ValidationResult(
                is_valid=False, platform=Platform.UNKNOWN, url_type=URLType.UNKNOWN,
                value="", original_url=url, error=f"Parsing error: {e}",
            )

        platform = cls.detect_platform(url)

        if platform in _REMOVED_PLATFORMS:
            # Explicitly reject removed dump/leak platforms before source resolution.
            # This prevents fallback to generic scrapers, whose tools may still
            # support some of these platforms internally.
            return ValidationResult(
                is_valid=False, platform=platform, url_type=URLType.UNKNOWN,
                value="", original_url=url,
                error=f"Source '{platform.value}' not supported: this site was "
                      "removed from this scraper.",
            )

        if platform == Platform.UNKNOWN:
            # Delegate well-formed HTTP(S) URLs on unknown domains to yt-dlp.
            if '.' in parsed.netloc:
                return ValidationResult(
                    is_valid=True, platform=Platform.GENERIC, url_type=URLType.VIDEO,
                    value=url, original_url=url,
                )
            return ValidationResult(
                is_valid=False, platform=Platform.UNKNOWN, url_type=URLType.UNKNOWN,
                value="", original_url=url, error="Unrecognized URL",
                suggestions=[
                    "Specialized platforms: RedGIFs, Instagram, Picazor",
                    "Other video sites (TikTok, YouTube, ...): paste the full page URL",
                ],
            )

        domain = (parsed.hostname or '').lower()
        if platform in cls.VALID_DOMAINS and domain not in cls.VALID_DOMAINS[platform]:
            valid_domains = ', '.join(cls.VALID_DOMAINS[platform])
            return ValidationResult(
                is_valid=False, platform=platform, url_type=URLType.UNKNOWN,
                value="", original_url=url,
                error=f"Invalid domain for {platform.value}",
                suggestions=[f"Use: {valid_domains}"],
            )

        if platform == Platform.REDGIFS:
            return cls._validate_redgifs(url)
        if platform == Platform.INSTAGRAM:
            return cls._validate_instagram(url)
        if platform == Platform.PICAZOR:
            return cls._validate_picazor(url)
        if platform == Platform.EROME:
            return cls._validate_erome(url)
        if platform == Platform.PEXELS:
            return cls._validate_pexels(url)
        if platform in (Platform.X, Platform.TIKTOK, Platform.PORNPICS,
                        Platform.CIVITAI, Platform.FAPELLO, Platform.REDDIT,
                        Platform.SEXCOM):
            return cls._validate_gallerydl_platform(url, platform)

        # Defensive, normally unreachable guard: every detected Platform above
        # has a corresponding _validate_X method.
        return ValidationResult(
            is_valid=False, platform=platform, url_type=URLType.UNKNOWN,
            value="", original_url=url, error="Unsupported platform.")


    @classmethod
    def _validate_redgifs(cls, url: str) -> ValidationResult:
        for pattern in cls.PATTERNS[Platform.REDGIFS]["user"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                return ValidationResult(True, Platform.REDGIFS, URLType.PROFILE, m.group(1), url)

        for pattern in cls.PATTERNS[Platform.REDGIFS]["video"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                video_id = m.group(1)
                if video_id.lower() not in ('users', 'niches', 'watch', 'gifs'):
                    return ValidationResult(True, Platform.REDGIFS, URLType.VIDEO, video_id, url)

        for pattern in cls.PATTERNS[Platform.REDGIFS]["niche"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                return ValidationResult(True, Platform.REDGIFS, URLType.NICHE, m.group(1), url)

        return ValidationResult(
            False, Platform.REDGIFS, URLType.UNKNOWN, "", url,
            error="Unrecognized RedGIFs URL format",
            suggestions=[
                "Supported formats:",
                "  • Profile: redgifs.com/users/username",
                "  • Video: redgifs.com/watch/videoid",
                "  • Niche: redgifs.com/niches/nichename",
            ],
        )

    @classmethod
    def _validate_instagram(cls, url: str) -> ValidationResult:
        for pattern in cls.PATTERNS[Platform.INSTAGRAM]["post"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                post_id = m.group(m.lastindex) if m.lastindex else m.group(1)
                return ValidationResult(True, Platform.INSTAGRAM, URLType.POST, post_id, url)

        for pattern in cls.PATTERNS[Platform.INSTAGRAM]["reel"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                reel_id = m.group(m.lastindex) if m.lastindex else m.group(1)
                return ValidationResult(True, Platform.INSTAGRAM, URLType.REEL, reel_id, url)

        for pattern in cls.PATTERNS[Platform.INSTAGRAM]["profile"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                username = m.group(1)
                if username not in ('p', 'reel', 'reels', 'stories', 'explore', 'tv'):
                    return ValidationResult(True, Platform.INSTAGRAM, URLType.PROFILE, username, url)

        return ValidationResult(
            False, Platform.INSTAGRAM, URLType.UNKNOWN, "", url,
            error="Unrecognized Instagram URL format",
            suggestions=[
                "Supported formats:",
                "  • Profile: instagram.com/username",
                "  • Post: instagram.com/p/postid",
                "  • Reel: instagram.com/reel/reelid",
            ],
        )

    @classmethod
    def _validate_picazor(cls, url: str) -> ValidationResult:
        for pattern in cls.PATTERNS[Platform.PICAZOR]["listing"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                return ValidationResult(True, Platform.PICAZOR, URLType.LISTING, m.group(2), url)

        for pattern in cls.PATTERNS[Platform.PICAZOR]["profile"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                creator = m.group(2)
                if creator not in ('videos', 'models', 'categories'):
                    return ValidationResult(True, Platform.PICAZOR, URLType.PROFILE, creator, url)

        for pattern in cls.PATTERNS[Platform.PICAZOR]["video"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                creator = m.group(2)
                if creator not in ('videos', 'models', 'categories'):
                    return ValidationResult(True, Platform.PICAZOR, URLType.VIDEO, creator, url)

        return ValidationResult(
            False, Platform.PICAZOR, URLType.UNKNOWN, "", url,
            error="Unrecognized Picazor URL format",
            suggestions=[
                "Supported formats:",
                "  • Profile: picazor.com/fr/creator",
                "  • Listing page: picazor.com/fr/creator/page/2",
                "  • Single media: picazor.com/fr/creator/123",
                "  • Listing: picazor.com/fr/videos/week",
            ],
        )

    @classmethod
    def _validate_erome(cls, url: str) -> ValidationResult:
        # Albums (/a/ID) and searches (/search?q=) contain media.
        for pattern in cls.PATTERNS[Platform.EROME]["listing"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                value = m.group(1) if m.groups() else "search"
                return ValidationResult(True, Platform.EROME, URLType.LISTING, value, url)

        # User profiles (/USER): exclude reserved paths.
        for pattern in cls.PATTERNS[Platform.EROME]["profile"]:
            m = re.search(pattern, url, re.IGNORECASE)
            if m:
                user = m.group(1)
                if user.lower() not in ('a', 'search', 'login', 'register',
                                        'tos', 'dmca', 'faq'):
                    return ValidationResult(True, Platform.EROME, URLType.PROFILE, user, url)

        return ValidationResult(
            False, Platform.EROME, URLType.UNKNOWN, "", url,
            error="Unrecognized Erome URL format",
            suggestions=[
                "Supported formats:",
                "  • Album: erome.com/a/AbCdEfGh",
                "  • Search: erome.com/search?q=keyword",
                "  • Profile: erome.com/username",
            ],
        )

    @classmethod
    def _validate_pexels(cls, url: str) -> ValidationResult:
        """Accept only paths covered by the official API.

        Search, collections and individual photos have documented endpoints.
        Reject public /@user profiles, roots, videos, unknown locales and routes
        before networking, with actionable suggestions."""
        parsed = urlparse(url)
        suggestions = [
            "Supported Pexels formats:",
            "  • Search: pexels.com/search/portrait/",
            "  • Localized search: pexels.com/en-us/search/portrait/",
            "    or pexels.com/fr-fr/chercher/portrait/",
            "  • Collection accessible with your key: pexels.com/collections/name-id/",
            "  • Photo: pexels.com/photo/name-123456/",
            "The /en-us/ and /fr-fr/ prefixes are also accepted for photos and collections.",
            "The official Pexels API does not expose public /@user profiles.",
        ]
        if parsed.username is not None or parsed.password is not None:
            return ValidationResult(
                False, Platform.PEXELS, URLType.UNKNOWN, "", url,
                error="Invalid Pexels URL: userinfo not allowed.",
                suggestions=suggestions,
            )

        route = parse_pexels_path(parsed.path or "/")
        if route:
            url_type = URLType.POST if route.kind == 'photo' else URLType.LISTING
            return ValidationResult(
                True, Platform.PEXELS, url_type, route.value, url)

        return ValidationResult(
            False, Platform.PEXELS, URLType.UNKNOWN, "", url,
            error="Pexels URL format not supported by the official API.",
            suggestions=suggestions,
        )

    @classmethod
    def _validate_gallerydl_platform(cls, url, platform):
        """Minimally validate gallery-dl platforms: the host is already confirmed;
        let gallery-dl parse the path. A coarse LISTING URL type is sufficient
        because the scan enumerates through gallery-dl."""
        return ValidationResult(
            is_valid=True, platform=platform, url_type=URLType.LISTING,
            value=url, original_url=url)


url_validator = URLValidator()
