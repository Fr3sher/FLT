/** 👁️ ComfyUI's console, as the app words it — everything that is not JSX.
 *
 * The server reads ComfyUI's own console buffer (`/internal/logs/raw`), strips
 * it and parses the progress bar into numbers (`comfyui_console.py`). This is
 * the sentence those numbers become on a card, the dock and the banner, kept
 * pure so it can be tested for what it SAYS.
 *
 * Why it exists: a 175-frame clip paged through a full card for hours at
 * `3/4 [1:07:21<1:03:12, 3792.78s/it]`, and nothing in the app could say so —
 * the tile spun the same way for a minute and for a night, the queue called
 * the job "paused", and the launcher had the console window hidden.
 */

/** "45 s" / "12 min" / "1 h 03 min" — the same shape the server's sentence uses. */
export function durationLabel(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds))) return null;
  const total = Math.max(0, Math.round(Number(seconds)));
  if (total < 60) return `${total} s`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} h ${String(rest).padStart(2, '0')} min` : `${hours} h`;
}

/**
 * "step 3/4 · 1 h 03 min per step · about 1 h 03 min left", or null when there
 * is no bar to read. Each piece only when the bar knows it: a bar that has not
 * started says "step 0/4" and nothing about time.
 */
export function progressLabel(progress) {
  if (!progress || !Number.isFinite(Number(progress.total)) || Number(progress.total) <= 0) return null;
  const parts = [`step ${Number(progress.value) || 0}/${Number(progress.total)}`];
  const perStep = durationLabel(progress.seconds_per_step);
  if (perStep && Number(progress.seconds_per_step) > 0) parts.push(`${perStep} per step`);
  const left = durationLabel(progress.remaining_s);
  if (left != null && progress.remaining_s != null) parts.push(`about ${left} left`);
  return parts.join(' · ');
}

/** The last `count` console lines as plain text, oldest first. */
export function consoleLines(console, count = 8) {
  const lines = Array.isArray(console?.lines) ? console.lines : [];
  return lines.slice(-Math.max(1, count)).map((line) => (typeof line === 'string' ? line : line?.m || ''))
    .filter((text) => text.trim().length > 0);
}

/**
 * The bar the listing carries belongs to ONE job — the one on the GPU. A card
 * shows it only for that job; when the server could not name the job, the
 * single running row is the only candidate and gets it.
 */
export function renderForJob(render, jobId) {
  if (!render) return null;
  if (render.job_id == null || jobId == null) return render;
  return String(render.job_id) === String(jobId) ? render : null;
}
