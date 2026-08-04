/** The grammar of "bake a LoRA into a base", with no React in it.
 *
 * Split out for the same reason `denseModels.js` is: `node --test` can import
 * this and assert the sentences, the row bookkeeping and the guards without a
 * DOM. What is left in the component is markup.
 *
 * The wording here is load-bearing, not decoration. On the model sites a
 * checkpoint made exactly this way is routinely published as a "finetune" — by
 * authors who describe the merge themselves a sentence later. LDS produces the
 * same object and refuses the same vocabulary: what comes out of this is a base
 * with LoRAs folded into it, it is not a model that was trained, and both the
 * screen and the file's own header say so.
 */

export const MERGE_RUNNING_STATES = ['running'];

export const fmtGB = (bytes) => (
  typeof bytes === 'number' && bytes > 0 ? `${(bytes / 1e9).toFixed(1)} GB` : '—'
);

/** "about 4 minutes" — never a false precision on something disk-bound. */
export function fmtDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return '';
  if (value < 90) return 'under a minute';
  const minutes = Math.round(value / 60);
  if (minutes < 60) return `about ${minutes} minute${minutes > 1 ? 's' : ''}`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `about ${hours} h${rest ? ` ${rest} min` : ''}`;
}

export const pct = (done, total) => (
  total > 0 ? Math.min(100, Math.max(0, Math.round((done / total) * 100))) : 0
);

/** A blank LoRA row. 1.0 = the LoRA exactly as it was trained. */
let nextRowId = 0;
export function newLoraRow(path = '', weight = 1) {
  nextRowId += 1;
  return { id: `lora-${nextRowId}`, path, weight };
}

/** Only rows that actually name a file reach the server. */
export function loraPayload(rows) {
  return (rows || [])
    .filter((row) => String(row?.path || '').trim())
    .map((row) => ({ path: String(row.path).trim(), weight: Number(row.weight) }));
}

/** Can we even ask for a plan? Cheap client-side gate — the SERVER owns every
 *  real refusal, so this only stops a request that carries nothing. */
export function canAskPlan(base, rows) {
  return Boolean(String(base || '').trim()) && loraPayload(rows).length > 0;
}

/** The one-line summary of what the merge would write. */
export function planHeadline(plan) {
  if (!plan?.ok) return '';
  const count = plan.loras?.length || 0;
  return `Folds ${count} LoRA${count > 1 ? 's' : ''} into `
    + `${plan.base_name}, and writes ${plan.destination_name} (${fmtGB(plan.output_bytes)}) `
    + `into ${plan.destination_dir}.`;
}

/** Tensors the merge will copy through without understanding them.
 *
 * This exists because one real community Krea 2 checkpoint carries ~75 MB of an
 * image in two tensors named `last.down.weight` / `last.up.weight`, hiding under
 * a legitimate prefix. We do not refuse the merge over them and we do not
 * silently drop somebody's bytes — we carry them and say so, with their names.
 */
export function carriedOverNote(plan) {
  const rows = plan?.carried_over || [];
  if (!rows.length) return '';
  const names = rows.slice(0, 4).map((row) => row.name).join(', ');
  const more = rows.length > 4 ? `, and ${rows.length - 4} more` : '';
  return `${rows.length} tensor${rows.length > 1 ? 's are' : ' is'} not part of the `
    + `${plan.family_label || 'model'} layout (${names}${more}, ${fmtGB(plan.carried_over_bytes)}). `
    + 'They are copied over unchanged — nothing is dropped, but they are not weights we merge into.';
}

/** Said on the screen, and written into the file's own header. */
export const HONESTY_NOTE = 'What this produces is a base with LoRAs folded into its '
  + 'weights — not a model that was trained as a whole. The file records that in its '
  + 'metadata, so it stays true after the file is renamed or re-uploaded.';

/** The reserve we owe anyone reading about the Turbo transplant. */
export const TURBO_NOTE = 'Merging a re-distillation LoRA (the one Krea publishes for '
  + 'Turbo) at 0.8-1.0 into a model trained on Raw is the published route to getting '
  + 'few-step speed back. We have not tested it ourselves, and it is an approximation '
  + 'rather than an identity — expect to compare before you publish.';

/** Merging into an already-quantized file is refused, and this says why. */
export const PRECISION_NOTE = 'Merge into the full-precision (bf16) model, then quantize '
  + 'the result — quantizing first and merging after loses precision twice, and the loss '
  + 'compounds every time.';

/** Weight bounds mirrored from the server, so the field can guide before it refuses. */
export const WEIGHT_MIN = -2;
export const WEIGHT_MAX = 2;

export function weightHint(weight) {
  const value = Number(weight);
  if (!Number.isFinite(value)) return '';
  if (value === 0) return 'A weight of 0 contributes nothing.';
  if (value > 1) return 'Above 1 applies the LoRA harder than it was trained.';
  if (value < 0) return 'A negative weight subtracts the LoRA.';
  return '';
}
