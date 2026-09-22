"""Universal source: SSRF guard, generic enumeration, yt-dlp fallback. All calls are
mocked: no network or gallery-dl process."""

import pytest

pytestmark = pytest.mark.plugins('scrape')


from app.scrape import netfetch
from lds_scrape.sources import gdl
from lds_scrape.sources.universal import UniversalSource


class _Proc:
    """Faux CompletedProcess : seuls returncode/stdout/stderr sont lus."""

    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_unsupported_site_on_a_vetted_host_falls_back_to_ytdlp(monkeypatch, tmp_path):
    """gallery-dl exit64 (no extractor) on a vetted host MUST fall back to yt-dlp.
    Previously kind was compared with a phrase no caller emitted, preventing the
    fallback."""
    monkeypatch.setattr(gdl.subprocess, 'run',
                        lambda *a, **k: _Proc(returncode=64, stderr='Unsupported URL'))
    called = {}

    def fake_ytdlp(url, dest_base):
        called['url'] = url
        return True, 'video.mp4', None
    monkeypatch.setattr(netfetch, 'download_via_ytdlp', fake_ytdlp)

    ok, filename, err = UniversalSource().download(
        'https://x.com/someone/status/1', str(tmp_path / 'item'))

    assert (ok, filename, err) == (True, 'video.mp4', None)
    assert called['url'] == 'https://x.com/someone/status/1'


def test_unsupported_site_on_an_unvetted_host_refuses_instead_of_fetching(
        monkeypatch, tmp_path):
    monkeypatch.setattr(gdl.subprocess, 'run',
                        lambda *a, **k: _Proc(returncode=64, stderr='Unsupported URL'))

    def boom(url, dest_base):
        raise AssertionError('yt-dlp must not run for an unvetted host')
    monkeypatch.setattr(netfetch, 'download_via_ytdlp', boom)

    ok, filename, err = UniversalSource().download(
        'https://unknown.example/thing', str(tmp_path / 'item'))

    assert ok is False and filename is None
    assert 'not vetted' in err


def test_auth_failure_is_reported_and_never_retried_via_ytdlp(monkeypatch, tmp_path):
    """Exit16 means an authentication wall, not an unknown site: report the failure
    rather than trying another tool."""
    monkeypatch.setattr(gdl.subprocess, 'run',
                        lambda *a, **k: _Proc(returncode=16, stderr='login required'))

    def boom(url, dest_base):
        raise AssertionError('yt-dlp must not run after an authentication failure')
    monkeypatch.setattr(netfetch, 'download_via_ytdlp', boom)

    ok, _filename, err = UniversalSource().download(
        'https://x.com/someone/status/1', str(tmp_path / 'item'))

    assert ok is False and 'auth' in err


# SSRF guard: the generic source alone accepts arbitrary hosts and launches gallery-dl
# against them. Dedicated sources match named hosts, so private addresses cannot reach
# them.
def test_match_refuses_non_public_urls():
    src = UniversalSource()
    for url in ('http://127.0.0.1/gallery',
                'http://localhost:8080/gallery',
                'http://192.168.1.10/gallery',
                'http://[::1]/gallery',
                'file:///etc/passwd'):
        assert src.match(url) is None, url


def test_match_still_accepts_a_public_http_url(monkeypatch):
    # Use example.test with mocked DNS for an isolated test of real SSRF IP
    # classification. RFC5737 reserved addresses are correctly rejected, so a synthetic
    # ordinary public address exercises the accepted branch without contacting it or
    # using a personal network address.
    monkeypatch.setattr(
        netfetch.socket, 'getaddrinfo',
        lambda *a, **k: [(netfetch.socket.AF_INET, netfetch.socket.SOCK_STREAM,
                           6, '', ('93.184.216.34', 443))])
    assert UniversalSource().match('https://example.test/album/1') is not None


def test_classify_exit_none_is_not_silently_a_success():
    """subprocess.run never returns returncode=None, but a poor test double may. A
    falsiness check treated None as success0 and then an empty scan. Require
    equality to0: an unusable exit code remains explicit toolerror, never
    disguised success."""
    assert gdl.classify_exit(0) is None
    assert gdl.classify_exit(None) == 'toolerror'


def test_enumerate_album_recursion_sentinel_carries_a_kind(monkeypatch):
    """When all albums fail through the type-1 sentinel, enumerate must return
    GdlError with readable kind, not a plain string that bypasses classification."""

    def fake_run_simulate(url, max_items, cookies, extra_opts, image_range=None):
        if 'category' in url:
            return [[6, 'https://x/album1/', {}]], None
        return [[-1, {'message': 'blocked by extractor'}]], None

    monkeypatch.setattr(gdl, '_run_simulate', fake_run_simulate)

    items, err = gdl.enumerate('https://x/category/')

    assert items is None
    assert getattr(err, 'kind', None) == 'toolerror'


