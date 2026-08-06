# app/scrape/sources/universal.py
"""Source universelle (catch-all, priorité 0) : hybride gallery-dl → (exit 64) → yt-dlp.
Tente d'abord gallery-dl (extracteurs dédiés de nombreux sites) ; si gallery-dl ne
supporte pas l'URL (exit code & 64), repli sur yt-dlp — mais SEULEMENT pour les hôtes
d'une allowlist vettée (atténuation SSRF interim, cf. spec décision #6)."""
import os
from urllib.parse import urlparse

from .base import Source, Capabilities, Match
from . import registry, gdl
from .. import netfetch

# Hôtes pour lesquels la branche générique yt-dlp est autorisée (interim SSRF).
# Coomer/Kemono/Cyberdrop/Bunkr n'y figurent plus : ces sources sont retirées et
# validators.py les refuse explicitement avant même d'atteindre cette source (donc
# avant match()) — les garder ici serait du code mort et une fausse impression que
# le repli générique reste possible pour elles.
VETTED_DOMAINS = (
    'x.com', 'twitter.com', 'tiktok.com',
    'youtube.com', 'youtu.be', 'pornhub.com', 'xvideos.com', 'redgifs.com',
    'vimeo.com', 'dailymotion.com',
)


def _host_vetted(url):
    host = (urlparse(url).hostname or '').lower()
    if not host:
        return False
    return any(host == d or host.endswith('.' + d) for d in VETTED_DOMAINS)


class UniversalSource(Source):
    name = 'universal'
    priority = 0
    capabilities = Capabilities(is_universal_fallback=True, own_downloader=True)

    def match(self, url):
        from ..validators import url_validator, Platform
        # SSRF : le chemin générique est le seul à accepter un hôte arbitraire, et
        # scan() lance gallery-dl dessus. Refuser ICI signifie qu'aucune source ne
        # matche et que la route répond 400 AVANT qu'un sous-process ne parte.
        ok, _err = netfetch._validate_public_http_url(url)
        if not ok:
            return None
        result = url_validator.validate_url(url)
        if result.is_valid and result.platform == Platform.GENERIC:
            return Match(url=url, validation=result)
        return None

    def scan(self, match):
        # Énumération générique : 1 item (yt-dlp gère la vidéo unique) ; gallery-dl
        # générique étant off par défaut, on reste sur l'item unique au scan.
        url = match.url
        return ([{'url': url, 'title': url, 'thumbnail': None,
                  'type': 'video', 'platform': 'generic'}], None)

    def download(self, url, dest_base):
        # 1) gallery-dl (extracteur dédié) d'abord.
        dest_dir = os.path.dirname(dest_base)
        filename = os.path.basename(dest_base)
        ok, abs_path, err = gdl.download(url, dest_dir, filename)
        if ok and abs_path:
            return True, os.path.basename(abs_path), None
        # 2) gallery-dl ne supporte pas le site → yt-dlp, mais seulement si l'hôte
        #    est vetté (atténuation SSRF, cf. spec décision #6). On teste le KIND,
        #    jamais le texte du message.
        if getattr(err, 'kind', None) == 'unsupported':
            if not _host_vetted(url):
                return False, None, "Site not supported (gallery-dl) and host not vetted for yt-dlp."
            return netfetch.download_via_ytdlp(url, dest_base)
        # 3) auth/réseau (pas 'unsupported') → on remonte l'erreur gallery-dl.
        return False, None, err or "Generic download failed."


registry.register(UniversalSource())
