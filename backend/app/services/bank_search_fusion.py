"""Reciprocal Rank Fusion over the ranked lists several search engines return.

Bank search can run more than one embedding engine — SigLIP 2 for fine-grained
and multilingual semantics, a LAION CLIP for the unfiltered concepts SigLIP 2
was never trained on. Their results have to be combined, and they cannot be
combined by score: vectors from different CLIP configurations are not
comparable (see ``infer/clip_image_embed_infer.py``), and their cosines sit on
unrelated scales with unrelated temperatures. Averaging or thresholding across
them returns a number that is wrong without looking wrong.

So scores stop at each engine's boundary and only ORDER crosses. RRF scores an
item as ``sum(1 / (K + rank))`` over the engines that ranked it, rank 1-based.

The consequence that shapes the rest of the feature: fusing ONE list returns
that list unchanged, because ``1 / (K + rank)`` is strictly decreasing in rank.
An install that never built a second index gets its single engine's results
verbatim, down this same code path. The degraded case is the general case at
n=1, not a branch to maintain.
"""
from __future__ import annotations

# The damping term from the original RRF paper. Large enough that the gap
# between rank 1 and rank 2 does not dwarf a second engine's agreement, which
# is what makes consensus outrank a single engine's confidence.
RRF_K = 60


def rrf(ranked_lists, k=RRF_K, limit=None):
    """Fuse ``{engine: [item_id, ...]}`` into ``[(item_id, score, engines)]``.

    Each list is ordered best-first. Returns rows ordered best-first, where
    ``engines`` is the alphabetically sorted tuple of engines that ranked the
    item — the caller needs it to report which engine answered.

    Ties break on ``item_id`` so the ranking never depends on dict iteration
    order or float noise.
    """
    if k <= 0:
        raise ValueError(f'RRF k must be positive, got {k!r}')

    scores: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    for engine, items in ranked_lists.items():
        seen: set[str] = set()
        for rank, item in enumerate(items, 1):
            # A repeated item keeps its BEST rank instead of accumulating a
            # second contribution — a malformed engine result must not be able
            # to buy score by listing the same image twice.
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            sources.setdefault(item, set()).add(engine)

    fused = sorted(
        ((item, score, tuple(sorted(sources[item])))
         for item, score in scores.items()),
        key=lambda row: (-row[1], row[0]))
    return fused[:limit] if limit is not None else fused
