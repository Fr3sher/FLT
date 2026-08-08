"""The output canvas of a local generation — ONE calculation, both engines.

Klein and Krea used to size their results by unrelated rules. Klein rescaled the
source to a hardcoded 2 MP and kept the reference's shape; Krea asked for the
catalog card's shape but capped the budget at the reference's own pixel count.
The same dataset therefore held 2 MP Klein tiles next to 0.84 MP Krea ones, in
different shapes, with nothing on screen explaining either number.

This module is that single answer. Both helpers import `fit_output_size` from
here — not a copy each, because "the two engines produce the same size" has to be
a property of the code and not a coincidence between two call sites.

Two paths, deliberately different:
  * A dataset variation names its CARD ratio. `variations.output_megapixels` then
    decides the budget outright, upscale included — the dial is the instruction,
    and a reference that happens to be 0.85 MP must not silently overrule it.
  * A free reference edit names no ratio. It keeps the source geometry AND the
    no-upscale rule: the user cropped that frame on purpose, and inventing
    detail it never had is not what "edit this photo" means.
"""
import logging
import math

from .. import config as cfg

logger = logging.getLogger(__name__)

# The edit models drift above ~2 MP, which is also the ceiling of the dial.
MAX_OUTPUT_MP = 2.0
# Below this the canvas stops being a training image at all.
MIN_OUTPUT_MP = 0.5
_LATENT_MULTIPLE = 16


def _aspect_ratio(requested_aspect):
    """Return a positive finite ``W:H`` ratio, or None for an unusable request."""
    if not isinstance(requested_aspect, str):
        return None
    try:
        aw, ah = (float(part.strip()) for part in requested_aspect.split(':', 1))
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(aw) and math.isfinite(ah) and aw > 0 and ah > 0):
        return None
    ratio = aw / ah
    # A catalog ratio is deliberately modest (the widest shipped card is 16:9).
    # Treat pathological dimensions as invalid rather than letting them form an
    # impractical one-cell canvas or an enormous target side.
    if not math.isfinite(ratio) or not 1 / 32 <= ratio <= 32:
        return None
    return ratio


def _requested_canvas(ratio, budget):
    """Largest near-ratio 16-grid canvas that does not exceed ``budget``."""
    cells = max(1, int(budget // (_LATENT_MULTIPLE ** 2)))
    height_cells = max(1, int((cells / ratio) ** 0.5))
    width_cells = max(1, int(round(ratio * height_cells)))
    while width_cells * height_cells > cells:
        # Reduce the dimension that currently leaves the ratio furthest from its
        # requested value. This only runs on the 16px grid, so it cannot drift
        # above the pixel budget while finding a close ratio.
        if width_cells / height_cells > ratio:
            width_cells = max(1, width_cells - 1)
        else:
            height_cells = max(1, height_cells - 1)
    return width_cells * _LATENT_MULTIPLE, height_cells * _LATENT_MULTIPLE


def fit_output_size(width, height, max_mp=MAX_OUTPUT_MP, requested_aspect=None):
    """Return a 16-aligned output canvas for one generated image.

    A valid ``requested_aspect`` (``W:H``) is a dataset card asking for its own
    framing: it gets that ratio at the FULL ``max_mp`` budget, whether or not the
    reference holds that many pixels. With no ratio (or an invalid one), keep the
    source geometry and the no-upscale rule of the free reference edit.
    """
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        w = h = 0
    if w <= 0 or h <= 0:
        return 1024, 1024
    budget = max(0.1, float(max_mp)) * 1_000_000
    ratio = _aspect_ratio(requested_aspect)
    if ratio is not None:
        # The dial decides, upscale included. It used to be min(budget, w * h),
        # which is what made a 1024x832 reference cap every card at 0.84 MP while
        # the other engine rendered the same shot at 2 — see the module docstring.
        return _requested_canvas(ratio, budget)
    if w * h > budget:
        scale = (budget / (w * h)) ** 0.5
        w, h = w * scale, h * scale
    snap = lambda v: max(_LATENT_MULTIPLE,
                          int(round(v / _LATENT_MULTIPLE)) * _LATENT_MULTIPLE)
    ow, oh = snap(w), snap(h)
    source_ratio = w / h
    while ow * oh > budget:
        # Nearest-grid snapping can cross the pixel cap by a single 16px step.
        # Remove that step from the dimension that brings us closest to the
        # original source ratio, retaining the historic source-geometry path.
        if ow / oh > source_ratio:
            ow = max(_LATENT_MULTIPLE, ow - _LATENT_MULTIPLE)
        else:
            oh = max(_LATENT_MULTIPLE, oh - _LATENT_MULTIPLE)
    return ow, oh


def source_size(path):
    """The reference's VISUAL size (EXIF orientation applied), or a 1 MP square."""
    try:
        from PIL import Image
        from . import image_encoding
        with Image.open(path) as im:
            return image_encoding.visual_size_from_header(im)
    except Exception:
        # A source we cannot measure still deserves a job: 1 MP square is the
        # neutral fallback, not a crash.
        return (1024, 1024)


def variation_output_megapixels():
    """The ONE pixel budget both local engines render a dataset variation at.

    Not per engine: the point of the setting is that a dataset's shots are the
    same size whichever local engine produced them. 2.0 is Klein's historical
    hardcoded value, so an untouched install frames exactly as it always did.
    """
    raw = cfg.get('variations.output_megapixels')
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return MAX_OUTPUT_MP
    if not math.isfinite(value):
        return MAX_OUTPUT_MP
    return max(MIN_OUTPUT_MP, min(MAX_OUTPUT_MP, value))
