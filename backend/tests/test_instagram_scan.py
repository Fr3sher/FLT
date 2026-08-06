"""Instagram scan() : un profil légitimement sans publication est un résultat
vide, pas un échec ; un post unique qui refuse de se convertir en item reste
un vrai échec (finding #3 — verdicts différents pour deux formes de "aucun
média", cf. rapport).

Tout est mocké (`_build_loader`, `instaloader.Profile`/`Post`) : aucun réseau."""
import time
from types import SimpleNamespace

import instaloader

from app.scrape.sources import instagram
from app.scrape.validators import URLType


class _FakeEmptyProfile:
    def get_posts(self):
        return iter([])


class _FakeCarouselPostThatFailsToParse:
    """Carrousel dont l'extraction des slides échoue entièrement — aucun item
    récupérable, MAIS le post existe bel et bien (chargement réussi)."""
    shortcode = 'xyz789'
    typename = 'GraphSidecar'

    def get_sidecar_nodes(self):
        raise RuntimeError('sidecar parse failed')


class _FakeThrottledPost:
    """Ne devrait jamais être converti : le générateur du profil dort avant de
    le céder, assez longtemps pour dépasser `PROFILE_SCAN_TIMEOUT`."""
    shortcode = 'never-reached'


class _FakeThrottledProfile:
    """Simule le rate-controller RÉEL d'instaloader, qui DORT au lieu de lever
    (cf. module docstring / `PROFILE_SCAN_TIMEOUT`) — le test monkeypatche
    `PROFILE_SCAN_TIMEOUT` à une valeur minuscule pour ne pas dormir 60s réelles."""
    def get_posts(self):
        time.sleep(0.05)
        yield _FakeThrottledPost()


class _FakeProfileWhereEveryPostFailsConversion:
    """Deux posts vus, aucun ne survit à la conversion (ex. changement de mise
    en page côté Instagram) — pas la même chose qu'un profil sans publication."""
    def get_posts(self):
        return iter([_FakeCarouselPostThatFailsToParse(),
                     _FakeCarouselPostThatFailsToParse()])


def test_scan_profile_with_no_posts_is_empty_not_an_error(monkeypatch):
    monkeypatch.setattr(instagram, '_build_loader', lambda: SimpleNamespace(context=object()))
    monkeypatch.setattr(instaloader.Profile, 'from_username',
                        staticmethod(lambda context, username: _FakeEmptyProfile()))
    validation = SimpleNamespace(url_type=URLType.PROFILE, value='nobody', original_url=None)

    items, err = instagram.scan(validation)

    assert items is None
    assert getattr(err, 'kind', None) == 'empty'
    assert 'nobody' in err


def test_scan_single_with_no_extractable_media_stays_a_real_failure(monkeypatch):
    monkeypatch.setattr(instagram, '_build_loader', lambda: SimpleNamespace(context=object()))
    monkeypatch.setattr(instaloader.Post, 'from_shortcode',
                        staticmethod(lambda context, shortcode: _FakeCarouselPostThatFailsToParse()))
    validation = SimpleNamespace(url_type=URLType.POST, value='xyz789', original_url=None)

    items, err = instagram.scan(validation)

    assert items is None
    assert getattr(err, 'kind', None) is None
    assert 'usable media' in err


def test_scan_profile_timeout_with_zero_items_is_a_failure_not_empty(monkeypatch):
    """Probe from the reviewer: instaloader's rate controller SLEEPS rather than
    raising, so a throttled profile can hit the PROFILE_SCAN_TIMEOUT cap with
    zero items collected and no exception raised — before this fix that path
    fell into kind='empty', indistinguishable from a profile with no posts."""
    monkeypatch.setattr(instagram, '_build_loader', lambda: SimpleNamespace(context=object()))
    monkeypatch.setattr(instagram, 'PROFILE_SCAN_TIMEOUT', 0.01)
    monkeypatch.setattr(instaloader.Profile, 'from_username',
                        staticmethod(lambda context, username: _FakeThrottledProfile()))
    validation = SimpleNamespace(url_type=URLType.PROFILE, value='throttled', original_url=None)

    items, err = instagram.scan(validation)

    assert items is None
    assert err is not None
    assert getattr(err, 'kind', None) != 'empty'
    assert 'timed out' in err.lower()


def test_scan_profile_where_every_post_fails_conversion_is_a_failure_not_empty(monkeypatch):
    """Every post fails conversion (systematic layout change) — zero items with
    no exception raised, but posts WERE seen: also fell into kind='empty'
    before the fix."""
    monkeypatch.setattr(instagram, '_build_loader', lambda: SimpleNamespace(context=object()))
    monkeypatch.setattr(instaloader.Profile, 'from_username',
                        staticmethod(lambda context, username: _FakeProfileWhereEveryPostFailsConversion()))
    validation = SimpleNamespace(url_type=URLType.PROFILE, value='brokenlayout', original_url=None)

    items, err = instagram.scan(validation)

    assert items is None
    assert err is not None
    assert getattr(err, 'kind', None) != 'empty'
    assert 'none could be read' in err.lower()
