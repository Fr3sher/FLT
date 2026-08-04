/* ⚖ LoRA bench — the page's pure logic, kept out of the JSX.
 *
 * PURE JS on purpose (no JSX, no imports): `node --test` can load it directly,
 * so the parts that are easy to get quietly wrong — which strength wins, what
 * the grid is allowed to claim, when we refuse to guess a trigger — are pinned
 * by tests instead of by a screenshot.
 */

/** What a strength sweep on ONE prompt and ONE seed does and does not prove.
 *
 * It is a single sentence and it stays a single sentence: a paragraph under a
 * grid is a paragraph nobody reads. The claim it blocks is the one this whole
 * feature could otherwise manufacture — "the grid looked bad, the LoRA is bad" —
 * when all the grid ever showed was one prompt's behaviour. */
export const SWEEP_CAVEAT =
  'One prompt, one seed: this shows how strength changes the result, not whether '
  + 'the LoRA is good. A LoRA that only fails on this prompt still looks fine here.'

/** Search over the picker: matches the file name, its folder and its family. */
export function filterLoras(loras, query) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return loras || []
  return (loras || []).filter((l) => (
    `${l.name || ''} ${l.filename || ''} ${l.label || ''} ${l.family_label || ''}`
      .toLowerCase().includes(q)
  ))
}

/** [{family, label, folder, loras}] — picker sections, empty families dropped. */
export function groupByFamily(loras, families) {
  return (families || [])
    .map((f) => ({ ...f, loras: (loras || []).filter((l) => l.family === f.family) }))
    .filter((g) => g.loras.length > 0)
}

/** The strengths a run actually rendered, ascending. Read from the CELLS, never
 * from the form: a resumed or partially cancelled run has fewer than requested,
 * and the grid must show what exists. */
export function strengthsOf(run) {
  const seen = []
  for (const c of (run && run.cells) || []) {
    if (typeof c.strength === 'number' && !seen.includes(c.strength)) seen.push(c.strength)
  }
  return seen.sort((a, b) => a - b)
}

export function cellsAt(run, strength) {
  return ((run && run.cells) || []).filter((c) => c.strength === strength)
}

/** The file the DISPLAYED run tested — read off its own cells, never from the
 * picker. Opening an earlier bench of another LoRA leaves the picker on the
 * file you last clicked, and scoring the grid against that one would put the ★
 * on a strength measured for a different LoRA. */
export function runCheckpoint(run) {
  const cell = ((run && run.cells) || []).find((c) => c.checkpoint)
  return cell ? cell.checkpoint : null
}

/** The aggregated score of (file, strength) across every bench run — the scratch
 * dataset holds them all, so `cell_scores` already answers "at what strength
 * does THIS file win", not just "in this run". */
export function scoreAt(scores, checkpoint, strength) {
  return (scores || []).find(
    (s) => s.checkpoint === checkpoint && s.strength === strength) || null
}

/** The winning strength, or null.
 *
 * Null while NOTHING has been voted on: the backend sorts by Wilson lower bound,
 * and an unvoted sweep has every entry at rank 0 — crowning the first one would
 * invent a verdict out of tie-breaking order. */
export function bestStrength(scores, checkpoint) {
  const mine = (scores || []).filter((s) => s.checkpoint === checkpoint)
  if (!mine.some((s) => (s.voted || 0) > 0)) return null
  let best = null
  for (const s of mine) {
    if (!best
      || (s.rank || 0) > (best.rank || 0)
      || ((s.rank || 0) === (best.rank || 0) && (s.voted || 0) > (best.voted || 0))) best = s
  }
  return best ? best.strength : null
}

/** Are the votes behind `bestStrength` thin enough that we must say so? */
export function isLowConfidence(scores, checkpoint) {
  const mine = (scores || []).filter((s) => s.checkpoint === checkpoint)
  return mine.some((s) => (s.voted || 0) > 0) && mine.every((s) => s.low_confidence)
}

/** How the trigger field must be presented, from what the file's header said.
 * `state` ∈ 'metadata' | 'unknown'. Never 'guessed': a guessed trigger is the
 * single cause of a false verdict on a subject LoRA. */
export function triggerNotice(info) {
  if (info && info.source === 'metadata' && (info.trigger || '').trim()) {
    return {
      state: 'metadata',
      text: 'Filled in from the file itself (ss_output_name). That is the name it '
        + 'was trained under — usually, but not always, the word that activates it. '
        + 'Check it against the page you downloaded it from.',
    }
  }
  return {
    state: 'unknown',
    text: 'This file does not say what its activation word is. Copy it from the page '
      + 'you downloaded the LoRA from — without it a subject LoRA renders images it '
      + 'never touched, and the grid reads as a bad LoRA.',
  }
}

/** Can we launch? Returns null when yes, else the reason (shown, not hidden). */
export function launchBlocker({ filename, strengths, trigger, noTrigger, running, gpuBusy }) {
  if (gpuBusy) return gpuBusy
  if (running) return 'A bench run is still going.'
  if (!filename) return 'Pick a LoRA first.'
  if (!(strengths || []).length) return 'Pick at least one strength.'
  if (!(trigger || '').trim() && !noTrigger) {
    return 'Enter the activation word, or tick “this LoRA has no activation word”.'
  }
  return null
}

/** Toggle a strength in the sweep, keeping it sorted and capped. */
export function toggleStrength(list, value, max) {
  const has = (list || []).includes(value)
  if (has) return list.filter((v) => v !== value)
  if ((list || []).length >= (max || 8)) return list
  return [...list, value].sort((a, b) => a - b)
}
