"""Pure-PIL technical quality metrics for the 🗃️ image bank (CPU, no GPU, no
numpy/cv2 — the Flask venv is deliberately light, and the quality pass must
work out of the box on every install, extras or not).

The three metrics follow the classic recipes (the same ones Crucible-style
curation tools use), reformulated for PIL:

* **Sharpness** — variance of the 4-neighbour Laplacian, measured PER TILE and
  aggregated over the SHARPEST regions, not over the whole frame. PIL's
  ``Kernel`` filter clamps its uint8 output, so the signed Laplacian is
  recovered from TWO clamped convolutions (kernel and its negation,
  ``scale=4`` so the extreme |L|=4·255 maps exactly to 255 — no value ever
  clamps) and the variance is computed from their histograms: at every pixel
  exactly one of the two passes is non-zero, so E[L²] = 16·(E[pos²]+E[neg²])
  and E[L] = 4·(E[pos]−E[neg]). That identity is per-pixel, so it holds over
  any subset — cropping the two filtered images gives exact per-tile moments
  for free. Low variance = blurry (the ~100 rule of thumb).

  Whole-frame variance punished exactly the images a curator wants most:
  a bokeh portrait is a small razor-sharp subject inside a large creamy
  background, and the background drags the average under the threshold
  (reported from the community). Scoring tile by tile and keeping a high
  percentile of the tiles restores the intended meaning of the threshold: "even the
  sharpest region of this image is soft → it really is blurry".
  Scores are therefore on a NEW scale (higher for anything with a sharp
  region); nothing breaks, since the threshold is applied at read time —
  banks scanned before this change pick up the new score at their next
  Quality re-scan.
* **Noise** — RMS of the residual against a Gaussian blur (σ≈1.1, the OpenCV
  5×5 default): high-frequency energy the blur removed. High = noisy/grainy.
  (Fine texture counts too — that's inherent to the method; it's a FLAG
  threshold, not a verdict.)
* **Uniformity** — plain grayscale standard deviation. Near zero = a flat or
  almost-empty frame (solid color, black frame, blank screenshot).

All metrics run on a grayscale working copy downscaled to a fixed
``ANALYSIS_MAX_SIDE`` long side, so scores are comparable across resolutions
and the per-image cost is bounded (a phone photo and a 4K export cost the
same). Raw scores are returned — thresholds live in config ('bank' section)
and are applied at read time.
"""
import math

from PIL import Image, ImageChops, ImageFilter, ImageStat

ANALYSIS_MAX_SIDE = 1024

_LAPLACIAN = (0, 1, 0,
              1, -4, 1,
              0, 1, 0)
_LAPLACIAN_NEG = tuple(-c for c in _LAPLACIAN)
# |conv| ≤ 4·255 for this kernel → dividing by 4 fits uint8 exactly: the two
# half-convolutions never clamp and the variance below is exact (mod rounding).
_LAP_SCALE = 4

# Sharpness is read on a grid of at most _TILE_GRID×_TILE_GRID tiles over the
# analysis copy; tiles never go below _TILE_MIN_SIDE px (a 20-px tile measures
# almost nothing and its variance swings wildly), so small images simply get a
# coarser grid — down to a single tile, i.e. the historical whole-frame score.
_TILE_GRID = 8
_TILE_MIN_SIDE = 32
# Aggregate = 90th percentile of the tile variances, not the max: the max is one
# tile, so a single JPEG-artefact block, a sensor hot spot or a burnt highlight
# would certify a soft image as sharp. p90 asks that ~a tenth of the frame be
# sharp — far below the share a bokeh subject occupies, far above one stray tile.
_TILE_PERCENTILE = 0.90

# σ of the reference Gaussian for the noise residual — matches OpenCV's implied
# sigma for its 5×5 default kernel (0.3·((5−1)·0.5−1)+0.8).
_NOISE_SIGMA = 1.1


