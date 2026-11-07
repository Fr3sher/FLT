/** Optional generation-LoRA PRESETS (Idea by @waltm — Discord feature request).
 *
 * The user defines named combinations in Settings — each preset is an ORDERED
 * list of {file, strength} rows (list order = chain order after the
 * consistency LoRA on the local Klein edit graph; files are loras-relative
 * names the user points, never hardcoded). Per run the workspace just PICKS a
 * preset — it opens on klein.default_generation_lora_preset ("None" until one
 * is set), and picking something else there applies to that run only, without
 * rewriting the setting. No per-LoRA toggles, no automatic gating: the chosen
 * preset carries the intent. The request only ever sends the preset NAME; the
 * backend resolves files/strengths/order from config (fail-closed, unknown
 * names degrade to no extra LoRAs).
 */

export const LORA_STRENGTH_MAX = 1.5;

/** Hard caps — mirror the backend's klein_edit_helper.MAX_GENERATION_LORAS /
 *  MAX_GENERATION_LORA_PRESETS (shown in the Settings card). */
export const MAX_GENERATION_LORAS = 8;
export const MAX_GENERATION_LORA_PRESETS = 12;

/** Clamp a slider/user value into the [0, 1.5] strength range the backend
 *  enforces too (NaN and negatives collapse to 0). */
export function clampLoraStrength(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.min(LORA_STRENGTH_MAX, n);
}

/** Sanitize a config-shaped preset list (from /api/settings or a Settings
 *  edit): drop blank/duplicate names and blank/malformed rows, normalize
 *  strengths (junk -> 0.6), cap rows per preset and the preset count. Order
 *  is preserved everywhere — row order IS the chain order. */
export function sanitizeGenerationLoraPresets(list) {
  const out = [];
  const seen = new Set();
  for (const preset of Array.isArray(list) ? list : []) {
    if (!preset || typeof preset !== 'object') continue;
    const name = typeof preset.name === 'string' ? preset.name.trim() : '';
    if (!name || seen.has(name)) continue;
    const rows = [];
    for (const row of Array.isArray(preset.loras) ? preset.loras : []) {
      if (!row || typeof row !== 'object') continue;
      const file = typeof row.file === 'string' ? row.file.trim() : '';
      if (!file) continue;
      const n = Number(row.strength);
      rows.push({
        file,
        strength: Number.isFinite(n) ? Math.min(LORA_STRENGTH_MAX, Math.max(0, n)) : 0.6,
      });
      if (rows.length >= MAX_GENERATION_LORAS) break;
    }
    seen.add(name);
    out.push({ name, loras: rows });
    if (out.length >= MAX_GENERATION_LORA_PRESETS) break;
  }
  return out;
}

/** Which preset the run panel STARTS on, from `klein.default_generation_lora_preset`.
 *
 *  The panel used to open on "None" on every visit, so a configured preset only
 *  ever applied when the user remembered to re-pick it — and a run that forgot
 *  showed no LoRA anywhere in its PNG metadata, which reads as the app ignoring
 *  its own settings. This is a STARTING POINT, never a lock: the picker still
 *  offers None and every other preset for that run, and the choice made there is
 *  not written back to the setting.
 *
 *  Fail-closed, like every other step of the preset chain: a name matching no
 *  configured preset (renamed, deleted, typed by hand into config.json) resolves
 *  to '' — "no preset" — rather than blocking or guessing a neighbour. */
export function resolveDefaultPresetName(defaultName, presets = []) {
  const name = typeof defaultName === 'string' ? defaultName.trim() : '';
  if (!name) return '';
  return sanitizeGenerationLoraPresets(presets).some((p) => p.name === name) ? name : '';
}

/** Body fragment for /generate (and /regenerate): the picked preset's NAME as
 *  { generation_lora_preset: name } — the backend resolves the chain from its
 *  own config (fail-closed). Empty fragment ({}) when:
 *   - the engine is not Klein (API engines never see these knobs);
 *   - no preset is picked (the "None" default);
 *   - the picked name matches no configured preset, or the preset has no rows
 *    (nothing would chain — don't send a dead name). */
export function generationLoraPresetPayload({ isKlein = false, presetName = '', presets = [] } = {}) {
  if (!isKlein) return {};
  const name = typeof presetName === 'string' ? presetName.trim() : '';
  if (!name) return {};
  const preset = sanitizeGenerationLoraPresets(presets).find((p) => p.name === name);
  if (!preset || preset.loras.length === 0) return {};
  return { generation_lora_preset: name };
}

