// 🔎 Find scenes — the wording that keeps a SIMILARITY RANKING over shots from
// reading as a filter, kept out of the JSX so `node --test` can exercise it.
//
// The image lane already solved most of this problem and its reasoning is not
// repeated here — it is IMPORTED (see bankTextSearch.js for the measurements
// behind the spread bands, the readiness hints and the negation trap). Two lanes
// with two copies of the same calibrated sentences is how one of them quietly
// stops being true.
//
// WHAT IS GENUINELY DIFFERENT ABOUT VIDEO, and therefore lives here:
//
//  1. A result is a SHOT, and a shot is a span of time. The backend embeds
//     several frames of it and scores it by the best one, so a result carries a
//     SECOND — the moment that actually matched. Showing the shot without the
//     second hands the user a thirty-second clip and tells them the answer is
//     somewhere inside it, which is barely better than not answering.
//  2. That second is ABSOLUTE, in the source file's own timeline, because the
//     player streams the source and addresses it with a media fragment. Treating
//     it as an offset from the shot's start lands the playhead in the wrong shot.
//  3. "Not embedded" is a much more likely state here than in the image lane. A
//     bank of rushes is triaged long before anyone thinks to search it, so the
//     honest default is to explain the pass rather than to return an empty grid.
import {
  spreadLabel, readinessHint, pendingLabel, suggestPushDown,
} from '../bank/bankTextSearch.js'

// Re-exported so the video components have ONE import and cannot accidentally
// grow a second, drifting copy of a sentence that was measured once.
export { spreadLabel, readinessHint, pendingLabel, suggestPushDown }

/** Why a search cannot be run here, or '' when it can.
 *
 * Three different states that a single "unavailable" would flatten into one
 * useless sentence: there is nothing in the bank yet, the shots exist but have
 * no vectors (run the pass), or this install cannot run CLIP at all (nothing in
 * this bank will fix that). Offering the pass in the third case sends the user
 * round a loop — the pass 503s for the same reason the search would.
 */
export function searchUnavailableReason(counts, status) {
  const c = counts || {}
  if (status && status.available === false) {
    return status.reason || 'Searching by words is unavailable on this install.'
  }
  if (!Number(c.clips)) return 'This bank has no shots yet — find the shots first.'
  if (!Number(c.embedded)) {
    return 'Run 🔎 Find scenes first — it looks at a few frames of every shot so '
      + 'a typed word can reach them.'
  }
  return ''
}

/** The one-line summary above the grid, announced to screen readers.
 *
 * Never claims a match: it says "closest", gives the range the ranking spans,
 * and names the shots that could not be searched at all. */
export function summarize(result) {
  if (!result) return ''
  const shown = (result.clip_ids || []).length
  if (!shown) {
    return `No searchable shot to rank for “${result.query}”. ${unsearchableNote(result)}`.trim()
  }
  const r = result.score_range || {}
  const spread = spreadLabel(r, result.pool_median)
  const parts = [
    `${shown} closest shot${shown === 1 ? '' : 's'} of ${result.pool} for `
      + `“${result.query}”, best first.`,
    // Raw cosines, shown as what they are and never as a percentage: on this
    // model even a perfect match tops out around 0.2, so "22%" reads as failure.
    `Similarity ${fmt(r.top)} down to ${fmt(r.bottom)}${spread ? ` — ${spread}` : ''}.`,
    'Search brings the likeliest shots to the front; it does not select them. '
      + 'Every shot scores something against every phrase.',
  ]
  const note = unsearchableNote(result)
  if (note) parts.push(note)
  return parts.join(' ')
}

function fmt(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '—'
}

/** The load-bearing warning. A shot with no vectors cannot be found by ANY
 * phrase — staying silent about it lets the user conclude the scene is not in
 * the bank, which is how a search quietly becomes a lie. */
export function unsearchableNote(result) {
  const missing = Number(result?.unembedded) || 0
  if (missing <= 0) return ''
  return `${missing} shot(s) here have not been looked at yet and could NOT be `
    + 'searched — run 🔎 Find scenes to include them.'
}

