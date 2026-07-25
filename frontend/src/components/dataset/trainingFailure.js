/** What a FAILED local training run should actually show.
 *
 *  The panel used to print the raw tail of training.log in red. ai-toolkit's
 *  first output is normally a harmless `FutureWarning` from huggingface_hub, so
 *  a run that died before writing anything else showed that warning as if it
 *  were the cause — hours lost chasing a deprecation notice (reported by
 *  wannadecryptor on Discord). The backend now sends `excerpt` = the part of the
 *  log that explains the failure, with an explicit `kind`; this helper turns
 *  that into a rendering decision, and it stays a plain module so it can be
 *  tested without a DOM.
 *
 *  Rules:
 *   - a traceback / error line is a CAUSE      -> red, quoted as the reason;
 *   - nothing error-like in the log            -> neutral, said plainly, with a
 *                                                 pointer to the full log. A
 *                                                 warning is never dressed up
 *                                                 as a cause;
 *   - a GPU-architecture verdict, when present -> replaces the generic
 *                                                 "common first-run causes"
 *                                                 guesswork with the real one.
 */

// Both notes point at the 📂 Open run folder button rendered NEXT TO them in
// the failure block. They used to send people to the "📂 Run folder" button
// inside the collapsed "📦 Checkpoints & trained LoRAs" disclosure further
// down — and that button opened the `lora_<trigger>` save_root, one level
// BELOW the folder holding training.log, which a run dead at boot never even
// creates. Naming a button that sits right here keeps the two in sync.
export const NO_ERROR_NOTE =
  'No error line in this log — these are just its last lines. The full '
  + 'training.log is in the run folder (📂 Open run folder).';

export const FULL_LOG_NOTE =
  'The full log is training.log, in the run folder (📂 Open run folder).';

// A run can die before writing anything (a bad interpreter, a missing run.py):
// then there are no "last lines" to point at either.
export const EMPTY_LOG_NOTE =
  'The run wrote nothing to its log before dying — ai-toolkit did not get far '
  + 'enough to say why. Check the Python interpreter and ai-toolkit folder in '
  + 'Settings ▸ Local tools.';

export const GENERIC_CAUSES =
  'Common first-run causes: ai-toolkit’s Python venv is missing packages (re-run '
  + 'its install), or the base model is still downloading / needs a Hugging Face '
  + 'token (gated models like Krea 2, FLUX.1 and FLUX.2 Klein). Fix the cause '
  + 'above, then Train again.';

/** error = the `training_error` payload ({rc, log_tail, excerpt?, gpu_arch?}).
 *  Returns {title, excerpt, tone, note, causes, gpuArch} or null when there is
 *  nothing to show. `tone` is 'error' (this IS the cause) or 'neutral' (context
 *  only) — the caller styles on it. */
export function failureView(error) {
  if (!error) return null;
  const rc = error.rc;
  const title = `The last training run failed${rc != null ? ` (ai-toolkit exited ${rc})` : ''}`
    + ' — nothing is training now.';
  const excerpt = error.excerpt && typeof error.excerpt === 'object' ? error.excerpt : null;
  // A payload without `excerpt` predates this feature (states live up to 1h):
  // fall back to the tail, but keep it neutral rather than re-asserting the old
  // "the last lines are the cause" lie.
  const kind = excerpt ? excerpt.kind : 'legacy';
  const isCause = kind === 'traceback' || kind === 'error';
  const text = (excerpt ? excerpt.text : error.log_tail) || '';
  const gpu = error.gpu_arch && error.gpu_arch.message ? error.gpu_arch : null;
  return {
    title,
    excerpt: text,
    tone: isCause ? 'error' : 'neutral',
    note: !text ? EMPTY_LOG_NOTE : (isCause ? FULL_LOG_NOTE : NO_ERROR_NOTE),
    // The GPU verdict is a REAL cause: it takes the place of the generic list.
    causes: gpu ? '' : GENERIC_CAUSES,
    gpuArch: gpu,
  };
}