/** The preset row that names a LoRA the engine ALREADY loads — predicted in the
 *  editor, where the row is written, instead of only in the server log.
 *
 *  Both local engines pin one LoRA outside the presets: Klein chains
 *  `klein.consistency_lora` at `klein.consistency_strength`, Krea loads
 *  `krea.identity_lora` at `krea.identity_lora_strength`. A preset row naming
 *  that same file is DROPPED by the backend on purpose — chaining the identical
 *  LoRA twice sums both strengths into one delta well past what the file was
 *  trained for (measured as visible macro-blocking; reported by @waltm on
 *  Discord). See klein_edit_helper.build_workflow and
 *  krea_edit_helper._existing_generation_lora_rows.
 *
 *  Until now that drop happened in silence: nothing on screen, one warning line
 *  in the server log. A user who had written exactly one preset row, and had
 *  written the consistency LoRA into it, got a run with no extra LoRA at all and
 *  no reason why — which reads as "the app ignores my settings".
 *
 *  This module exists so the FRONT PREDICTS EXACTLY WHAT THE BACK WILL DO.
 *  The backend compares `os.path.normcase(os.path.normpath(a)) ==
 *  os.path.normcase(os.path.normpath(b))`, so a '/' instead of a '\\', a
 *  doubled separator, a './' segment or a difference of case must NOT dodge the
 *  warning — otherwise the editor says "fine" about a row the server discards.
 *
 *  Case: the comparison here is always case-insensitive, while `normcase` is a
 *  no-op on a POSIX server. That is deliberate and it does not over-promise: on
 *  a case-sensitive filesystem a case-different spelling names a file that is
 *  not on disk, and the row is dropped anyway ("not found under any loras root
 *  — skipped"). The row is ignored either way; only the log's reason differs,
 *  which is why the warning says the row is ignored rather than naming a
 *  mechanism it cannot know.
 *
 *  What it deliberately does NOT claim: an ABSOLUTE path aliasing the same file
 *  (Klein resolves preset rows through resolve_model_ref before comparing, so
 *  the server can catch a case the front cannot). Missing a warning is a much
 *  smaller failure than inventing one.
 */

/** Mirror of `os.path.normcase(os.path.normpath(value))` for the model
 *  references these fields hold (relative loader names, occasionally an absolute
 *  path). Separators unify to '/', '.' segments vanish, '..' pops the previous
 *  segment, repeated separators collapse, a trailing separator is dropped, and
 *  the result is lowercased. Junk input yields ''. */
export function normalizeLoraRef(value) {
  const raw = typeof value === 'string' ? value.trim() : '';
  if (!raw) return '';
  const unified = raw.replace(/\\/g, '/');
  // Keep a leading '/' (or a drive prefix) so an absolute path never compares
  // equal to the relative name of the same tail.
  const rooted = /^(\/|[A-Za-z]:\/)/.test(unified);
  const prefix = rooted ? (unified.match(/^(\/|[A-Za-z]:\/)/)[0]) : '';
  const out = [];
  for (const part of unified.slice(prefix.length).split('/')) {
    if (!part || part === '.') continue;
    if (part === '..') {
      // Popping past the root is meaningless; python's normpath keeps the
      // leading '..' on a relative path and swallows it on an absolute one.
      if (out.length && out[out.length - 1] !== '..') out.pop();
      else if (!rooted) out.push('..');
      continue;
    }
    out.push(part);
  }
  const joined = prefix + out.join('/');
  return (joined || (rooted ? prefix : '.')).toLowerCase();
}

/** True when `rowFile` names the same file as `fixedLora` — i.e. the backend
 *  will drop this preset row. Blank on either side is never a match. */
export function isFixedLoraDuplicate(rowFile, fixedLora) {
  const a = normalizeLoraRef(rowFile);
  const b = normalizeLoraRef(fixedLora);
  return !!a && !!b && a === b;
}

/** The sentence shown on the offending row. Engine-specific because the two
 *  fixed slots have different names and different strength settings, and a
 *  warning that cannot name the setting to change is a dead end. */
const FIXED_LORA_SLOTS = {
  klein: {
    label: 'consistency LoRA',
    strengthSetting: 'Consistency strength',
  },
  krea: {
    label: 'identity edit LoRA',
    strengthSetting: 'Identity LoRA strength',
  },
};

export function fixedLoraDuplicateWarning(engine) {
  const slot = FIXED_LORA_SLOTS[engine];
  if (!slot) return '';
  return `Ignored: this is the ${slot.label} the engine already loads. `
    + `It is applied once at its own ${slot.strengthSetting}, and chaining it a `
    + 'second time here would add both strengths together — past what the file '
    + 'was trained for (blocky, posterized output). Point this row at a different '
    + `file, or change the ${slot.strengthSetting} instead.`;
}
