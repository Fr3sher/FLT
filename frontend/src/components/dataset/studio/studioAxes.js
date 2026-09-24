/**
 * COMPARISON render axes: CFG, steps and second pass. Single-LoRA Studio and Canvas get these from
 * useStudioForm's dataset payload; multi-LoRA comparison has no single dataset, so these controls
 * and request keys were absent. Choices now arrive in /api/studio/base-models axes; these helpers
 * apply the same selected-or-default rules as other surfaces.
 */

/**
 * Effective launch axis: user selection if present, otherwise the family's single default value. A
 * null default means an empty axis, such as second pass outside SDXL: omit it and retain backend
 * defaults.
 */
export function effectiveAxis(selected, fallback) {
  if (Array.isArray(selected) && selected.length) return selected;
  return fallback == null ? [] : [fallback];
}

/** Grid multiplier from these axes. An empty axis counts as one: it sweeps
 *  nothing and must not reduce the entire count to zero. */
export function axisTotal({ cfgs, steps, steps2 } = {}) {
  const n = (a) => Math.max(1, (Array.isArray(a) ? a.length : 0));
  return n(cfgs) * n(steps) * n(steps2);
}

/**
 * Add request keys only for axes with values. Missing axes leave backend defaults unchanged,
 * preserving behavior for installations that make no selection.
 */
export function axisPayload({ cfgs, steps, steps2 } = {}) {
  const out = {};
  if (Array.isArray(cfgs) && cfgs.length) out.cfgs = [...cfgs];
  if (Array.isArray(steps) && steps.length) out.steps = [...steps];
  if (Array.isArray(steps2) && steps2.length) out.steps2 = [...steps2];
  return out;
}

/**
 * Multi-select toggle always retains at least one value, matching solo Studio's useStudioForm
 * _toggleKeep rule.
 */
export function toggleAxisValue(current, value) {
  const base = Array.isArray(current) ? current : [];
  const next = base.includes(value)
    ? base.filter((v) => v !== value)
    : [...base, value].sort((a, b) => a - b);
  return next.length ? next : base;
}
