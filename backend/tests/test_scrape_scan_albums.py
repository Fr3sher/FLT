"""Gallery listings (PornPics category/tag/search) use covers by default and full
albums optionally. Parse the actual HTML/AJAX listing thumbnail selected by the
site, not the first album image, without gallery-dl. include_albums from Scan full
albums restores complete gallery-dl traversal. If cover parsing fails after a
layout change, fall back to one image per album. Direct /galleries/ URLs are
unaffected. Everything is mocked: no network or gallery-dl process."""
import time

import pytest

from lds_scrape.sources import gdl, image_sites
from lds_scrape.sources.base import Match
from lds_scrape.sources.image_sites import PornpicsSource, _covers_scan, _full_size


def _mock_gdl_runs(monkeypatch):
    """Fake _run_simulate: a category with two albums of five images. Return calls
    (URL and image_range) for inspection."""
    calls = []

    def fake(url, max_items, cookies, extra_opts, image_range=None):
        calls.append({'url': url, 'image_range': image_range})
        if 'category' in url:
            return [[6, 'https://x/album1/', {}], [6, 'https://x/album2/', {}]], None
        n = int((image_range or '1-99').split('-')[1])
        return [[3, f'{url}img{i}.jpg', {'extension': 'jpg'}]
                for i in range(1, 6)][:n], None
    monkeypatch.setattr(gdl, '_run_simulate', fake)
    return calls


def test_enumerate_per_album_1_returns_one_cover_per_album(monkeypatch):
    calls = _mock_gdl_runs(monkeypatch)
    items, err = gdl.enumerate('https://x/category/', per_album=1)
    assert err is None
    assert [it['url'] for it in items] == ['https://x/album1/img1.jpg',
                                           'https://x/album2/img1.jpg']
    # Limit each album simulation with --range1-1; do not enumerate a full album just to
    # retain one image.
    assert [c['image_range'] for c in calls[1:]] == ['1-1', '1-1']


def test_enumerate_without_per_album_dives_full_albums(monkeypatch):
    _mock_gdl_runs(monkeypatch)
    items, err = gdl.enumerate('https://x/category/')
    assert err is None
    assert len(items) == 10          # Historical behavior: two albums with five images each.
    #
    # Item provenance (from_albums) prevents a silent Load more action.

def test_enumerate_flags_album_sourced_items_so_callers_can_disable_pagination(monkeypatch):
    """These items come exclusively from type6 album recursion limited by ALBUM COUNT
    (max_albums), never a page offset. Advertising pagination would send Load more
    into an ignored --range window. enumerate must expose from_albums so callers
    avoid that silent failure."""
    _mock_gdl_runs(monkeypatch)
    items, err = gdl.enumerate('https://x/category/')
    assert err is None
    assert getattr(items, 'from_albums', False) is True


def test_enumerate_does_not_flag_top_level_media_as_album_sourced(monkeypatch):
    """Top-level type3 media without recursion remains pageable through image_range
    and has no from_albums signal."""
    def fake(url, max_items, cookies, extra_opts, image_range=None):
        return [[3, f'{url}img1.jpg', {'extension': 'jpg'}]], None
    monkeypatch.setattr(gdl, '_run_simulate', fake)

    items, err = gdl.enumerate('https://x/direct-media/')

    assert err is None
    assert getattr(items, 'from_albums', False) is False


# Global time budget (deadline) prevents Flask requests lasting about nine minutes.

def test_enumerate_stops_the_album_recursion_once_the_deadline_has_passed(monkeypatch):
    """An already expired deadline stops album recursion BEFORE the first album
    subprocess. Return the documented kind=empty outcome for a spent budget rather
    than a tool error; no real clock needs to advance."""
    calls = _mock_gdl_runs(monkeypatch)

    items, err = gdl.enumerate('https://x/category/', per_album=1,
                               deadline=time.monotonic() - 1)   # Already expired.

    assert items is None
    assert getattr(err, 'kind', None) == 'empty'
    # The top-level scan still discovers both albums, but the expired deadline stops
    # recursion before the first album.
    assert len(calls) == 1