# Generic enumeration.
from lds_scrape.sources.base import Match   # noqa: E402  (grouped with its tests)


def _spy_enumerate(monkeypatch, items=None, err=None):
    seen = {}

    def fake(url, **kw):
        seen['url'] = url
        seen.update(kw)
        return items, err
    monkeypatch.setattr(gdl, 'enumerate', fake)
    return seen


def test_scan_returns_every_image_of_the_page(monkeypatch):
    found = [{'url': f'https://cdn.example.test/{i}.jpg', 'title': '',
              'thumbnail': None, 'type': 'image', 'platform': 'generic'}
             for i in range(3)]
    seen = _spy_enumerate(monkeypatch, items=found)
    m = Match(url='https://example.test/album/1')
    m.page = 0

    items, err = UniversalSource().scan(m)

    assert err is None and items == found
    assert seen['platform'] == 'generic'
    assert seen['per_album'] == 1          # Default: one cover per album.
    assert seen['image_range'] == '1-120'


def test_scan_dives_into_albums_only_when_asked(monkeypatch):
    seen = _spy_enumerate(monkeypatch, items=[{'url': 'https://cdn.example.test/a.jpg',
                                               'title': '', 'thumbnail': None,
                                               'type': 'image', 'platform': 'generic'}])
    m = Match(url='https://example.test/albums/')
    m.page = 0
    m.include_albums = True

    UniversalSource().scan(m)

    assert seen['per_album'] is None       # Scan complete albums.


def test_scan_walks_the_listing_window_on_later_pages(monkeypatch):
    seen = _spy_enumerate(monkeypatch, items=[{'url': 'https://cdn.example.test/a.jpg',
                                               'title': '', 'thumbnail': None,
                                               'type': 'image', 'platform': 'generic'}])
    m = Match(url='https://example.test/album/1')
    m.page = 2

    UniversalSource().scan(m)

    assert seen['image_range'] == '241-360'


def test_a_blocked_scan_is_an_error_never_an_empty_result(monkeypatch):
    """Surface429, authentication and DDoS-Guard failures. Reporting them as no
    images repeats the Erome regression."""
    _spy_enumerate(monkeypatch, err=gdl.GdlError('gallery-dl: auth (429).', 'auth'))
    m = Match(url='https://example.test/album/1')
    m.page = 0

    items, err = UniversalSource().scan(m)

    assert items is None
    assert '429' in err


def test_a_genuinely_empty_page_carries_its_kind_for_the_route_to_read(monkeypatch):
    """kind=empty means gallery-dl completed successfully without media (deleted
    post, empty album or wrong page type). Forward GdlError with readable kind;
    conversion to an empty200 response belongs only in routes/scrape.py, which
    handles all gallery-dl sources. Duplicating it here would create divergent
    rules."""
    _spy_enumerate(monkeypatch,
                   err=gdl.GdlError('gallery-dl: no media found.', 'empty'))
    m = Match(url='https://example.test/album/1')
    m.page = 0

    items, err = UniversalSource().scan(m)

    assert items is None
    assert getattr(err, 'kind', None) == 'empty'


def test_a_site_gallery_dl_does_not_know_still_yields_the_single_media(monkeypatch):
    """Legacy fallback returns one video item so vetted hosts reach yt-dlp during
    download. A single item is not pageable."""
    _spy_enumerate(monkeypatch,
                   err=gdl.GdlError('gallery-dl: unsupported (no extractor).', 'unsupported'))
    m = Match(url='https://x.com/someone/status/1')
    m.page = 0

    items, err = UniversalSource().scan(m)

    assert err is None
    assert items == [{'url': 'https://x.com/someone/status/1',
                      'title': 'https://x.com/someone/status/1',
                      'thumbnail': None, 'type': 'video', 'platform': 'generic'}]
    assert m.paginated is False


def test_exit_zero_with_no_stdout_is_classified_empty_not_unclassified(monkeypatch):
    """gallery-dl may exit0 without stdout for a valid page without media.
    classify_exit(0) returns None, so _run_simulate must explicitly assign
    kind=empty; otherwise scan treats it as a generic error and returns502 instead
    of200/count=0. The route-level test covers the matching conversion contract."""
    monkeypatch.setattr(gdl.subprocess, 'run',
                        lambda *a, **k: _Proc(returncode=0, stdout='', stderr=''))

    entries, err = gdl._run_simulate('https://example.test/album/1', 60, None, None)

    assert entries is None
    assert getattr(err, 'kind', None) == 'empty'

    _spy_enumerate(monkeypatch,
                   err=gdl.GdlError('gallery-dl: empty output (no data).', 'empty'))
    m = Match(url='https://example.test/album/1')
    m.page = 0

    items, scan_err = UniversalSource().scan(m)

    assert items is None
    assert getattr(scan_err, 'kind', None) == 'empty'
