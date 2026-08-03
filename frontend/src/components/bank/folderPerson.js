// 👤 "Single person here" — the wording of a folder-level person assertion.
//
// Pure on purpose (node --test cannot parse JSX): what this feature says is the
// part that has to be provable. Two sentences have to stay honest whatever the
// data does:
//   * an assertion is the USER'S WORD, never a measurement — the panel never
//     phrases it as something the app found out;
//   * a sample check looked at ~15 images, so it may only ever speak about the
//     sample. "sample consistent" is not "this folder is clean", and the copy
//     must not let one be read as the other.

export const SAMPLE_SIZE = 15

/** The assertion covering one subfolder, or null. '' (the bank root) is a real
 *  subfolder here as everywhere else, so the lookup compares against null. */
export function assertionFor(assertions, subfolder) {
  if (subfolder == null || !Array.isArray(assertions)) return null
  return assertions.find((a) => a.subfolder === subfolder) || null
}

export function folderLabel(subfolder) {
  return subfolder === '' ? 'the bank root' : subfolder
}

/** What the assertion IS, in one line. Always attributes it to the user. */
export function assertionSummary(entry) {
  if (!entry) return ''
  const n = entry.images || 0
  return `Person #${entry.cluster_id} · ${n} image${n === 1 ? '' : 's'} grouped by you, `
    + 'with no face pass'
}

/** 'ok' | 'warn' | 'muted' — the tone of a sample verdict. Unknown verdicts read
 *  as muted rather than reassuring: a shape we do not recognise is not good news. */
export function verdictTone(sample) {
  if (!sample) return 'muted'
  if (sample.verdict === 'consistent') return 'ok'
  if (sample.verdict === 'mixed') return 'warn'
  return 'muted'
}

/** The verdict sentence, scoped to the sample it came from. Never states a fact
 *  about the folder — the check only ever saw ~15 of its images. */
export function verdictLine(sample) {
  if (!sample) return null
  const note = sample.note || ''
  if (sample.verdict === 'consistent') return `✓ ${note}`
  if (sample.verdict === 'mixed') return `⚠ ${note}`
  return note ? `· ${note}` : null
}

/** What a sample check will cost, said before it is paid — the whole point of
 *  the feature is the number it is compared against. */
export function checkCostNote(entry) {
  const total = (entry && entry.images) || 0
  if (total <= SAMPLE_SIZE) {
    return `Embeds the ${total} image${total === 1 ? '' : 's'} of this folder.`
  }
  return `Embeds ${SAMPLE_SIZE} images spread across the folder — not the `
    + `${total} a full 👤 Group by person pass would.`
}

/** The "could not read a face here" list. It is a HEADS-UP, never an exclusion:
 *  those images stay in the group, and the sentence has to say so. */
export function toCheckNote(entry) {
  const n = (entry && entry.to_check && entry.to_check.length) || 0
  if (!n) return null
  return `${n} image${n === 1 ? '' : 's'} here showed no usable face `
    + '(no face, too small, or unreadable). Still in the group — worth a look.'
}

export function revokeNote(subfolder) {
  return `${folderLabel(subfolder)} goes back to normal clustering, and the `
    + 'group disappears. Nothing is deleted.'
}
