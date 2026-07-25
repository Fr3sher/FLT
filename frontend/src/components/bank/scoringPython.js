/* "Use a GPU Python you already have" — the decidable half, JSX-free so
 * `node --test` can import it.
 *
 * ✨ Score ships CPU-only PyTorch on purpose, and on a machine with a card that
 * costs hours. The fix is NOT to download a 2.5 GB CUDA wheel from inside the
 * app (wrong wheel index = a broken environment, and it is a big download for
 * people who may not need it). It is to reuse an interpreter this machine has
 * already proven — the one ComfyUI runs on, the one that trains LoRAs.
 *
 * The whole value is in being specific. "ai-toolkit: no" is useless; "ai-toolkit
 * has CUDA but is missing OpenCLIP, here is the command" is actionable. So every
 * row carries a per-dependency verdict and the backend refuses anything it could
 * not prove — a wrong pick would surface as an import error an hour into a pass.
 */

/** Best first: a ready GPU interpreter, then a working CPU one, then the ones
 *  that need something, then the ones that did not answer. Ties keep the
 *  backend's order (the interpreter in use first, the app's own last). */
const RANK = { gpu_ready: 0, cpu_only: 1, incomplete: 2, unreachable: 3 }

export function sortInterpreters(rows) {
  return [...(rows || [])].sort(
    (a, b) => (RANK[a.status] ?? 9) - (RANK[b.status] ?? 9))
}

/** Badge wording + tone per status. 'ok' green, 'warn' amber, 'off' muted. */
export function statusBadge(status) {
  switch (status) {
    case 'gpu_ready': return { tone: 'ok', label: 'GPU ready' }
    case 'cpu_only': return { tone: 'warn', label: 'CPU only' }
    case 'incomplete': return { tone: 'warn', label: 'Missing packages' }
    default: return { tone: 'off', label: 'No answer' }
  }
}

/** The one interpreter worth suggesting: a GPU-ready one that isn't already the
 *  selected one. null when there is nothing better than what is in use. */
export function bestUpgrade(rows) {
  return (sortInterpreters(rows).find((r) => r.status === 'gpu_ready' && !r.selected)) || null
}

/** Can the user pick this row? Only interpreters proven able to run the whole
 *  pass — the backend enforces the same rule; this just greys the button. */
export function canSelect(row) {
  return Boolean(row && row.usable && !row.selected)
}

/** The names of what's missing, for a sentence like "missing OpenCLIP, timm". */
export function missingLabels(row) {
  return (row?.deps || []).filter((d) => !d.present).map((d) => d.label)
}

/** One honest line under the dialog title, from the whole detection result.
 *  Never promises: when nothing GPU-capable was found it says so plainly rather
 *  than inviting the user to keep hunting. */
export function detectionSummary(rows) {
  const list = rows || []
  if (!list.length) return 'No Python interpreters found to check yet.'
  const ready = list.filter((r) => r.status === 'gpu_ready')
  if (ready.length) {
    return `${ready.length} of ${list.length} can run ✨ Score on your GPU.`
  }
  const close = list.filter((r) => r.status === 'incomplete' && r.cuda)
  if (close.length) {
    const names = close.map((r) => `${r.label} (${missingLabels(r).join(', ')})`)
    return `None is ready yet. Reaches the GPU but needs packages: ${names.join('; ')}.`
  }
  return 'None of these can reach the GPU — ✨ Score stays on the CPU.'
}

/** What the Score panel says about the current interpreter, once one has been
 *  chosen explicitly. null when the app default is in use (the CPU note already
 *  covers that case, and saying it twice is noise). */
export function selectionNote(result) {
  const rows = result?.interpreters || []
  const current = rows.find((r) => r.selected)
  if (!current) return null
  return `✨ Score runs in ${current.label} — ${current.detail}`
}
