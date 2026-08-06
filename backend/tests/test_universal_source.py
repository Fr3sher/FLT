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
