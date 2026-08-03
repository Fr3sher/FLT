import {
  SAMPLE_SIZE, assertionSummary, checkCostNote, folderLabel, revokeNote,
  toCheckNote, verdictLine, verdictTone,
} from './folderPerson'

/** 👤 "Single person here" — the folder-level person assertion, shown right under
 *  the Subfolder selector because that is where the user already IS when they
 *  think it: they picked the folder, they know whose it is.
 *
 *  What it offers, in order of what it costs:
 *   • Single person here — free. Groups the whole folder immediately and tells
 *     the face pass to skip it. That skip is the saving.
 *   • Check a sample — ~15 embeddings. Says what the SAMPLE showed and nothing
 *     more; the assertion stands whatever it finds (the user's folder, the
 *     user's call), which is why the warning is a line and not a dialog.
 *   • Revoke — free. The group dissolves, the folder goes back to clustering.
 *
 *  Wording lives in folderPerson.js so it can be tested without a DOM. */
export default function SubfolderPersonPanel({
  subfolder, entry, busy, onAssert, onRevoke, onCheck,
}) {
  if (subfolder == null) return null
  const sample = entry && entry.sample
  const tone = verdictTone(sample)
  const verdict = verdictLine(sample)
  const heads = toCheckNote(entry)
  const toneClass = tone === 'ok'
    ? 'text-emerald-300'
    : tone === 'warn' ? 'text-amber-300' : 'text-content-subtle'

  if (!entry) {
    return (
      <div className="flex flex-wrap items-center gap-2 text-xs text-content-subtle">
        <button type="button" onClick={onAssert} disabled={busy}
          title={`Group every image of ${folderLabel(subfolder)} as one person, `
            + 'with no face pass. Undoable at any time.'}
          className="rounded-md border border-border px-2 py-1 font-semibold text-content hover:bg-white/10 disabled:opacity-50">
          👤 Single person here
        </button>
        <span>
          Already one person’s folder? Say so — the 👤 Group by person pass then
          skips it instead of paying an embedding per image to find out.
        </span>
      </div>
    )
  }

  return (
    <div className="space-y-1.5 rounded-md border border-sky-400/40 bg-sky-500/10 px-2.5 py-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="font-semibold text-sky-200">👤 Single person here</span>
        <span className="text-content-subtle">{assertionSummary(entry)}</span>
      </div>
      {verdict && <p className={toneClass}>{verdict}</p>}
      {heads && <p className="text-content-subtle">⚠ {heads}</p>}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={onCheck} disabled={busy}
          title={checkCostNote(entry)}
          className="rounded border border-border px-2 py-0.5 font-semibold text-content hover:bg-white/10 disabled:opacity-50">
          🔍 {sample ? 'Check the sample again' : `Check a sample (${SAMPLE_SIZE} images)`}
        </button>
        <button type="button" onClick={onRevoke} disabled={busy}
          title={revokeNote(subfolder)}
          className="rounded border border-border px-2 py-0.5 text-content-subtle hover:bg-white/10 disabled:opacity-50">
          ↩ Not one person after all
        </button>
      </div>
    </div>
  )
}
