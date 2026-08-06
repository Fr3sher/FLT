"""Recherche d'images par mot-clé (source websearch).

La bibliothèque `ddgs` n'est JAMAIS appelée : les tests remplacent la seule
indirection `_images`."""
import pytest

from app.scrape.sources import websearch
from app.scrape.sources.base import Match
from app.scrape.sources.websearch import WebSearchSource


_RESULT = {
    'title': 'Curly hair portrait',
    'image': 'https://cdn.example.test/photo.jpg',
    'thumbnail': 'https://cdn.example.test/thumb.jpg',
    'url': 'https://blog.example.test/post/42',
    'height': 1200, 'width': 800, 'source': 'example',
}


def _spy_images(monkeypatch, results=None, raises=None):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        if raises is not None:
            raise raises
        return results if results is not None else []
    monkeypatch.setattr(websearch, '_images', fake)
    return seen


# --- match() -------------------------------------------------------------------
def test_match_reads_the_keyword_and_safesearch_from_the_url():
    m = WebSearchSource().match(
        'https://duckduckgo.com/?q=curly+hair&iax=images&ia=images&kp=-2')
    assert m is not None
    assert m.query == 'curly hair'
    assert m.safesearch == 'off'


def test_match_honours_the_strict_safesearch_flag():
    m = WebSearchSource().match('https://duckduckgo.com/?q=portrait&kp=1')
    assert m.safesearch == 'on'


@pytest.mark.parametrize('url', [
    'https://duckduckgo.com/?q=&iax=images',      # mot-clé vide
    'https://duckduckgo.com/',                     # pas de q
    'https://duckduckgo.com.evil.test/?q=x',       # suffixe d'hôte
    'https://example.test/?q=x',                   # autre site
])
def test_match_refuses_anything_else(url):
    assert WebSearchSource().match(url) is None


# --- scan() --------------------------------------------------------------------
def test_scan_maps_results_to_the_common_schema(monkeypatch):
    seen = _spy_images(monkeypatch, results=[_RESULT])
    m = WebSearchSource().match('https://duckduckgo.com/?q=curly+hair&kp=-2')
    m.page = 0

    items, err = WebSearchSource().scan(m)

    assert err is None
    assert items == [{
        'url': 'https://cdn.example.test/photo.jpg',      # média DIRECT
        'title': 'Curly hair portrait',
        'thumbnail': 'https://cdn.example.test/thumb.jpg',
        'type': 'image',
        'platform': 'websearch',
        'source_url': 'https://blog.example.test/post/42',  # provenance
    }]
    assert seen['query'] == 'curly hair'
    assert seen['safesearch'] == 'off'
    assert seen['page'] == 1        # ddgs compte à partir de 1, match.page de 0


def test_scan_asks_for_the_next_page(monkeypatch):
    seen = _spy_images(monkeypatch, results=[_RESULT])
    m = WebSearchSource().match('https://duckduckgo.com/?q=portrait')
    m.page = 3

    WebSearchSource().scan(m)

    assert seen['page'] == 4


def test_scan_drops_entries_without_a_usable_https_image(monkeypatch):
    _spy_images(monkeypatch, results=[
        {'image': 'http://cdn.example.test/insecure.jpg'},        # pas https
        {'image': 'https://user:pw@cdn.example.test/creds.jpg'},  # credentials
        {'title': 'no image at all'},
        _RESULT,
    ])
    m = WebSearchSource().match('https://duckduckgo.com/?q=portrait')
    m.page = 0

    items, err = WebSearchSource().scan(m)

    assert err is None
    assert [it['url'] for it in items] == ['https://cdn.example.test/photo.jpg']


def test_an_empty_search_is_empty_not_an_error(monkeypatch):
    """Zéro résultat pour un mot-clé est un fait, pas une panne."""
    _spy_images(monkeypatch, results=[])
    m = WebSearchSource().match('https://duckduckgo.com/?q=zzzznotathing')
    m.page = 0

    items, err = WebSearchSource().scan(m)

    assert err is None and items == []


def test_a_failing_library_is_reported_and_never_raises(monkeypatch):
    _spy_images(monkeypatch, raises=RuntimeError('ratelimit'))
    m = WebSearchSource().match('https://duckduckgo.com/?q=portrait')
    m.page = 0

    items, err = WebSearchSource().scan(m)

    assert items is None
    assert 'failed' in err.lower() and 'ratelimit' in err


def test_a_missing_dependency_says_how_to_install_it(monkeypatch):
    """Le registry importe toutes les sources au démarrage : une dépendance
    optionnelle absente doit donner une consigne, jamais empêcher le boot."""
    _spy_images(monkeypatch, raises=ImportError('No module named ddgs'))
    m = WebSearchSource().match('https://duckduckgo.com/?q=portrait')
    m.page = 0

    items, err = WebSearchSource().scan(m)

    assert items is None
    assert 'requirements-scrape.txt' in err


def test_the_source_is_registered_ahead_of_the_universal_fallback():
    from app.scrape.sources import registry
    match = registry.resolve('https://duckduckgo.com/?q=portrait&iax=images')
    assert match is not None and match.source.name == 'websearch'
