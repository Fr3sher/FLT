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

# Fenêtre d'énumération par page : la valeur que le moteur gallery-dl utilise
# déjà par défaut. Pas de réglage supplémentaire à accorder entre les deux.
MAX_ITEMS = gdl.DEFAULT_MAX_ITEMS


def _host_vetted(url):
    host = (urlparse(url).hostname or '').lower()
    if not host:
        return False
    return any(host == d or host.endswith('.' + d) for d in VETTED_DOMAINS)


class UniversalSource(Source):
    name = 'universal'
    priority = 0
    paginated = True
    category = 'image'
    capabilities = Capabilities(is_universal_fallback=True, own_downloader=True,
                                media_kinds=frozenset({'image', 'video'}))

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
        """Énumération générique via gallery-dl (~300 sites). Défaut : les médias
        directs de la page ; un listing d'albums rend UNE cover par album, la case
        « Scan full albums » (include_albums) rétablit la plongée."""
        url = match.url
        page = max(0, int(getattr(match, 'page', 0) or 0))
        items, err = gdl.enumerate(
            url, platform='generic', max_items=MAX_ITEMS,
            per_album=None if getattr(match, 'include_albums', False) else 1,
            image_range=f'{page * MAX_ITEMS + 1}-{(page + 1) * MAX_ITEMS}')
        if items:
            return items, None
        if getattr(err, 'kind', None) == 'unsupported':
            # gallery-dl n'a pas d'extracteur : on restitue le comportement
            # historique (1 média) pour que les hôtes vettés atteignent yt-dlp.
            match.paginated = False
            return ([{'url': url, 'title': url, 'thumbnail': None,
                      'type': 'video', 'platform': 'generic'}], None)
        if getattr(err, 'kind', None) == 'empty':
            # gallery-dl a tourné sans incident et n'a rien trouvé (post supprimé,
            # album vide, mauvais type de page) : un scan vide réussi, PAS un
            # échec. Le confondre avec 'toolerror' rendrait les deux cas
            # indiscernables pour cet appelant — exactement ce que 'empty' existe
            # pour éviter (cf. docstring de GdlError).
            return [], None
        # Auth / 429 / DDoS-Guard / erreur outil : on remonte. Ne JAMAIS déguiser
        # un blocage en « aucune image trouvée ».
        return None, err or "Nothing to scan at this URL."

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