def test_enumerate_applies_a_default_deadline_when_the_caller_passes_none(monkeypatch):
    """gdl.enumerate must apply a time budget even when callers omit deadline.
    Previously only universal.py supplied one; other gallery-dl sources could run
    1+max_albums subprocesses at GDL_TIMEOUT each inside a synchronous Flask
    request, approaching nine minutes."""
    calls = _mock_gdl_runs(monkeypatch)
    base = 1_000_000.0
    clock = iter([base,                                            # Compute the default deadline.
                  base + gdl.DEFAULT_SCAN_BUDGET_SECONDS + 1])      # boucle : avant album1
    monkeypatch.setattr(gdl.time, 'monotonic', lambda: next(clock))

    items, err = gdl.enumerate('https://x/category/', per_album=1)   # No deadline.

    assert items is None
    assert getattr(err, 'kind', None) == 'empty'
    assert len(calls) == 1     # Top-level only; recursion never started.


def test_enumerate_deadline_checked_between_albums_lets_the_first_one_through(monkeypatch):
    """Check the budget at each loop start, never during an active subprocess. A fake
    clock expiring after album1 lets that album finish and prevents album2,
    yielding a partial rather than empty result."""
    calls = _mock_gdl_runs(monkeypatch)
    clock = iter([0.0,    # Before album1: deadline not reached.
                  2.0])   # Before album2: deadline exceeded.
    monkeypatch.setattr(gdl.time, 'monotonic', lambda: next(clock))

    items, err = gdl.enumerate('https://x/category/', per_album=1, deadline=1.0)

    assert err is None
    assert [it['url'] for it in items] == ['https://x/album1/img1.jpg']
    assert getattr(items, 'partial', False) is True
    assert len(calls) == 2      # Top-level scan discovers albums, then reads only album1.


def test_enumerate_reports_a_blocked_album_scan_even_when_the_budget_also_expired(monkeypatch):
    """Regression: album1 returns an authentication error and the budget expires
    before album2. Checking timed_out before album_errors formerly replaced the
    collected auth failure with kind=empty and200/count=0. The authentication
    error and502 extractor message must win even when the deadline has expired."""
    calls = []

    def fake(url, max_items, cookies, extra_opts, image_range=None):
        calls.append(url)
        if 'category' in url:
            return [[6, 'https://x/album1/', {}], [6, 'https://x/album2/', {}]], None
        return None, gdl.GdlError('gallery-dl: auth (429).', 'auth')
    monkeypatch.setattr(gdl, '_run_simulate', fake)

    clock = iter([0.0,    # Before album1: deadline not reached.
                  2.0])   # Before album2: deadline exceeded.
    monkeypatch.setattr(gdl.time, 'monotonic', lambda: next(clock))

    items, err = gdl.enumerate('https://x/category/', per_album=1, deadline=1.0)

    assert items is None
    assert getattr(err, 'kind', None) == 'auth'
    assert '429' in err
    # Top-level finds both albums, album1 fails, and the deadline prevents album2.
    # Verify both conditions together, not album_errors alone.
    assert len(calls) == 2


# Cover mode parses listing thumbnails.
_TILE_HTML = '''
<li><a class="rel-link" href="/galleries/flexible-girl-123/">
  <img src="1px.png" data-src="https://cdni.pornpics.com/460/1/2/123/123_009_ab.jpg" alt="Flexible girl">
</a></li>
<li><a class="rel-link" href="https://www.pornpics.com/galleries/splits-babe-456/">
  <img src='1px.png' data-src='https://cdni.pornpics.com/300/3/4/456/456_113_cd.jpg' alt='Splits babe'>
</a></li>
<li><a class="rel-link" href="/channels/whatever/">navigation link without tile data-src</a></li>
'''


def test_full_size_swaps_cdn_size_segment():
    assert _full_size('https://cdni.pornpics.com/460/1/2/123/123_009_ab.jpg') \
        == 'https://cdni.pornpics.com/1280/1/2/123/123_009_ab.jpg'
    assert _full_size('https://cdni.pornpics.com/300/3/4/456/456_113_cd.jpg') \
        == 'https://cdni.pornpics.com/1280/3/4/456/456_113_cd.jpg'


def test_covers_page0_returns_the_listing_thumbnails(monkeypatch):
    monkeypatch.setattr(image_sites, '_listing_html', lambda url: _TILE_HTML)
    items, err = _covers_scan('https://www.pornpics.com/flexible/', 0)
    assert err is None
    # Use the VISIBLE thumbnail (_009_/_113_), not the first album image. Include
    # gallery tiles only; ignore /channels/ links.
    assert [it['url'] for it in items] == [
        'https://cdni.pornpics.com/1280/1/2/123/123_009_ab.jpg',
        'https://cdni.pornpics.com/1280/3/4/456/456_113_cd.jpg']
    assert items[0]['thumbnail'].startswith('https://cdni.pornpics.com/460/')
    assert items[0]['title'] == 'Flexible girl'


