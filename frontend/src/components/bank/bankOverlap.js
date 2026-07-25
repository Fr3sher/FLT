/* 🗃 Banks that share files — the DECIDABLE part, kept free of JSX so
 * `node --test` can run it.
 *
 * Nothing stops two banks pointing at nested folders, and while you are only
 * triaging that is harmless: statuses live on the bank, not on the file. It
 * stops being harmless at 🗑 Delete rejected, the one action that removes the
 * FILES — the other bank simply finds them gone. These helpers turn the backend
 * facts into the sentences that have to be said BEFORE that click.
 */

/** Where a delete run's files end up, in the user's words. Mirrors the backend's
 *  preference order (OS trash → the app's own trash → a permanent unlink). */
export function deleteDestination(mode) {
  if (mode === 'trash') return 'your system Recycle Bin'
  if (mode === 'app_trash') return "the app's Trash (Settings ▸ Storage)"
  return 'nowhere — they are deleted for good'
}

/** true when the files can still be brought back after the run. */
export function isRecoverable(mode) {
  return mode === 'trash' || mode === 'app_trash'
}

/** The one-line notice for a bank created over a folder another bank already
 *  covers — or null when there is nothing to say. */
export function overlapNotice(overlaps) {
  const list = (overlaps || []).filter((o) => o && o.name)
  if (!list.length) return null
  const names = list.map((o) => `“${o.name}”`).join(', ')
  return `Heads up: this folder overlaps ${names}. Both banks list the same files, `
    + 'so 🗑 Delete rejected in one removes them from the other too.'
}

/** The blocking warning inside the delete confirmation: which OTHER banks lose
 *  files, and how many. null when this bank is on its own. */
export function sharedFilesWarning(preview) {
  const shared = (preview?.shared || []).filter((s) => s && s.files > 0)
  if (!shared.length) return null
  const parts = shared.map((s) => `${s.files} of them are also in “${s.name}”`)
  return `${parts.join('; ')}. Deleting them here removes them from that bank too `
    + '— its own decisions on those images are lost with the files.'
}

/** Total files another bank would lose, across every overlapping bank. Used to
 *  decide how loud the confirmation has to be. */
export function sharedFileCount(preview) {
  return (preview?.shared || []).reduce((n, s) => n + (Number(s?.files) || 0), 0)
}
