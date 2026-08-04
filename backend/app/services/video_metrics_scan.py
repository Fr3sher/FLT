"""The metrics scan: one decode per clip feeds every measurement.

The arithmetic lives in video_metrics.py; this module owns the plumbing, and the
plumbing is where the money is. Decoding is ~85 % of this lane's cost (measured
on a real 4.5-hour corpus once shot detection moved to the GPU), so motion,
exposure, sharpness and freeze detection all come out of ONE pass over the
frames. Written as four passes, the lane would cost four times its only
expensive part.

THE MOTION-VECTOR TRAP, PINNED HERE BECAUSE IT WAS MEASURED HERE. H.264 already
contains motion vectors — the codec computed them to compress — and ffmpeg
exports them for free: +0.09 s on a 15.6 s file, two million vectors, zero GPU.
But the export option must be set on the STREAM's codec context. The container
form, `av.open(path, options={'flags2': '+export_mvs'})`, is the intuitive one;
it runs, decodes, raises nothing and yields ZERO vectors. Every clip would then
measure motion_mean == 0 and the still-clip filter would flag the entire bank.
`MV_OPTIONS_TARGET` exists so a refactor that moves the option back cannot pass
review by looking plausible.

Frames are measured at ANALYSIS_WIDTH, not full size: a Laplacian over 1080p
costs more than the decode itself, while at analysis size the whole measurement
rides inside the decode's own budget — the same reasoning as the image lane's
analysis_copy().
"""
import json
import logging
import math

from ..extensions import db
from ..models import VideoBank, VideoClip, VideoSource
from . import video_metrics

logger = logging.getLogger(__name__)

# The export option and WHERE it must land. Data, not prose, so the test that
# pins the working form fails loudly if a refactor "simplifies" it back to the
# container call that yields zero vectors.
MV_OPTIONS = {'flags2': '+export_mvs'}
MV_OPTIONS_TARGET = 'stream_codec_context'

# Long-side target for the per-frame analysis copy. Small enough that the
# Laplacian is cheap, large enough that real softness is still visible at it.
ANALYSIS_WIDTH = 160

# A 3x3 Laplacian as plain nested loops would be unusably slow in Python; numpy
# ships with PyAV, so the frame math uses it — but ONLY inside the decode seam,
# so the module stays importable (and the scan testable) without either.


def _read_clip_frames(path, start_s, end_s, fps):
    """Decode ONE clip's segment and return per-frame readings:
    [{'luma': 0..1, 'sharp': laplacian-variance, 'motion': normalised-magnitude}].

    The single seam that touches PyAV/numpy. Raises on a broken segment — the
    caller turns that into 'unreadable' for THIS clip and moves on.
    """
    import av
    import numpy as np

    frames = []
    with av.open(path) as container:
        stream = container.streams.video[0]
        stream.thread_type = 'AUTO'
        # THE STREAM, not the container — see the module docstring.
        stream.codec_context.options = dict(MV_OPTIONS)
        diag = math.hypot(stream.codec_context.width or 1,
                          stream.codec_context.height or 1)
        try:
            container.seek(int(start_s / (stream.time_base or 1)), stream=stream)
        except Exception:                    # noqa: BLE001 — some streams refuse
            pass                             # seeking; decoding from 0 still works
        prev_small = None
        for frame in container.decode(stream):
            t = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
            if t < start_s:
                continue
            if t > end_s:
                break
            # Grayscale analysis copy, reduced BEFORE any math.
            gray = frame.reformat(width=ANALYSIS_WIDTH,
                                  height=max(2, int(ANALYSIS_WIDTH * frame.height
                                                    / max(frame.width, 1))),
                                  format='gray')
            arr = gray.to_ndarray().astype(np.float32)
            luma = float(arr.mean()) / 255.0
            # Laplacian variance via shifted sums — vectorised, no kernel loop.
            lap = (arr[1:-1, :-2] + arr[1:-1, 2:] + arr[:-2, 1:-1]
                   + arr[2:, 1:-1] - 4.0 * arr[1:-1, 1:-1])
            sharp = float(lap.var())
            # Motion from the bitstream's own vectors when present; falling back
            # to frame differencing for intra-only frames, which carry none.
            motion = None
            for sd in frame.side_data:
                if 'MOTION_VECTOR' in str(sd.type).upper():
                    a = sd.to_ndarray()
                    scale = max(int(a['motion_scale'][0]), 1) if len(a) else 1
                    if len(a):
                        motion = float(np.hypot(a['motion_x'] / scale,
                                                a['motion_y'] / scale).mean()) / diag
                    break
            if motion is None:
                motion = (float(np.abs(arr - prev_small).mean()) / 255.0
                          if prev_small is not None else 0.0)
            prev_small = arr
            frames.append({'luma': luma, 'sharp': sharp, 'motion': motion})
    return frames


def run_metrics(bank_id, remeasure=False):
    """Measure every clip of a bank that has not been measured yet.

    Same resume contract as every other pass: a clip's summary is written in the
    same transaction that produced it, so stopping loses nothing and a re-run
    pays only for what the first run had not reached. One broken clip costs that
    clip — a bank is scanned in bulk, and a bitstream error in file 200 must not
    throw away 199 summaries.
    """
    bank = db.session.get(VideoBank, bank_id)
    if bank is None:
        return {'measured': 0, 'unreadable': 0}
    q = (VideoClip.query.filter_by(bank_id=bank_id)
         .join(VideoSource, VideoSource.id == VideoClip.source_id)
         .filter(VideoSource.probe_state == 'ok'))
    if not remeasure:
        q = q.filter(VideoClip.metrics_json.is_(None))
    rows = q.order_by(VideoClip.id.asc()).all()

    measured = unreadable = 0
    from .video_bank_service import _abs_source_path
    for clip in rows:
        src = db.session.get(VideoSource, clip.source_id)
        # The same containment-checked resolver every other reader uses: a
        # relpath is data from a database, and resolving it unchecked is how
        # `..` reads a file the bank was never pointed at.
        path = _abs_source_path(bank, src.relpath)
        fps = src.fps_native or 25.0
        if not path:
            summary = video_metrics.summarise([], fps)
            clip.metrics_json = json.dumps(summary)
            unreadable += 1
            db.session.commit()
            continue
        try:
            frames = _read_clip_frames(path, clip.start_s, clip.end_s, fps)
            summary = video_metrics.summarise(frames, fps)
        except Exception as e:               # noqa: BLE001 — per-clip failure
            logger.warning('metrics: clip %s unreadable: %s', clip.id, e)
            summary = video_metrics.summarise([], fps)
        # sharpest_frame_s is relative to the segment's head; store it absolute
        # so the thumbnail pass can seek straight to it.
        if summary.get('sharpest_frame_s') is not None:
            summary['sharpest_frame_s'] += clip.start_s
        clip.metrics_json = json.dumps(summary)
        if summary['metrics_state'] == 'ok':
            measured += 1
        else:
            unreadable += 1
        db.session.commit()                  # the resume contract, per clip
    return {'measured': measured, 'unreadable': unreadable}
