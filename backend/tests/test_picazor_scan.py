"""Picazor scan() : distinguer un résultat vide LÉGITIME (listing/profil sans
média, page HTML chargée sans incident) d'un vrai échec de parsing (finding #3).

Tout est mocké (`_request_html`) : aucun appel réseau / curl_cffi."""
from types import SimpleNamespace

from app.scrape.sources import picazor


def test_an_empty_listing_is_a_result_not_an_error(monkeypatch):
    monkeypatch.setattr(picazor, '_request_html', lambda url: ('<html>no tiles here</html>', None))
    validation = SimpleNamespace(original_url='https://picazor.com/fr/videos/week',
                                 value='', url_type=None)

    items, err = picazor.scan(validation)

    assert items is None
    assert getattr(err, 'kind', None) == 'empty'


def test_an_empty_profile_is_a_result_not_an_error(monkeypatch):
    monkeypatch.setattr(picazor, '_request_html', lambda url: ('<html>no tiles here</html>', None))
    validation = SimpleNamespace(original_url='https://picazor.com/fr/nobody',
                                 value='nobody', url_type=None)

    items, err = picazor.scan(validation)

    assert items is None
    assert getattr(err, 'kind', None) == 'empty'


def test_a_detail_page_with_no_extractable_media_stays_a_real_failure(monkeypatch):
    """La page de détail décrit toujours un média précis — l'absence de match
    régex signale un layout changé (échec de parsing), pas une page vide.
    Volontairement PAS convertie en kind='empty' (cf. rapport)."""
    monkeypatch.setattr(picazor, '_request_html', lambda url: ('<html>layout changed</html>', None))
    validation = SimpleNamespace(original_url='https://picazor.com/fr/someone/42',
                                 value='someone', url_type=None)

    items, err = picazor.scan(validation)

    assert items is None
    assert getattr(err, 'kind', None) is None
    assert 'detail page' in err


def test_a_populated_listing_still_returns_its_items(monkeypatch):
    html = '"/uploads/a/b/300px_x.jpg"'
    monkeypatch.setattr(picazor, '_request_html', lambda url: (html, None))
    validation = SimpleNamespace(original_url='https://picazor.com/fr/models',
                                 value='', url_type=None)

    items, err = picazor.scan(validation)

    assert err is None
    assert len(items) == 1
