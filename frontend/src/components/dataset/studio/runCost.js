/**
 * Estimate launch cost BEFORE clicking. An earlier 24-prompt cap rejected a real 33-prompt request
 * despite no technical limit: bodies were kilobytes under 64 MB, prompt storage is TEXT, queues
 * have no maximum depth, and result views do not truncate. Capping one of six axes accepted 24
 * prompts across eight checkpoints yet rejected 25 across one despite far less work. TOTAL passes
 * and elapsed time matter. Use the backend's measured seconds_per_image median and warn without
 * capping, matching the project rule: serial execution, with count and duration shown before
 * launch. Prompt batches follow that same rule.
 */

/** Fallback when the machine lacks sufficient history: the old UI-wide constant.
 *  It remains an approximation, not a measurement; measured distinguishes them. */
export const DEFAULT_SECONDS_PER_IMAGE = 12;

/**
 * Ask confirmation above this estimated DURATION, not an image count: time has the same meaning on
 * a 4090 and a GPU five times slower. Measured pace makes slower machines ask sooner,
 * intentionally. An hour of GPU time merits confirmation; below it, inform without interrupting.
 */
export const CONFIRM_ABOVE_SECONDS = 3600;

/* Format seconds as a human-readable duration. */
export function durationLabel(seconds) {
  const s = Math.max(0, Math.round(Number(seconds) || 0));
  if (s < 60) return `${s} s`;
  const minutes = Math.round(s / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${String(rest).padStart(2, '0')}` : `${hours} h`;
}

/**
 * Cost of cells generations. secondsPerImage is the backend's measured median, or null/zero when
 * history is insufficient. Then use the default and mark measured accordingly so the UI never
 * calls an assumed constant the user's current pace.
 */
export function runCost(cells, secondsPerImage) {
  const measured = Number(secondsPerImage) > 0;
  const per = measured ? Number(secondsPerImage) : DEFAULT_SECONDS_PER_IMAGE;
  const n = Math.max(0, Math.floor(Number(cells) || 0));
  const seconds = n * per;
  return {
    cells: n,
    secondsPerImage: per,
    measured,
    seconds,
    label: durationLabel(seconds),
    // heavy never forbids launch: it colors one line and asks ONE question.
    heavy: seconds > CONFIRM_ABOVE_SECONDS,
  };
}

/* Long-launch message states the cost without scolding; it is the user's machine. */
export function heavyRunNotice(cost) {
  return `${cost.cells} generations, about ${cost.label}`
    + (cost.measured ? ' at your current pace' : '')
    + '. The queue is serial — you can stop it at any time and keep what is done.';
}

/**
 * Ask only once before launch and only above the threshold. A three-prompt batch should not
 * require a dialog.
 */
export function heavyRunConfirm(cost) {
  return `This run will queue ${cost.cells} generations — about ${cost.label}`
    + (cost.measured ? ' at your current pace' : '')
    + '.\n\nThe queue is serial: you can stop it at any time, and the images already '
    + 'generated are kept.\n\nStart it?';
}
