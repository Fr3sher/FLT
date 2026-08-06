"""Instagram scan() : un profil légitimement sans publication est un résultat
vide, pas un échec ; un post unique qui refuse de se convertir en item reste
un vrai échec (finding #3 — verdicts différents pour deux formes de "aucun
média", cf. rapport).

Tout est mocké (`_build_loader`, `instaloader.Profile`/`Post`) : aucun réseau."""
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
