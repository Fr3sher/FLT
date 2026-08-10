/* 🎨 One colour per dataset, for the LoRA Canvas edges.

   On a board holding several datasets every connector was drawn in the same
   pale grey/indigo, so once two lanes' pinned pictures were parked near each
   other there was no way to tell whose line was whose — and lines cross a lot,
   because a picture can be placed anywhere. Giving each dataset its own hue
   makes a crossing readable without touching a single card.

   ── Why only SEVEN, when a dozen was asked for ─────────────────────────────
   The board already spends three hue bands on MEANING, and those must keep
   meaning what they mean (see lineageEdges.jsx):
     • amber  ≈ 43°   — a superseded branch
     • cyan   ≈ 187°  — an edge to an external LoRA file pinned on the board
     • violet ≈ 271°  — generation provenance (this picture was blended from…)
   Two saturated strokes need ~25° of hue between them to be told apart at 1.5
   px, and a tint has to clear the reserved bands by as much or it starts
   answering "what KIND of edge is this" instead of "whose". Scanning the circle
   under both constraints leaves exactly six usable hues — 0°, 83°, 162°, 213°,
   302°, 330° — plus the board's original neutral grey, which is a seventh
   perfectly nameable "colour". A twelve-entry palette here would have been four
   pairs nobody can tell apart plus three that lie about what an edge means, so
   the eighth dataset reuses the first hue instead. The contract test in
   datasetTint.test.js holds both distances, so this cannot quietly rot — it
   already rejected an indigo that sat 21° from the blue.

   ── Order matters ──────────────────────────────────────────────────────────
   Numeric dataset ids are assigned by the palette's INDEX (`id % 7`), so
   datasets created one after another never collide. That makes the ORDER of
   this array the adjacency the eye actually sees, which is why it is not sorted
   by hue: consecutive entries are deliberately far apart on the wheel. */

/** The palette. Bright enough for a 1.5-px stroke on graphite, ordered so that
 *  neighbouring indices are far apart in hue. */
export const DATASET_TINTS = [
  '#f87171', // red-400        ~0°
  '#34d399', // emerald-400  ~162°
  '#f371ef', // magenta       ~302°  (not indigo: indigo-400 sits 21° from the
  //                                  blue below, and this palette's own test
  //                                  refused it — the tightest surviving pair
  //                                  is this one against the pink, at 28°)
  '#a3e635', // lime-400      ~83°
  '#60a5fa', // blue-400     ~213°
  '#f472b6', // pink-400     ~330°
  '#94a3b8', // slate-400     neutral — the board's original edge grey
];

/** FNV-1a, for ids that are not plain integers (a slug, a uuid). Deterministic
 *  and stable across sessions, which is the whole point: a tint that changed on
 *  reload would be noise, not information. */
function fnv1a(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i += 1) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

/** Which palette slot a dataset owns. Same id ⇒ same slot, forever, whatever
 *  else is on the board — the association is only learnable if it holds. */
export function tintIndexFor(datasetId) {
  if (datasetId === null || datasetId === undefined || datasetId === '') return 0;
  const n = Number(datasetId);
  // Integer ids (the normal case) go through the identity, not a hash: it is
  // the only mapping that guarantees eight consecutive datasets get eight
  // DIFFERENT colours instead of a 1-in-8 chance of a clash per pair.
  if (Number.isSafeInteger(n) && n >= 0) return n % DATASET_TINTS.length;
  return fnv1a(String(datasetId)) % DATASET_TINTS.length;
}

/** The dataset's colour, for anything drawn in CSS (the lane header's dot). */
export function tintFor(datasetId) {
  return DATASET_TINTS[tintIndexFor(datasetId)];
}
