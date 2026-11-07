// react-frontend/src/components/dataset/studio/resultKeys.js
/**
 * Studio results KEYS define launches, variants and cells. Pure helpers are extracted from JSX for
 * node --test, like flipOrder and stackResults, because wrong keys silently hide images.
 * Previously run_seed | prompt split one N-prompt launch into N pseudo-runs and showed only one.
 * Tests enforce two rules: run_id identifies a launch, never prompt; prompt DOES identify variants
 * and cells alongside aspect/CFG/steps so batch images do not collapse into unlabeled cells. Both
 * cell indexing and ResultCell row/column/variant lookup use cellKey, preventing axes from being
 * added to one side only.
 */

/**
 * Key part: null and undefined become empty strings, matching the old manually written ?? ''
 * behavior.
 */
const part = (v) => (v == null ? '' : String(v));

/**
 * Build keys with JSON rather than joining with |: prompts are FREE TEXT and may contain
 * delimiters, which would otherwise cause distinct prompts to share a cell.
 */
const join = (parts) => JSON.stringify(parts.map(part));

/**
 * LAUNCH identity is the opaque run_id placed on every cell by the backend invocation, covering
 * all prompts, models and seeds. Older cells without this column preserve the exact legacy key:
 * run_seed ?? seed plus prompt. Prompt remains necessary there because separate launches with a
 * PINNED seed share run_seed. Old runs render as before; new ones no longer split apart.
 */
export function runKey(cell) {
  const runId = cell?.run_id;
  if (runId) return `id:${runId}`;
  const runSeed = cell?.run_seed ?? cell?.seed;
  return `seed:${join([runSeed, cell?.prompt])}`;
}

/**
 * VARIANT identity defines one grid using render axes INCLUDING prompt. Each prompt receives its
 * own table, like each aspect and CFG value.
 */
export function variantKey(cell) {
  return join([cell?.z_model, cell?.aspect, cell?.cfg, cell?.steps, cell?.steps2, cell?.prompt]);
}

/* Grid-consumed variant descriptor: key and axis values. */
export function variantOf(cell) {
  return {
    key: variantKey(cell),
    zModel: cell?.z_model || '',
    zModelLabel: cell?.z_model_label || '',
    aspect: cell?.aspect || '',
    cfg: cell?.cfg,
    steps: cell?.steps,
    steps2: cell?.steps2,
    prompt: cell?.prompt || '',
  };
}

/**
 * CELL identity is checkpoint x strength x variant. Both index cellKey(cell) and ResultCell lookup
 * cellKey({checkpoint, strength, ...variant}) use this function and therefore produce the same
 * string.
 */
export function cellKey(cell) {
  return join([cell?.checkpoint, cell?.strength,
               cell?.z_model, cell?.aspect, cell?.cfg, cell?.steps, cell?.steps2, cell?.prompt]);
}

/* ResultCell lookup key from its row, column and variant. */
export function cellKeyFor(checkpoint, strength, variant) {
  return cellKey({
    checkpoint,
    strength,
    z_model: variant?.zModel,
    aspect: variant?.aspect,
    cfg: variant?.cfg,
    steps: variant?.steps,
    steps2: variant?.steps2,
    prompt: variant?.prompt,
  });
}

/**
 * Shorten a prompt to a label. Test prompts often span hundreds of characters, but grid captions
 * must fit one line even at 400 px. Keep full text in title.
 */
export function promptLabel(prompt, max = 48) {
  const text = String(prompt ?? '').trim().replace(/\s+/g, ' ');
  if (text.length <= max) return text;
  return `${text.slice(0, max - 1).trimEnd()}…`;
}

/**
 * Count DISTINCT batch prompts to decide whether labels are needed. A single-prompt run would
 * repeat the same caption on every table.
 */
export function distinctPrompts(cells) {
  return new Set((cells || []).map((c) => c?.prompt || '')).size;
}
