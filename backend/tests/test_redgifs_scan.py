"""RedGifs scan() : un profil/niche légitimement sans vidéo est un résultat vide,
pas un échec (finding #3 — la règle « empty est honoré partout » n'était payée
que pour la famille gallery-dl ; RedGifs répondait 502 sur un profil vide).

Tout est mocké (client RedGifs) : aucun appel réseau."""
from types import SimpleNamespace

from app.scrape.sources import redgifs
from app.scrape.validators import URLType


def test_scan_returns_empty_not_error_for_a_profile_with_no_videos(monkeypatch):
    monkeypatch.setattr(redgifs.client, 'get_token', lambda: 'tok')
    monkeypatch.setattr(redgifs.client, 'iter_user', lambda username: iter([]))
    validation = SimpleNamespace(url_type=URLType.PROFILE, value='nobody')

    items, err = redgifs.scan(validation)

    assert err is None
    assert items == []


def test_scan_returns_empty_not_error_for_a_niche_with_no_videos(monkeypatch):
    monkeypatch.setattr(redgifs.client, 'get_token', lambda: 'tok')
    monkeypatch.setattr(redgifs.client, 'iter_niche', lambda niche: iter([]))
    validation = SimpleNamespace(url_type=URLType.NICHE, value='empty-niche')

    items, err = redgifs.scan(validation)

    assert err is None
    assert items == []


def test_scan_still_returns_items_for_a_populated_profile(monkeypatch):
    monkeypatch.setattr(redgifs.client, 'get_token', lambda: 'tok')
    monkeypatch.setattr(redgifs.client, 'iter_user',
                        lambda username: iter([{'id': 'abc', 'urls': {}}]))
    validation = SimpleNamespace(url_type=URLType.PROFILE, value='someone')

    items, err = redgifs.scan(validation)

    assert err is None
    assert len(items) == 1
    assert items[0]['url'] == 'https://www.redgifs.com/watch/abc'


def test_a_missing_single_video_stays_a_real_error_not_an_empty_result(monkeypatch):
    """VIDEO (média unique) : l'échec du lookup reste une vraie erreur, pas un
    « rien ici » — non touché par ce finding (cf. rapport)."""
    monkeypatch.setattr(redgifs.client, 'get_token', lambda: 'tok')
    monkeypatch.setattr(redgifs.client, 'get_single_video', lambda video_id: None)
    validation = SimpleNamespace(url_type=URLType.VIDEO, value='deadbeef')

    items, err = redgifs.scan(validation)

    assert items is None
    assert 'not found' in err


def test_scan_reports_a_failure_not_an_empty_success_when_profile_is_rate_limited(monkeypatch):
    """Probe from the reviewer: a 429 on the profile page must not report an
    empty success. Before the fix, `_iter_paged` swallowed EVERY HTTP error
    (429/403/5xx/timeout) and just `return`ed, ending the generator — a
    rate-limited profile then yielded zero items and `scan()` answered
    ([], None): HTTP 200, count 0, "No images found on this page." """
    def _rate_limited(username):
        raise redgifs.RedGifsAbort("RedGifs: HTTP 429.")
        yield  # pragma: no cover - unreachable, keeps this a generator function

    monkeypatch.setattr(redgifs.client, 'get_token', lambda: 'tok')
    monkeypatch.setattr(redgifs.client, 'iter_user', _rate_limited)
    validation = SimpleNamespace(url_type=URLType.PROFILE, value='throttled')

    items, err = redgifs.scan(validation)

    assert items is None
    assert err is not None
    assert 'rate' in err.lower() or 'blocked' in err.lower()


def test_scan_reports_a_failure_not_an_empty_success_when_niche_is_rate_limited(monkeypatch):
    def _rate_limited(niche):
        raise redgifs.RedGifsAbort("RedGifs: HTTP 429.")
        yield  # pragma: no cover - unreachable, keeps this a generator function

    monkeypatch.setattr(redgifs.client, 'get_token', lambda: 'tok')
    monkeypatch.setattr(redgifs.client, 'iter_niche', _rate_limited)
    validation = SimpleNamespace(url_type=URLType.NICHE, value='throttled-niche')

    items, err = redgifs.scan(validation)

    assert items is None
    assert err is not None
    assert 'rate' in err.lower() or 'blocked' in err.lower()


def test_scan_returns_partial_when_rate_limited_after_collecting_some_items(monkeypatch):
    """Pre-existing bug the reviewer also verified: a 429 on page 2 after page 1
    succeeded used to return 1 item with err=None and no truncation signal, while
    dozens of advertised pages were refused. Now it must carry `partial=True`."""
    def _partial(username):
        yield {'id': 'abc', 'urls': {}}
        raise redgifs.RedGifsAbort("RedGifs: HTTP 429.")

    monkeypatch.setattr(redgifs.client, 'get_token', lambda: 'tok')
    monkeypatch.setattr(redgifs.client, 'iter_user', _partial)
    validation = SimpleNamespace(url_type=URLType.PROFILE, value='throttled')

    items, err = redgifs.scan(validation)

    assert err is None
    assert len(items) == 1
    assert getattr(items, 'partial', False) is True
