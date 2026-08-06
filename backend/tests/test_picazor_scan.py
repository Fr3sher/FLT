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


def test_profile_scan_marks_a_mid_pagination_failure_as_partial(monkeypatch):
    """A profile has 3 pages worth of media (per the /fr/{creator}/{index} links
    on page 1). Page 1 loads fine and yields an item; page 2 gets blocked by
    Cloudflare mid-pagination. Before this fix, `scan()` degraded gracefully by
    just `break`ing out of the loop and returning `all_items[:MAX_ITEMS], None`
    — a plain list with no truncation signal, presenting a harvest cut short by
    a real HTTP failure as a complete profile. Patches at the HTTP-layer
    boundary (`_request_html`, same function the real pagination loop calls for
    every page) so the actual loop logic runs, not a stubbed-out scan()."""
    html_page1 = '"/uploads/a/b/300px_x.jpg"' + '<a href="/fr/someone/50">50</a>'

    def fake_request_html(url):
        if url.endswith('/page/2'):
            return None, "Picazor (Cloudflare) blocked access."
        return html_page1, None

    monkeypatch.setattr(picazor, '_request_html', fake_request_html)
    validation = SimpleNamespace(original_url='https://picazor.com/fr/someone',
                                 value='someone', url_type=None)

    items, err = picazor.scan(validation)

    assert err is None
    assert len(items) == 1
    assert getattr(items, 'partial', False) is True
