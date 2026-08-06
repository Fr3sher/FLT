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
