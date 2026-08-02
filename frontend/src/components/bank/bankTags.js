/**
 * Turning ONE image's caption into the chips you can filter the bank by.
 *
 * Asked for by the maintainer: "let me open an image, see its tags, tick the
 * ones I care about, and show me the other images that have them". It is the
 * complement of 🎯 Similar to selected, not a rival — and the difference has to
 * stay legible in the UI, because the two answer different questions:
 *
 *   🎯 Similar to selected  — visual similarity, from CLIP embeddings. A black
 *                             box: it works on images nobody captioned, and it
 *                             cannot tell you WHY two images landed together.
 *   🏷️ Tags from this image — attributes YOU picked, matched as words. Fully
 *                             legible (you can read the chips you ticked), and
 *                             it can only ever see what a caption put in words.
 *
 * WHAT A CHIP IS. Captions in this app come in two shapes, so the split does too
 * — the same distinction `utils/tagFilter.js` draws for the dataset grid:
 *
 *  • BOORU ("a woman, red dress, balcony, golden hour") — commas ARE the tag
 *    separator, so each segment is a chip, whole and unsplit. This is detected,
 *    not configured: several commas and short segments between them.
 *  • PROSE ("a woman in a red dress standing on a balcony") — there are no tag
 *    boundaries to read, so words are the best available unit. Grammar words
 *    carry no visual meaning and would produce a wall of useless chips, so a
 *    stop list drops them.
 *
 * The honest limits, stated here and repeated in the UI:
 *  • A prose caption yields WORDS, not concepts: "golden hour" becomes two chips
 *    ("golden", "hour"), and ticking both means "captions mentioning both words",
 *    not "captions about golden hour".
 *  • A chip can only find what a captioner wrote down. An attribute nobody
 *    captioned is invisible to this, however plainly it is in the picture.
 */

/** Words that survive every caption and mean nothing visually. Deliberately dull
 *  and short: a stop list that tries to be clever starts eating real subjects
 *  ("light", "young", "long" are NOT here on purpose). */
const STOP = new Set([
  'a', 'an', 'the', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'with', 'from',
  'for', 'by', 'as', 'is', 'are', 'was', 'were', 'be', 'being', 'been', 'it',
  'its', 'this', 'that', 'these', 'those', 'there', 'here', 'her', 'his',
  'their', 'them', 'they', 'he', 'she', 'him', 'you', 'your', 'we', 'our',
  'has', 'have', 'had', 'while', 'into', 'onto', 'over', 'under', 'out', 'up',
  'down', 'off', 'about', 'above', 'below', 'very', 'some', 'both', 'than',
  'then', 'so', 'but', 'if', 'not', 'no', 'photo', 'image', 'picture', 'shot',
]);

/** Longest chip we keep. A whole sentence that slipped through as one booru
 *  segment is not a tag, and a 90-character chip breaks every layout. */
const MAX_CHIP_LEN = 32;
/** Enough chips to choose from, few enough to read at 400 px. */
export const MAX_CHIPS = 24;

const clean = (s) => (s || '').trim().toLowerCase();

/**
 * Booru or prose? Commas alone are not the test — a prose caption uses them too
 * ("a woman, seen from behind, on a balcony"). What separates the two is that
 * booru segments are SHORT: the tag list has many commas and few words between
 * them. Falling back to prose is the safe direction: prose splitting always
 * yields usable chips, while treating a sentence as one booru tag yields one
 * unusable chip.
 */
export function captionStyle(caption) {
  const parts = (caption || '').split(',').map((s) => s.trim()).filter(Boolean);
  if (parts.length < 3) return 'prose';
  const words = parts.map((p) => p.split(/\s+/).length);
  const avg = words.reduce((a, b) => a + b, 0) / words.length;
  return avg <= 3.5 ? 'booru' : 'prose';
}

/**
 * The chips for one caption, in the order they appear (a reader scanning the
 * caption finds them where they expect), de-duplicated, capped.
 * Returns [] for an empty/absent caption — the caller then says "this image has
 * no caption yet" rather than showing an empty tag row.
 */
export function captionChips(caption) {
  const style = captionStyle(caption);
  const raw = style === 'booru'
    ? (caption || '').split(',')
    // Prose: cut on everything that is not a letter, a digit or an inner
    // hyphen/apostrophe, so "t-shirt" and "woman's" survive as single words.
    : (caption || '').split(/[^\p{L}\p{N}'’-]+/u);
  const out = [];
  const seen = new Set();
  for (const piece of raw) {
    const tag = clean(piece).replace(/^[-'’]+|[-'’]+$/g, '');
    if (!tag || tag.length > MAX_CHIP_LEN) continue;
    // Single letters and bare numbers are never a useful filter.
    if (tag.length < 2 || /^\d+$/.test(tag)) continue;
    if (style === 'prose' && STOP.has(tag)) continue;
    if (seen.has(tag)) continue;
    seen.add(tag);
    out.push(tag);
    if (out.length >= MAX_CHIPS) break;
  }
  return out;
}

/** The query value for the `tags` parameter: the ticked chips, comma-joined.
 *  Empty selection ⇒ null, i.e. "no tag filter", never an empty-string filter
 *  that would match everything or nothing depending on the server's mood. */
export function tagsParam(selected) {
  const list = [...(selected || [])].map(clean).filter(Boolean);
  return list.length ? list.join(',') : null;
}

/** How the active tag filter reads above the grid. AND is stated in words, not
 *  left to be inferred from the chips: "red + dress" showing images that have
 *  only one of the two would be a silent lie. */
export function tagFilterSummary(selected) {
  const list = [...(selected || [])];
  if (!list.length) return '';
  if (list.length === 1) return `Showing images whose caption mentions “${list[0]}”.`;
  return `Showing images whose caption mentions ALL of: ${list.map((t) => `“${t}”`).join(' + ')}.`;
}