def _moments(hist):
    """(mean, mean-of-squares) of a 256-bin PIL histogram."""
    n = sum(hist)
    if not n:
        return 0.0, 0.0
    m1 = sum(v * c for v, c in enumerate(hist)) / n
    m2 = sum(v * v * c for v, c in enumerate(hist)) / n
    return m1, m2


def _laplacian_variance(pos: Image.Image, neg: Image.Image, box) -> float:
    """Variance of the signed Laplacian over ``box``, from the histograms of the
    two half-convolutions (see module docstring). ``box`` must already exclude
    PIL's unfiltered 1-px border."""
    p1, p2 = _moments(pos.crop(box).histogram())
    n1, n2 = _moments(neg.crop(box).histogram())
    mean = _LAP_SCALE * (p1 - n1)
    return max(0.0, _LAP_SCALE * _LAP_SCALE * (p2 + n2) - mean * mean)


def _tile_boxes(box):
    """Split ``box`` into an ~even grid of at most _TILE_GRID² tiles, each at
    least _TILE_MIN_SIDE px per side where the box allows it."""
    x0, y0, x1, y1 = box
    cols = max(1, min(_TILE_GRID, (x1 - x0) // _TILE_MIN_SIDE))
    rows = max(1, min(_TILE_GRID, (y1 - y0) // _TILE_MIN_SIDE))
    xs = [x0 + round(i * (x1 - x0) / cols) for i in range(cols + 1)]
    ys = [y0 + round(j * (y1 - y0) / rows) for j in range(rows + 1)]
    return [(xs[i], ys[j], xs[i + 1], ys[j + 1])
            for j in range(rows) for i in range(cols)]


def _high_percentile(values) -> float:
    """Nearest-rank percentile (_TILE_PERCENTILE) of a list of tile variances."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    idx = min(len(ordered) - 1,
              max(0, math.ceil(_TILE_PERCENTILE * len(ordered)) - 1))
    return ordered[idx]


def analysis_copy(im: Image.Image) -> Image.Image:
    """Grayscale working copy, long side capped to ANALYSIS_MAX_SIDE.
    LANCZOS: a box/bilinear downscale would smear detail and systematically
    deflate the sharpness of large images."""
    g = im.convert('L')
    w, h = g.size
    m = max(w, h)
    if m > ANALYSIS_MAX_SIDE:
        r = ANALYSIS_MAX_SIDE / m
        g = g.resize((max(1, round(w * r)), max(1, round(h * r))), Image.LANCZOS)
    return g


def quality_metrics(im: Image.Image) -> dict:
    """Raw technical scores for one PIL image:
    {'blur_score', 'noise_score', 'uniformity_score'} (see module docstring)."""
    g = analysis_copy(im)
    # Sharpness: Laplacian variance via the two clamp-free half-convolutions.
    # PIL leaves a 1-px border UNFILTERED (raw grayscale values, huge once
    # squared) — crop to the interior before reading the histograms.
    # The convolutions run ONCE on the whole frame and the tiles are cropped out
    # of the RESULT: filtering each tile separately would invent a hard edge at
    # every tile border and inflate the score of a perfectly smooth image.
    w, h = g.size
    interior = (1, 1, max(2, w - 1), max(2, h - 1))
    pos = g.filter(ImageFilter.Kernel((3, 3), _LAPLACIAN, scale=_LAP_SCALE))
    neg = g.filter(ImageFilter.Kernel((3, 3), _LAPLACIAN_NEG, scale=_LAP_SCALE))
    blur = _high_percentile([_laplacian_variance(pos, neg, box)
                             for box in _tile_boxes(interior)])
    # Noise: RMS of the Gaussian residual.
    blurred = g.filter(ImageFilter.GaussianBlur(radius=_NOISE_SIGMA))
    _d1, d2 = _moments(ImageChops.difference(g, blurred).histogram())
    noise = d2 ** 0.5
    # Uniformity: grayscale std.
    uniformity = ImageStat.Stat(g).stddev[0]
    return {'blur_score': round(blur, 3),
            'noise_score': round(noise, 3),
            'uniformity_score': round(uniformity, 3)}
