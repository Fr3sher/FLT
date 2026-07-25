/** 🗃️ Moving a bank's folder — pure helpers (no JSX, so `node --test` runs them).
 *
 * A bank points at a folder by path, but every image row is stored RELATIVE to
 * it and every analysis (scores, duplicate groups, face verdicts, captions,
 * keep/reject decisions) hangs off the row id. So moving the folder to another
 * disk costs nothing — as long as the bank can be repointed, and as long as the
 * repointing is aimed at the right folder.
 *
 * That last part is the whole job of this file: the backend answers a dry run
 * with `found` / `missing` counts, and the user confirms an actual number
 * rather than a hopeful "Move". Nothing is ever deleted on either side. */

/** Is this preview safe to apply? A folder holding NONE of the bank's files is
 * a different folder, not a moved one — the backend refuses it outright, and
 * the button is disabled before the user can get that far. */
export function canApplyRelocation(preview) {
  if (!preview) return false
  const total = Number(preview.total) || 0
  const found = Number(preview.found) || 0
  return total === 0 || found > 0
}

/** The verdict line under the folder field: what the dry run found, in words
 * that name the numbers. {tone, headline, detail} — tone drives the colour. */
export function relocationSummary(preview) {
  if (!preview) return null
  const total = Number(preview.total) || 0
  const found = Number(preview.found) || 0
  const missing = Number(preview.missing) || 0
  const extra = Number(preview.extra) || 0
  if (total > 0 && found === 0) {
    return {
      tone: 'error',
      headline: `None of this bank's ${total} image(s) are in that folder.`,
      detail: 'That looks like a different folder. Pick the one that CONTAINS '
        + 'the images — usually the folder you moved, not its parent.',
    }
  }
  if (preview.same_folder) {
    return {
      tone: 'warn',
      headline: 'That is the folder this bank already points at.',
      detail: `${found} of ${total} image(s) are there right now.`,
    }
  }
  const extraNote = extra > 0
    ? ` ${extra} extra image(s) in there will be added on the next refresh.` : ''
  if (missing === 0) {
    return {
      tone: 'ok',
      headline: `All ${found} image(s) of this bank are in that folder.`,
      detail: 'Every score, caption and keep/reject decision is kept.'
        + extraNote,
    }
  }
  return {
    tone: 'warn',
    headline: `${found} of ${total} image(s) found — ${missing} are not there.`,
    detail: 'You can still repoint the bank: nothing is deleted, the missing '
      + 'rows keep their analysis and simply read as missing until their files '
      + 'come back.' + extraNote,
  }
}

/** Label for the apply button — the count is the point, so it is IN the label
 * (a user who reads "Repoint to 29 759 image(s)" cannot mis-click into a
 * folder that only matched 12). */
export function relocationApplyLabel(preview) {
  if (!preview) return 'Repoint this bank'
  // 'en-US' explicitly: the UI is English everywhere, and the runtime locale
  // would otherwise group thousands differently from the rest of the app.
  const found = Number(preview.found) || 0
  return `Repoint this bank to ${found.toLocaleString('en-US')} image(s)`
}

/** Toast text once it landed. */
export function relocationDoneText(result) {
  const found = Number(result?.found) || 0
  const missing = Number(result?.missing) || 0
  const tail = missing > 0
    ? ` ${missing} file(s) are still not on disk — their rows were kept.` : ''
  return `Bank repointed — ${found} image(s) found at the new folder, every `
    + `analysis kept.${tail}`
}
