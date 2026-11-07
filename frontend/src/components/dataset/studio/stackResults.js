// react-frontend/src/components/dataset/studio/stackResults.js
/**
 * PURE Blend-stack RESULTS logic, extracted for node --test like loraStack.js handles LAUNCH
 * logic. A stack produces only the leading LoRA column, making ordinary comparison/ranking
 * unhelpful. Users need composition (LoRAs, weights, triggers), side-by-side alternate weights,
 * and the best WEIGHT SET rather than an isolated checkpoint. Backend supplies stack, null for
 * non-stacks, and stack_variants for the SAME composition with current-run variants marked active.
 * Since weight sweeps, one variant is no longer one run: identify it by the PAIR of run and weight
 * vector through variantKey.
 */
// Keep the explicit extension because node --test does not resolve extensionless imports.
import { blendComboLabel } from './loraStack.js';

/* Displayed run's stack composition, or [] when it is not a stack. */
export function stackMembers(data) {
  const members = data?.stack;
  return Array.isArray(members) ? members : [];
}

/* Is the displayed run a stack of at least two LoRAs in one image? */
export function isStackRun(data) {
  return stackMembers(data).length > 1;
}

/**
 * Numeric weight, or NaN if absent. Number(null) is zero; guard missing weights from old runs or
 * truncated cells so unknown is not falsely displayed as 0.00, meaning the LoRA was disabled.
 */
const numWeight = (weight) => (weight == null || weight === '' ? NaN : Number(weight));

/* Display weight with two decimals, or a dash when absent from the backend. */
export function fmtWeight(weight) {
  const n = numWeight(weight);
  return Number.isFinite(n) ? n.toFixed(2) : '—';
}

/**
 * Short variant label is its WEIGHT VECTOR in stack order. LoRAs are identical across columns;
 * weights distinguish them.
 */
export function weightVectorText(weights) {
  return (weights || []).map((w) => fmtWeight(w?.weight)).join(' / ');
}

/**
 * Variant identity WITHIN the list. Since sweeps, one run carries multiple weight combinations;
 * run_id alone would give different columns the same React key.
 */
export function variantKey(v) {
  return `${v?.run_id}:${weightVectorText(v?.weights)}`;
}

/**
 * Readable combination label, such as subject 0.8 x style 0.6. Delegate to the same
 * loraStack.blendComboLabel used before launch, keeping promised and displayed sweep labels
 * consistent.
 */
export function comboLabelText(weights) {
  const list = weights || [];
  return blendComboLabel(
    list.map((w) => ({ lora_label: w?.label || w?.filename || '' })),
    list.map((w) => w?.weight),
  );
}

/**
 * Align variant weights to reference composition and compute deltas against the active variant BY
 * FILENAME, not position. Relaunches may select the same stack in different orders; positional
 * comparison would misrepresent members. Return {filename, label, weight, delta, changed} per
 * member.
 */
export function alignWeights(members, variantWeights, activeWeights = null) {
  const byFile = new Map((variantWeights || []).map((w) => [w?.filename, w]));
  const activeByFile = new Map((activeWeights || []).map((w) => [w?.filename, w]));
  return (members || []).map((m) => {
    const here = numWeight(byFile.get(m?.filename)?.weight);
    const there = activeWeights ? numWeight(activeByFile.get(m?.filename)?.weight) : NaN;
    const comparable = Number.isFinite(here) && Number.isFinite(there);
    // Round to hundredths before comparison. Weights are set in 0.05 increments and stored
    // rounded; a 1e-15 delta is not a real change.
    const delta = comparable ? Math.round((here - there) * 100) / 100 : 0;
    return {
      filename: m?.filename ?? null,
      label: m?.label ?? '',
      weight: Number.isFinite(here) ? here : null,
      delta,
      changed: comparable && delta !== 0,
    };
  });
}

/** Variant summary: generated-image count and net votes. */
export function variantSummary(variant) {
  const cells = variant?.cells || [];
  const likes = variant?.likes ?? cells.filter((c) => c.rating === 1).length;
  const dislikes = variant?.dislikes ?? cells.filter((c) => c.rating === -1).length;
  const done = variant?.done ?? cells.filter((c) => c.status === 'done' && c.filename).length;
  return { likes, dislikes, net: likes - dislikes, done, total: cells.length };
}

/**
 * Restore variant weights to the launch map keyed by dataset_id:checkpoint, using
 * loraStack.stackKey, to replay those weights. Get dataset IDs from COMPOSITION because variants
 * carry only filenames.
 */
export function weightsIntoStackMap(members, variantWeights) {
  const byFile = new Map((variantWeights || []).map((w) => [w?.filename, w]));
  const out = {};
  for (const m of members || []) {
    const w = numWeight(byFile.get(m?.filename)?.weight);
    if (m?.dataset_id != null && m?.filename && Number.isFinite(w)) {
      out[`${m.dataset_id}:${m.filename}`] = w;
    }
  }
  return out;
}

/**
 * Build stack best-setting POST: leading LoRA goes in checkpoint/strength for Canvas pins, Apply
 * and deletion safeguards; other members go in stack. Return null for incomplete composition: hide
 * the button rather than save half a stack.
 */
export function bestStackPayload(members) {
  const list = members || [];
  if (list.length < 2) return null;
  const [head, ...rest] = list;
  // Number(null) is zero: reject an ABSENT weight rather than treating it as zero.
  const incomplete = (m) => m?.dataset_id == null || !m?.filename
    || m?.weight == null || !Number.isFinite(Number(m.weight));
  if (incomplete(head) || rest.some(incomplete)) return null;
  return {
    dataset_id: head.dataset_id,
    checkpoint: head.filename,
    strength: Number(head.weight),
    stack: rest.map((m) => ({
      dataset_id: m.dataset_id,
      lora_filename: m.filename,
      weight: Number(m.weight),
    })),
  };
}
