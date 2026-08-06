"""Source universelle : garde SSRF, énumération générique, repli yt-dlp.

Tout est mocké — aucun appel réseau ni process gallery-dl."""
import subprocess

from app.scrape import netfetch
from app.scrape.sources import gdl, universal
from app.scrape.sources.universal import UniversalSource


class _Proc:
    """Faux CompletedProcess : seuls returncode/stdout/stderr sont lus."""

    def __init__(self, returncode=0, stdout='', stderr=''):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_unsupported_site_on_a_vetted_host_falls_back_to_ytdlp(monkeypatch, tmp_path):
    """gallery-dl sans extracteur (exit 64) sur un hôte vetté DOIT basculer sur
    yt-dlp. Historiquement faux : le kind était comparé à une phrase que personne
    n'émettait, donc la bascule n'a jamais eu lieu."""
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
        raise AssertionError('yt-dlp ne doit PAS être appelé sur un hôte non vetté')
    monkeypatch.setattr(netfetch, 'download_via_ytdlp', boom)

    ok, filename, err = UniversalSource().download(
        'https://unknown.example/thing', str(tmp_path / 'item'))

    assert ok is False and filename is None
    assert 'not vetted' in err


def test_auth_failure_is_reported_and_never_retried_via_ytdlp(monkeypatch, tmp_path):
    """Exit 16 = mur d'authentification, PAS « site inconnu » : on remonte
    l'erreur au lieu de retenter avec un autre outil."""
    monkeypatch.setattr(gdl.subprocess, 'run',
                        lambda *a, **k: _Proc(returncode=16, stderr='login required'))

    def boom(url, dest_base):
        raise AssertionError('yt-dlp ne doit PAS être appelé sur un échec auth')
    monkeypatch.setattr(netfetch, 'download_via_ytdlp', boom)

    ok, _filename, err = UniversalSource().download(
        'https://x.com/someone/status/1', str(tmp_path / 'item'))

    assert ok is False and 'auth' in err


# --- Garde SSRF : la source générique est la SEULE à accepter un hôte arbitraire,
# et son scan lance désormais gallery-dl dessus. Les sources dédiées matchent des
# hôtes nommés, une adresse privée ne les a jamais atteintes.
def test_match_refuses_non_public_urls():
    src = UniversalSource()
    for url in ('http://127.0.0.1/gallery',
                'http://localhost:8080/gallery',
                'http://192.168.1.10/gallery',
                'http://[::1]/gallery',
                'file:///etc/passwd'):
        assert src.match(url) is None, url


def test_match_still_accepts_a_public_http_url(monkeypatch):
    # example.test (domaine de test RFC 2606, SANS enregistrement DNS réel) :
    # on simule la résolution pour rester hermétique (aucun appel réseau) tout
    # en exerçant la vraie branche de classification d'IP du garde SSRF.
    # RFC 5737 (203.0.113.1, etc.) échoue ici : is_reserved → _ip_is_blocked
    # le rejette correctement. Adresse publique ordinaire pour tester la branche
    # accepte; ne cible ni ce poste ni le réseau (la garde cible les données perso).
    monkeypatch.setattr(
        netfetch.socket, 'getaddrinfo',
        lambda *a, **k: [(netfetch.socket.AF_INET, netfetch.socket.SOCK_STREAM,
                           6, '', ('93.184.216.34', 443))])
    assert UniversalSource().match('https://example.test/album/1') is not None


def test_enumerate_album_recursion_sentinel_carries_a_kind(monkeypatch):
    """Quand TOUS les albums échouent via le sentinel type -1 (pas via une
    exception/`_run_simulate` en erreur), l'erreur remontée par `enumerate()`
    doit rester une GdlError utilisable par `getattr(err, 'kind', None)` — pas
    un str nu redevenu invisible au branchement kind."""

    def fake_run_simulate(url, max_items, cookies, extra_opts, image_range=None):
        if 'category' in url:
            return [[6, 'https://x/album1/', {}]], None
        return [[-1, {'message': 'blocked by extractor'}]], None

    monkeypatch.setattr(gdl, '_run_simulate', fake_run_simulate)

    items, err = gdl.enumerate('https://x/category/')

    assert items is None
    assert getattr(err, 'kind', None) == 'toolerror'