def test_covers_next_pages_use_the_ajax_endpoint(monkeypatch):
    seen = {}

    def fake_json(url, offset):
        seen['offset'] = offset
        return [{'g_url': 'https://www.pornpics.com/galleries/x-789/', 'desc': 'X',
                 't_url_460': 'https://cdni.pornpics.com/460/5/6/789/789_042_ef.jpg'}]
    monkeypatch.setattr(image_sites, '_listing_json', fake_json)
    items, err = _covers_scan('https://www.pornpics.com/flexible/', 2)
    assert err is None and seen['offset'] == 40
    assert items[0]['url'] == 'https://cdni.pornpics.com/1280/5/6/789/789_042_ef.jpg'
    assert items[0]['title'] == 'X'


def test_covers_scan_signals_fallback_never_raises(monkeypatch):
    def boom(url):
        raise RuntimeError('site down')
    monkeypatch.setattr(image_sites, '_listing_html', boom)
    assert _covers_scan('https://www.pornpics.com/flexible/', 0) == (None, None)
    monkeypatch.setattr(image_sites, '_listing_html', lambda url: '<html>changed layout</html>')
    assert _covers_scan('https://www.pornpics.com/flexible/', 0) == (None, None)


# --- Routage PornpicsSource.scan : covers / albums / galerie directe / repli ---
@pytest.fixture()
def _spies(monkeypatch):
    seen = {'enum': None, 'covers': 0}

    def fake_enum(url, **kw):
        seen['enum'] = kw
        return [], None
    monkeypatch.setattr(gdl, 'enumerate', fake_enum)
    monkeypatch.setattr(image_sites, '_listing_html', lambda url: seen.update(covers=seen['covers'] + 1) or _TILE_HTML)
    return seen


def test_pornpics_default_scan_serves_covers_without_gdl(_spies):
    m = Match(url='https://www.pornpics.com/flexible/')
    m.page = 0
    items, err = PornpicsSource().scan(m)
    assert err is None and len(items) == 2
    assert _spies['covers'] == 1 and _spies['enum'] is None   # gallery-dl never launched.


def test_pornpics_include_albums_dives_via_gdl(_spies):
    m = Match(url='https://www.pornpics.com/flexible/')
    m.page = 0
    m.include_albums = True
    PornpicsSource().scan(m)
    assert _spies['covers'] == 0                    # No cover parsing.
    assert _spies['enum']['per_album'] is None      # Scan complete albums.


def test_pornpics_direct_gallery_url_bypasses_covers(_spies):
    m = Match(url='https://www.pornpics.com/galleries/flexible-girl-123/')
    m.page = 0
    PornpicsSource().scan(m)
    assert _spies['covers'] == 0                    # URL d'album → gallery-dl direct
    assert _spies['enum'] is not None


def test_pornpics_covers_failure_falls_back_to_bounded_gdl(monkeypatch, _spies):
    def boom(url):
        raise RuntimeError('site down')
    monkeypatch.setattr(image_sites, '_listing_html', boom)
    m = Match(url='https://www.pornpics.com/flexible/')
    m.page = 0
    items, err = PornpicsSource().scan(m)
    assert err is None
    assert _spies['enum']['per_album'] == 1         # Bounded fallback: one image per album.


@pytest.mark.plugins('scrape')
def test_scan_route_passes_include_albums_to_match(client, monkeypatch):
    seen = {}

    def fake_scan(self, match):
        seen['include_albums'] = getattr(match, 'include_albums', None)
        return [{'url': 'https://cdni.pornpics.com/x.jpg', 'title': '',
                 'thumbnail': None, 'type': 'image', 'platform': 'pornpics'}], None
    monkeypatch.setattr(PornpicsSource, 'scan', fake_scan)
    r = client.post('/api/scrape/scan',
                    json={'url': 'https://www.pornpics.com/flexible/',
                          'include_albums': True})
    assert r.status_code == 200
    assert seen['include_albums'] is True
    r = client.post('/api/scrape/scan',
                    json={'url': 'https://www.pornpics.com/flexible/'})
    assert r.status_code == 200
    assert seen['include_albums'] is False       # Default: covers only.
