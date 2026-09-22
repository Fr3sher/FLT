/**
 * Prompt batches replay MULTIPLE history entries in one launch. Test Studio and Canvas Generate
 * from the board share RunSetupPanel and its history component, so these four functions centralize
 * count, button wording and POST payload. Batch is a server AXIS, not N launches: another POST
 * would be rejected as already running and GPU execution is serial anyway. Each prompt uses the
 * same checkpoints, settings and seed for comparison. No selected prompts preserves EXACT previous
 * behavior: no prompts key, no multiplier and unchanged label.
 */

/**
 * Read history text in either API shape: strings before a Flask restart, objects afterward, for
 * backward compatibility.
 */
export function promptTexts(recentPrompts) {
  return (recentPrompts || [])
    .map((p) => (typeof p === 'string' ? p : p && p.prompt))
    .filter((p) => typeof p === 'string' && p !== '');
}

/**
 * The actually launchable batch automatically drops prompts deleted from history. Never launch an
 * entry no longer visible on screen.
 */
export function visibleBatch(batch, recentPrompts) {
  const available = promptTexts(recentPrompts);
  return (batch || []).filter((p) => available.includes(p));
}

/**
 * Checked Civitai prompts may not yet be in history. Append them AFTER selected history prompts
 * and deduplicate: a previously replayed Civitai prompt selected from both sources should count as
 * ONE pass. Launch adds it to history normally.
 */
export function mergeBatches(historyPicked, extraPicked) {
  // Deduplicate by the TRIMMED string but return the ORIGINAL. This matches engine _prompt_axis
  // trimming/deduplication, avoiding counts that promise unrendered cells. Returning originals
  // preserves single-source batches byte-for-byte.
  const seen = new Set();
  const out = [];
  for (const p of [...(historyPicked || []), ...(extraPicked || [])]) {
    if (typeof p !== 'string') continue;
    const key = p.trim();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out;
}

/**
 * Launch body carries prompts through the same object as global settings. Both Test Studio and
 * Canvas hooks spread it into POST bodies, reaching both routes without signature changes. Empty
 * batch returns the original object itself, keeping the old body unchanged.
 */
export function launchSettings(genSettings, picked) {
  const list = picked || [];
  return list.length ? { ...(genSettings || {}), prompts: [...list] } : genSettings;
}

/** Button text keeps its surface's action: Run test here, or Deploy 2 checkpoints,
 *  then generate on the board. Add what the batch changes so a nine-image launch
 *  never hides behind a generic launch label. */
export function launchText(baseLabel, picked) {
  const n = (picked || []).length;
  return n > 1 ? `${baseLabel || 'Run test'} · ${n} prompts` : (baseLabel ?? null);
}
