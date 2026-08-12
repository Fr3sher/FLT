/* "Have I already run this?"

   Until the bank started journalling its passes (ImageBank.last_passes), the only
   way to answer was to run it again and watch — which on a big bank meant minutes
   of work to be told nothing had changed. The window that launches a pass now says
   what the last run found, and when.

   It deliberately does NOT claim the result is still current. Deciding that means
   comparing the signature of everything the pass reads, which is a full-table read
   this payload is polled far too often to afford. The pass itself does that check
   the moment it starts — for free, once — and reports "already up to date" instead
   of redoing the work. So this line informs the decision; the run still owns the
   verdict. */

export function relativeWhen(ts, now = Date.now()) {
  if (!ts) return ''
  const seconds = Math.max(0, (now - ts * 1000) / 1000)
  if (seconds < 90) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

/** {when, summary} for the pass, or null when it has never run on this bank. */
export function lastPassNote(payload, passId, now = Date.now()) {
  const run = payload?.last_passes?.[passId]
  if (!run || !run.at) return null
  const groups = (run.counts || {}).semantic_groups
  return {
    when: relativeWhen(run.at, now),
    summary: typeof groups === 'number'
      ? `${groups} group(s) of the same shot`
      : (run.detail || ''),
  }
}

/** The sentence shown in the launch window. */
export function lastPassSentence(note) {
  if (!note) return ''
  const found = note.summary ? `, found ${note.summary}` : ''
  return `Already run ${note.when}${found}. `
    + 'If nothing has changed since, this run says so instead of redoing it.'
}
