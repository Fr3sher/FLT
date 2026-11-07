// Shared host interaction and presentation contract, version 1.5.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0.

export function normalizeSemanticEngine(value) {
  const raw = typeof value === 'object' && value
    ? (value.semantic_engine ?? value.semantic?.engine ?? value.engine)
    : value
  return raw === 'siglip2' ? 'siglip2' : 'clip'
}

export function semanticEngineLabel(value) {
  return normalizeSemanticEngine(value) === 'siglip2' ? 'SigLIP 2' : 'CLIP'
}


const SPREAD_BANDS = [
  { maxRatio: 0.35, label: 'all about equally close' },
  { maxRatio: 0.80, label: 'the last ones are noticeably looser' },
  { maxRatio: Infinity, label: 'the tail is much weaker than the top' },
]

const FLAT_LIFT_RATIO = 0.05

export function spreadLabel(range, poolMedian) {
  const top = Number(range?.top)
  const bottom = Number(range?.bottom)
  if (!Number.isFinite(top) || !Number.isFinite(bottom) || top <= 0) return ''
  const median = Number(poolMedian)
  if (!Number.isFinite(median)) {
    // No baseline: fall back to the set's own drop, still a pure ratio.
    const drop = (top - bottom) / top
    return (SPREAD_BANDS.find((b) => drop / 0.3 <= b.maxRatio)
      || SPREAD_BANDS[SPREAD_BANDS.length - 1]).label
  }
  const lift = top - median
  if (lift <= 0 || lift / top < FLAT_LIFT_RATIO) {
    return 'barely above what any image here scores — the order is a hint at best'
  }
  const ratio = (top - bottom) / lift
  return (SPREAD_BANDS.find((b) => ratio <= b.maxRatio)
    || SPREAD_BANDS[SPREAD_BANDS.length - 1]).label
}

export function readinessHint(status, engine = 'clip') {
  if (!status) return ''
  const label = status.model_label || semanticEngineLabel(status.engine || engine)
  if (!status.available) {
    return status.reason || 'Text search is unavailable on this install.'
  }
  if (status.weights_warning) return status.weights_warning
  if (status.warm) return `${label} search model is loaded — results are instant.`
  return `First search loads the ${label} search model (about 10 seconds, on the CPU). `
    + 'After that, searches are instant.'
}

export function pendingLabel(status) {
  return status?.warm ? 'Searching…' : 'Loading the search model…'
}

const NEGATION = /(?:,\s*)?\b(?:with\s+no|without|excluding|except|minus|not|no)\s+([^,.;]+)/i

const TAIL = /\s+(?:in|on|at|with|and|or)\b.*$/i

export function suggestPushDown(query) {
  const m = NEGATION.exec(String(query || ''))
  if (!m) return ''
  // The article rides along ("a hat", not "hat"): CLIP barely distinguishes them
  // (cos = 0.986, measured) and keeping it makes the offered chip read like the
  // words the user typed.
  const term = String(m[1] || '').replace(TAIL, '').trim()
  // One to three words: "a hat", "blonde hair", "a red baseball cap". Longer is
  // a clause, not a trait, and a bad guess costs more than no guess.
  if (!term || term.split(/\s+/).length > 3) return ''
  return term.toLowerCase()
}
