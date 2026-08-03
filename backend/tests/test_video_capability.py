"""🎬 The `video` extra — where ffmpeg comes from, and what the app says when a
piece of the video lane is missing.

The whole point of this file is the second half. Today a .mp4 dropped into a bank
is skipped in SILENCE: the extension filter does not match, nothing is logged,
and the user is left thinking their file was scanned. The video lane must never
reproduce that, so the probe is required to NAME the piece that is missing.

Nothing here imports av, torch or ffmpeg — these tests describe the app's
behaviour when those are absent, which is the case they exist for.
"""
import sys

import pytest

from app import capabilities
from app.services import ffmpeg_tools


class _FakeImageioFfmpeg:
    def __init__(self, path):
        self._path = path

    def get_ffmpeg_exe(self):
        return self._path


# --- where the binary comes from ----------------------------------------------

def test_ffmpeg_prefers_the_binary_bundled_with_the_extra(monkeypatch, tmp_path):
    """imageio-ffmpeg ships a static binary, which is what makes the extra
    self-sufficient: the user installs nothing by hand."""
    bundled = tmp_path / 'ffmpeg.exe'
    bundled.write_bytes(b'')
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg',
                        _FakeImageioFfmpeg(str(bundled)))
    monkeypatch.setattr(ffmpeg_tools.shutil, 'which', lambda name: '/usr/bin/ffmpeg')

    assert ffmpeg_tools.ffmpeg_path() == str(bundled)


def test_ffmpeg_falls_back_to_the_one_already_on_the_system(monkeypatch):
    """A user who already has ffmpeg installed should not be made to download a
    second copy — the scraper already resolves it this way."""
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg', None)
    monkeypatch.setattr(ffmpeg_tools.shutil, 'which', lambda name: '/usr/bin/ffmpeg')

    assert ffmpeg_tools.ffmpeg_path() == '/usr/bin/ffmpeg'


def test_a_bundled_path_that_is_not_on_disk_is_not_believed(monkeypatch):
    """imageio-ffmpeg answers with a path whether or not the download completed.
    Trusting it blindly turns a half-finished install into 'ffmpeg not found'
    errors from deep inside an encode, instead of a missing-extra message."""
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg',
                        _FakeImageioFfmpeg('/nowhere/ffmpeg'))
    monkeypatch.setattr(ffmpeg_tools.shutil, 'which', lambda name: '/usr/bin/ffmpeg')

    assert ffmpeg_tools.ffmpeg_path() == '/usr/bin/ffmpeg'


def test_no_ffmpeg_anywhere_answers_none_instead_of_raising(monkeypatch):
    """Callers decide what to do about it; resolving must not be the thing that
    explodes."""
    monkeypatch.setitem(sys.modules, 'imageio_ffmpeg', None)
    monkeypatch.setattr(ffmpeg_tools.shutil, 'which', lambda name: None)

    assert ffmpeg_tools.ffmpeg_path() is None


# --- what the app says is missing ---------------------------------------------

def _probe(monkeypatch, *, decode=True, detect=True, encode=True, seen=None):
    # Route on the probe KEY, not on the import expression: the detect expression
    # legitimately contains 'av' too, and matching on it made both pieces answer
    # with the same value.
    def fake_import(key, python, expr):
        if seen is not None:
            seen[key] = python
        return decode if key.endswith('decode') else detect

    monkeypatch.setattr(capabilities, '_cached_import', fake_import)
    monkeypatch.setattr(capabilities.ffmpeg_tools, 'ffmpeg_path',
                        lambda: '/usr/bin/ffmpeg' if encode else None)
    return capabilities.probe_video()


def test_the_probe_is_ok_only_when_every_piece_is_present(monkeypatch):
    assert _probe(monkeypatch)['ok'] is True


@pytest.mark.parametrize('missing, word', [
    ('decode', 'av'),
    ('detect', 'shot detection'),
    ('encode', 'ffmpeg'),
])
def test_the_probe_names_the_piece_that_is_missing(monkeypatch, missing, word):
    """Three different absences, three different reasons. Collapsing them into one
    'video unavailable' is how a user ends up reinstalling the wrong thing."""
    result = _probe(monkeypatch, **{missing: False})

    assert result['ok'] is False
    assert word in result['detail'].lower()


def test_shot_detection_rides_the_environment_that_already_has_torch(monkeypatch):
    """TransNetV2 needs torch, and the app already manages an environment holding
    it for bank scoring. Installing a second copy would cost the user ~2.5 GB for
    nothing — the watermark detector settled this exact question the same way, and
    the probe has to resolve where the installer puts things or the two drift.

    Decoding is the opposite case: PyAV is imported IN-PROCESS by Flask, so it has
    to be the app's own interpreter, not the scoring one.
    """
    monkeypatch.setattr(capabilities.cfg, 'get',
                        lambda key, *a, **k: '/envs/scoring/python'
                        if key == 'bank_scoring.python' else None)
    seen = {}
    _probe(monkeypatch, seen=seen)

    assert seen['video_detect'] == '/envs/scoring/python'
    assert seen['video_decode'] == sys.executable


def test_the_probe_reports_each_piece_separately(monkeypatch):
    """The UI needs the parts, not just the sentence: decoding a bank and encoding
    a dataset are different actions and can be offered independently."""
    result = _probe(monkeypatch, encode=False)

    assert result['decode'] is True
    assert result['detect'] is True
    assert result['encode'] is False
