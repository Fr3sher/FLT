# app/scrape/sources/websearch.py
"""Recherche d'images par mot-clé sur le web ouvert — sans clé ni compte.

Le formulaire fabrique côté client une URL DuckDuckGo (`?q=…&iax=images&kp=…`) et
la poste au même /api/scrape/scan que toutes les autres sources : le contrat
« une URL entre » ne change pas (même patron que Pexels). Cette source la matche,
en ré-extrait le mot-clé et interroge `ddgs`, un métamoteur qui agrège plusieurs
backends — si l'un tombe, la recherche se dégrade au lieu de mourir.

Pourquoi ni Google ni Bing : leurs API de recherche d'images sont fermées aux
nouveaux clients (Google Custom Search s'arrête le 2027-01-01, Bing Search a été
retirée le 2025-08-11). Une source à clé serait morte chez tout nouvel installeur.
"""
import logging
from urllib.parse import parse_qs, urlsplit

from .base import Source, Capabilities, Match
from . import registry

logger = logging.getLogger(__name__)

PLATFORM = 'websearch'
MAX_RESULTS = 120        # même fenêtre que gdl.DEFAULT_MAX_ITEMS : une page = une page
_HOSTS = frozenset({'duckduckgo.com', 'www.duckduckgo.com'})
_MISSING_DEP = ("Web image search needs the 'ddgs' package: "
                "pip install -r backend/requirements-scrape.txt")


def _images(**kwargs):
    """Appel réel à la bibliothèque. Import PARESSEUX : le registry importe toutes
    les sources au démarrage de l'app, une dépendance optionnelle absente ne doit
    jamais empêcher le boot. C'est aussi le seul point de monkeypatch des tests."""
    from ddgs import DDGS
    return DDGS().images(**kwargs)


def _safe_https(value):
    """URL https sans credentials, ou None. Les résultats viennent de sites
    arbitraires : on ne restreint pas l'hôte, seulement la forme."""
    if not isinstance(value, str) or not value.strip():
        return None
    trimmed = value.strip()
    try:
        parsed = urlsplit(trimmed)
    except ValueError:
        return None
    if (parsed.scheme != 'https' or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        return None
    return trimmed


def _item(result):
    """Résultat ddgs → schéma commun, ou None. `image` = le média DIRECT (ce que
    l'import télécharge), `url` = la page où il a été trouvé (provenance)."""
    if not isinstance(result, dict):
        return None
    image = _safe_https(result.get('image'))
    if not image:
        return None
    title = result.get('title')
    return {
        'url': image,
        'title': title.strip() if isinstance(title, str) else '',
        'thumbnail': _safe_https(result.get('thumbnail')) or image,
        'type': 'image',
        'platform': PLATFORM,
        'source_url': _safe_https(result.get('url')),
    }


class WebSearchSource(Source):
    name = 'websearch'
    priority = 100          # coiffe la fallback universelle (priorité 0)
    paginated = True
    category = 'image'
    capabilities = Capabilities(media_kinds=frozenset({'image'}),
                                own_downloader=False, polite=True)

    def match(self, url):
        try:
            parsed = urlsplit(url or '')
        except ValueError:
            return None
        if (parsed.hostname or '').lower() not in _HOSTS:
            return None
        params = parse_qs(parsed.query)
        query = (params.get('q') or [''])[0].strip()
        if not query:
            return None
        m = Match(url=url)
        m.query = query
        # `kp` est le drapeau SafeSearch de DuckDuckGo lui-même : '1' strict,
        # '-2' désactivé (notre défaut). Il voyage dans l'URL parce que l'API de
        # scan n'accepte rien d'autre — pas de champ de requête ajouté.
        m.safesearch = 'on' if (params.get('kp') or [''])[0] == '1' else 'off'
        return m

    def scan(self, match):
        page = max(0, int(getattr(match, 'page', 0) or 0))
        try:
            results = _images(query=match.query, safesearch=match.safesearch,
                              type_image='photo', max_results=MAX_RESULTS,
                              page=page + 1)
        except ImportError:
            return None, _MISSING_DEP
        except Exception as exc:
            # La bibliothèque ne documente pas ses exceptions ; le contrat de
            # scan() est « ne lève jamais ». Un 429 doit dire qu'il a échoué,
            # surtout PAS « aucun résultat ».
            logger.warning("websearch: la recherche a échoué: %r", exc)
            return None, f"Web image search failed ({exc})."
        items = [item for item in (_item(r) for r in (results or [])) if item]
        return items, None


registry.register(WebSearchSource())
