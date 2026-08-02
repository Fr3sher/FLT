// 👁 Visual spread — wording for the one number the labels cannot produce.
//
// Framing chips, person clusters and resolution are LABELS: they cannot tell two
// hundred near-identical shots from two hundred different ones. The CLIP
// embeddings the ✨ Score pass already cached can, and the backend reduces them to
// a single mean pairwise cosine similarity plus a band.
//
// Pure functions, no JSX — `node --test` cannot parse JSX, and the thing worth
// proving is that an UNMEASURED pool never reads as a varied one.
//
// Band ids come from the server payload and are keyed on here: never rename one
// without an alias.

/** Bands, worst first. `null` band means "not measured", which is NOT a verdict. */
const BAND_TEXT = {
  redundant: {
    label: 'Very alike',
    tone: 'warn',
    hint: 'a set this repetitive teaches one look',
  },
  leaning: {
    label: 'Leaning alike',
    tone: 'info',
    hint: 'workable, but more variety would generalise better',
  },
  varied: {
    label: 'Varied',
    tone: 'ok',
    hint: 'the images cover a good range',
  },
}

/** The readout the panel renders, or null when there is nothing honest to show.
 *  Never invents a band: an unscored pool returns the "not measured" shape with
 *  `measured: false`, so the UI cannot accidentally paint it green. */
export function spreadReadout(visual) {
  if (!visual) return null
  const scored = visual.scored || 0
  if (!scored) {
    return {
      measured: false,
      tone: 'info',
      label: 'Not measured',
      detail: 'Run ✨ Score — visual variety is read from the embeddings it caches.',
    }
  }
  if (visual.similarity == null) {
    return {
      measured: false,
      tone: 'info',
      label: 'Not measured',
      detail: `Only ${scored} image${scored === 1 ? '' : 's'} with embeddings — too few to judge how alike they look.`,
    }
  }
  const band = BAND_TEXT[visual.band] || BAND_TEXT.varied
  return {
    measured: true,
    tone: band.tone,
    label: band.label,
    percent: Math.round(100 * visual.similarity),
    // "images with embeddings", not "scored images": the bank's own `scored`
    // counter means "has an aesthetic/NSFW score in the DB", which is a DIFFERENT
    // set — the aesthetic head can fail while the embeddings land fine. Reusing
    // the word would make this line contradict the counter beside it.
    detail: `${Math.round(100 * visual.similarity)}% average similarity across ${scored.toLocaleString()} image${scored === 1 ? '' : 's'} with embeddings — ${band.hint}.`,
  }
}

/** How much of the pool the visual read actually covered, so a partly-scored
 *  bank cannot present a number as if it described everything. */
export function spreadCoverageNote(visual, total) {
  if (!visual || !visual.scored || !total) return ''
  if (visual.scored >= total) return ''
  return `Read from ${visual.scored.toLocaleString()} of ${total.toLocaleString()} images — the rest are not scored yet.`
}
