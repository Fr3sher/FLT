"""The /api/scrape/scan route classifies scan errors by kind. A blocked source must
never look empty; legitimate emptiness must never look like failure. Verify this
centrally for ALL gallery-dl sources, not only UniversalSource. Mock
registry.resolve; no network or gallery-dl process."""
import pytest
from lds_scrape.sources import gdl, registry
from lds_scrape.sources.base import Match, Source, Capabilities, ResultList


class _FakeSource(Source):
    """Disposable source whose scan returns exactly the result supplied by the test."""
    name = 'fake'
    priority = 1000       # Before all real sources.
    capabilities = Capabilities()
    paginated = True
    category = 'image'

    def __init__(self, items=None, err=None):
        self._items = items
        self._err = err

    def match(self, url):
        if url.startswith('https://fake.example.test/'):
            return Match(url=url)
        return None

    def scan(self, match):
        return self._items, self._err


def _use_fake_source(monkeypatch, **kw):
    src = _FakeSource(**kw)

    def fake_resolve(url):
        match = src.match(url)
        if match is not None:
            match.source = src
        return match

    monkeypatch.setattr(registry, 'resolve', fake_resolve)
    return src


@pytest.mark.plugins('scrape')
def test_scan_empty_kind_is_200_with_zero_items(client, monkeypatch):
    """kind=empty means the scraper completed successfully without media.
    Return200/count=0, never502; generic502 responses previously hid this case for
    eleven of fourteen sources."""
    _use_fake_source(monkeypatch, items=None,
                     err=gdl.GdlError('gallery-dl: no media found.', 'empty'))

    r = client.post('/api/scrape/scan',
                    json={'url': 'https://fake.example.test/album/1'})

    assert r.status_code == 200
    body = r.get_json()
    assert body['count'] == 0
    assert body['items'] == []
    assert body['scannable'] is True


@pytest.mark.plugins('scrape')
def test_scan_auth_kind_still_answers_502_with_its_message(client, monkeypatch):
    """Authentication,429 and DDoS-Guard failures must NEVER masquerade as empty
    results. Only kind=empty becomes200; other failures retain502 and their
    original message."""
    _use_fake_source(monkeypatch, items=None,
                     err=gdl.GdlError('gallery-dl: auth (429).', 'auth'))

    r = client.post('/api/scrape/scan',
                    json={'url': 'https://fake.example.test/album/1'})

    assert r.status_code == 502
    body = r.get_json()
    assert 'auth' in body['error']


@pytest.mark.plugins('scrape')
def test_scan_toolerror_kind_still_answers_502(client, monkeypatch):
    """Apply the same guarantee to toolerror: every kind other than empty remains an
    explicit HTTP failure."""
    _use_fake_source(monkeypatch, items=None,
                     err=gdl.GdlError('gallery-dl: unreadable response.', 'toolerror'))

    r = client.post('/api/scrape/scan',
                    json={'url': 'https://fake.example.test/album/1'})

    assert r.status_code == 502


@pytest.mark.plugins('scrape')
def test_scan_surfaces_partial_when_the_time_budget_cut_the_listing_short(client, monkeypatch):
    """enumerate may return ResultList with partial=True after an album-recursion
    timeout. Previously universal.py only logged this and the route omitted it,
    preventing the UI from disclosing incomplete results."""
    truncated = ResultList([
        {'url': 'https://fake.example.test/a.jpg', 'title': '', 'thumbnail': None,
         'type': 'image', 'platform': 'fake'}])
    truncated.from_albums = True
    truncated.partial = True
    _use_fake_source(monkeypatch, items=truncated, err=None)

    r = client.post('/api/scrape/scan',
                    json={'url': 'https://fake.example.test/album/1'})

    assert r.status_code == 200
    body = r.get_json()
    assert body['partial'] is True
    assert body['count'] == 1


@pytest.mark.plugins('scrape')
def test_scan_partial_defaults_to_false_for_ordinary_sources(client, monkeypatch):
    """A non-gallery-dl source returning an ordinary list must default partial to
    False, without an exception or unexpected truthy value."""
    _use_fake_source(monkeypatch, items=[{'url': 'https://fake.example.test/a.jpg',
                                          'title': '', 'thumbnail': None,
                                          'type': 'image', 'platform': 'fake'}], err=None)

    r = client.post('/api/scrape/scan',
                    json={'url': 'https://fake.example.test/album/1'})

    assert r.status_code == 200
    assert r.get_json()['partial'] is False


@pytest.mark.plugins('scrape')
def test_scan_a_plain_string_error_without_kind_still_answers_502(client, monkeypatch):
    """A plain string error without GdlError.kind stays502. getattr(err, kind, None)
    must not invent an empty classification."""
    _use_fake_source(monkeypatch, items=None, err="Fake: something broke.")

    r = client.post('/api/scrape/scan',
                    json={'url': 'https://fake.example.test/album/1'})

    assert r.status_code == 502
