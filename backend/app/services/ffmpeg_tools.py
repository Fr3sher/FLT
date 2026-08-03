"""Where the ffmpeg binary comes from.

The video lane needs ffmpeg for exactly ONE step — encoding a kept clip into the
dataset — and nothing else. Probing a file, reading its timestamps and pulling a
thumbnail frame all happen in-process through PyAV, so a missing binary disables
the export and leaves scanning, detection and triage working. That split is only
possible if "do we have ffmpeg?" is a question with its own answer, which is what
this module is.

Two sources, in order:

1. `imageio-ffmpeg`, a pip package that ships a static binary. This is what makes
   the extra self-sufficient — a Windows user who has never heard of ffmpeg
   installs the extra and the export works. It is why the video extra exists as a
   pip install at all rather than a "please download ffmpeg" note.
2. Whatever is on PATH. A user who already runs ffmpeg should not be made to
   download a second copy; the scraper already resolves it this way
   (scrape/netfetch.py).

NOT ffprobe. imageio-ffmpeg bundles ffmpeg alone, so an ffprobe-based inspection
would work on the developer's machine — where a full ffmpeg install is on PATH —
and fail on the install the extra was written for. PyAV answers the same
questions in-process, and the video lane needs it for decoding anyway.
"""
import os
import shutil


def ffmpeg_path():
    """Absolute path to a usable ffmpeg binary, or None.

    Never raises: callers decide what a missing encoder means for them, and
    resolution itself must not be the thing that fails.
    """
    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        # imageio-ffmpeg answers with a path whether or not its download ever
        # finished. Believing it turns a half-installed extra into "ffmpeg not
        # found" raised from inside an encode, instead of the missing-extra
        # message the user can act on.
        if bundled and os.path.isfile(bundled):
            return bundled
    except Exception:
        pass                      # not installed, or broken — fall through to PATH
    return shutil.which('ffmpeg')


def has_ffmpeg():
    """True when an encode is possible at all."""
    return ffmpeg_path() is not None