/** "1:23.4" — the position a human can find on a scrub bar. One decimal because
 * a shot can be two seconds long and whole seconds would point at a third of it.
 * Minutes are NOT wrapped into hours: this is an offset inside one rush, and
 * "61:11" is easier to scrub to than "1:01:11". */
export function formatTimestamp(seconds) {
  const s = Number(seconds)
  if (seconds == null || !Number.isFinite(s) || s < 0) return '—'
  const m = Math.floor(s / 60)
  const rest = s - m * 60
  return `${m}:${rest < 10 ? '0' : ''}${rest.toFixed(1)}`
}

/** Where in the shot the match was found, in words. '' for a label we do not
 * know — leaking an internal key into the UI is worse than saying nothing. */
export function frameLabelPhrase(label) {
  return {
    start: 'near the start',
    key: 'at its sharpest frame',
    end: 'near the end',
  }[String(label || '')] || ''
}

/** "matched at 0:12.5, near the end" — the second to seek to, plus the reminder
 * that ONE moment of the shot matched, not the whole span. That distinction is
 * the entire reason several frames per shot are embedded, and hiding it would
 * oversell every result. */
export function matchLine(hit) {
  const t = Number(hit?.frame_s)
  if (!hit || !Number.isFinite(t)) return ''
  const where = frameLabelPhrase(hit.frame_label)
  return `matched at ${formatTimestamp(t)}${where ? `, ${where}` : ''}`
}

/** The media fragment that opens the player ON the matched second.
 *
 * The second is ABSOLUTE in the source file, and so is the fragment — the
 * player streams the whole rush and range-requests the span. A matched second
 * outside the shot means the bounds were re-cut after embedding; falling back to
 * the shot's own start is the honest answer, because seeking outside it would
 * show a frame from a neighbouring shot and label it the match. */
export function seekFragment(clip, seconds) {
  return `#t=${round3(playFromSecond(clip, seconds))},${round3(Number(clip?.end_s) || 0)}`
}

/** The second the player should OPEN at for this shot: the matched one when it
 * really falls inside the shot, the shot's own start otherwise. Separate from
 * the fragment because the lightbox builds its own src and needs the number, and
 * one clamp in two places is one clamp too many. */
export function playFromSecond(clip, seconds) {
  const start = Number(clip?.start_s) || 0
  const end = Number(clip?.end_s) || 0
  const t = Number(seconds)
  return (Number.isFinite(t) && t >= start && t <= end) ? t : start
}

function round3(v) {
  return Math.round(Number(v) * 1000) / 1000
}

/** What CLIP genuinely cannot do, shown in the panel rather than buried in a
 * doc: a user who trusts a wrong answer here silently builds a bad dataset.
 * These are measured weaknesses of this exact checkpoint, not a disclaimer.
 *
 * The negation entry is the expensive one. On a photo of a helmeted astronaut,
 * "an astronaut without a helmet" scored HIGHER (0.217) than "an astronaut with
 * a helmet" (0.212): CLIP does not weigh "without", it ignores it. The results
 * come back full and confident carrying exactly what was asked to be gone, with
 * nothing anywhere to reveal it. Hence `-term`, which subtracts instead of
 * speaking. */
export const VIDEO_CLIP_LIMITS = [
  'Negation — “without a hat” returns hats. Type “-hat” instead: it subtracts '
    + 'the unwanted thing from the score rather than saying the word.',
  'Counting — “two people” barely outranks one person; expect “one vs several” '
    + 'at best.',
  'Spatial relations — “to the left of” carries almost no meaning.',
  'Sound and motion — only frames are looked at, so “a door slamming” or '
    + '“panning left” describe nothing it can see.',
]

export function limitsSentence() {
  return 'Best at subjects, settings, styles and framing, in the frames it '
    + 'looked at. It cannot count, cannot hear, and ignores “without” — so '
    + 'describe what IS on screen, and type “-word” for what should be pushed '
    + 'down.'
}
