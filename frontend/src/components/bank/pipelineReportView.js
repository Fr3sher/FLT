/* What the Launch-all report is still entitled to claim.

   A report is a photograph of ONE run. The bug that produced this file: a
   Launch-all stopped before ✂ Find crops & variants ran wrote "cancelled before
   it ran", and went on saying it for days — including next to a standalone run
   of that very pass which had just grouped 2358 shots. The banner was not wrong
   about its own run; it was answering a question the user was no longer asking.

   The server marks any step re-run since the report was written
   (`superseded_at`, `superseded_detail`, from the bank's pass journal). Here we
   decide what that means on screen: the step reads as re-run, and a report whose
   every stopped step has been redone stops flying the 🛑. The original verdict is
   never erased — a step nobody re-ran keeps saying exactly what happened to it,
   which is the only reason the banner is worth reading at all. */

export const STATUS_STYLE = {
  done: { icon: '✅', cls: 'text-emerald-300' },
  skipped: { icon: '⏭️', cls: 'text-amber-300' },
  cancelled: { icon: '🛑', cls: 'text-content-subtle' },
  error: { icon: '⚠️', cls: 'text-rose-300' },
}

export function isSuperseded(step) {
  return !!(step && step.superseded_at && step.status !== 'done')
}

/** One row: the icon, the colour, and the sentence after the step name. */
export function stepView(step) {
  if (!step) return null
  if (isSuperseded(step)) {
    return {
      icon: '🔄',
      cls: 'text-content-muted',
      note: step.superseded_detail
        ? `re-run since — ${step.superseded_detail}`
        : 're-run since this report',
      superseded: true,
    }
  }
  const style = STATUS_STYLE[step.status] || STATUS_STYLE.error
  return {
    icon: style.icon,
    cls: style.cls,
    note: step.status === 'done' ? step.detail || '' : step.reason || '',
    superseded: false,
  }
}

/** The banner's headline. `stopped` drives the 🛑: it survives only while a step
    that never ran is still waiting for someone to run it. */
export function reportHeadline(report) {
  const steps = (report && Array.isArray(report.steps)) ? report.steps : []
  const done = steps.filter((s) => s.status === 'done').length
  const redone = steps.filter(isSuperseded).length
  const unfinished = steps.filter((s) => s.status !== 'done' && !isSuperseded(s))
  const stopped = !!(report && report.cancelled) && unfinished.length > 0
  return {
    done, redone, total: steps.length, stopped,
    icon: stopped ? '🛑' : '🚀',
    covered: done + redone,
  }
}
