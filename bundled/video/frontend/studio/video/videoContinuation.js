/* ⏭ What a launch continues, and what is armed that this launch will not use.
 *
 * One click on ⏭ stages ONE picture — the last frame of the clip — and arms it
 * in BOTH places a launch can start from: the strip that "From an image"
 * walks, and the first frame guide a reference launch pins at frame 0. The
 * mode then decides which of the two runs, so changing your mind about the
 * mode keeps the continuation instead of losing it.
 *
 * Why it is written down rather than read off the strip: measured on
 * 2026-09-07, a continuation of a References clip was armed in the strip
 * ALONE. The strip is not rendered in References mode (the panel takes its
 * place), so the staged frame was invisible; Generate then built its launch
 * from the reference guide alone, dropped the join, and rendered a fresh clip
 * under a "Queued" toast. A launch may refuse a continuation — Text only
 * starts from no picture at all — but it may never ignore one quietly.
 */

/** `{ used, ignored }` for the mode in force.
 *
 * `used` — the clip ids this launch is joined behind, in strip order.
 * `ignored` — what stays armed but sits this launch out, each with the mode
 * that WOULD run it, so the notice can offer that mode rather than a lecture.
 * An id armed in both places counts once, and never as ignored while it runs.
 */
export function continuationState({ mode, sources = [], firstFrame = null } = {}) {
  const strip = [...new Set((sources || []).map((f) => f?.continues).filter(Boolean))];
  const guide = firstFrame?.continues || null;
  const used = mode === 'i2v' ? strip : (mode === 'ref2va' && guide ? [guide] : []);
  const seen = new Set(used);
  const ignored = [];
  for (const [id, home] of [...strip.map((id) => [id, 'i2v']), ...(guide ? [[guide, 'ref2va']] : [])]) {
    if (seen.has(id)) continue;
    seen.add(id);
    ignored.push({ id, mode: home });
  }
  return { used, ignored };
}

/** The mode's name as the buttons write it — the notice offers a mode, and a
 * notice that named it differently from the segment above would be a riddle. */
export const MODE_NAMES = { i2v: 'From an image', t2v: 'Text only', ref2va: 'References' };

/** What ⏭ does with THIS clip: a References clip continues with its cast (the
 * references are what hold its characters, and the seam is their guide at
 * frame 0), anything else continues from the picture alone. A reference clip
 * whose references are gone from the row cannot: it continues as an image. */
export function continuesAsReference(clip) {
  return clip?.mode === 'ref2va' && Array.isArray(clip?.references) && clip.references.length > 0;
}
