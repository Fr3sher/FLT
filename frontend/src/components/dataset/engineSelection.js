/* Multi-engine generation: which engines a batch runs on, how the selected
   shots are shared between them, and what that costs.
   PURE JS (no JSX) so node --test can import and exercise it directly.

   WHY THIS FILE EXISTS
   --------------------
   The workspace used to generate with ONE engine, persisted as a plain string
   in localStorage `datasetGenerator`. Users want several at once — either to
   VARY the dataset (each shot goes to one engine) or to COMPARE engines on the
   same shots (every engine renders every shot).

   The storage rule of this repo forbids renaming or re-typing a persisted key:
   `datasetGenerator` remains for the ✎ identity-prompt modal and compatibility
   with profiles that only know one engine. Tile Retry instead reuses each row's
   stored provenance, never this workspace preference. The string key is KEPT,
   unchanged, as a mirror of the PRIMARY engine, and the list lives in a new key
   next to it. A profile that only ever knew the old key reads back as a
   one-engine selection — i.e. exactly today's behaviour. */

/* The engine facts — order, the API/local split, labels, accents, rates — come
   from ONE catalog (src/engines/catalog.js), read AT CALL TIME: a plugin's
   engines join it when the plugin loads, and a list copied at import would
   never see them. Its readers are re-exported here so every importer of this
   module keeps one import site. */
import {
  apiEngineIds, defaultEngineId, engineAccent, engineIds, engineLabel, engineLabels,
  engineRate, localEngineIds,
} from '../../engines/catalog.js';

export { apiEngineIds, engineAccent, engineIds, engineLabel, engineLabels, engineRate, localEngineIds };

export const STORAGE_ENGINES = 'datasetGenerators';     // JSON list (new)
export const STORAGE_PRIMARY = 'datasetGenerator';      // legacy string mirror — NEVER renamed
export const STORAGE_MODE = 'datasetGeneratorMode';     // 'split' | 'all'

/** The engine a profile with no stored preference generates with — the historic
 *  useState default of the workspace, read from the catalog (the first API
 *  engine, else the first engine there is). */
export function defaultEngine() { return defaultEngineId(); }
export const MODES = ['split', 'all'];
/** Sharing the N selected shots between the engines (total = N, today's cost)
 *  is the default: nobody should multiply their bill without asking. */
const DEFAULT_MODE = 'split';

/** Keep only real engine ids, de-duplicated, in canonical order. Anything else
 *  (a typo, a removed engine, a non-string) is dropped rather than trusted. */
export function canonicalEngines(list) {
  const wanted = new Set(Array.isArray(list)
    ? list.filter((e) => typeof e === 'string').map((e) => e.toLowerCase())
    : []);
  return engineIds().filter((e) => wanted.has(e));
}

/** The ids a stored list holds that the catalog does NOT know right now.
 *  They are a plugin's whose plugin is off (a typo of long ago at worst): not
 *  the user's choice to drop, so a write keeps them and a read skips them.
 *  Measured before this rule (refutation, 2026-09-05): opening the workspace
 *  with the plugin off rewrote a selection made of its engines as `[]`, and
 *  switching the plugin back on restored nothing. */
function storedUnknownEngines(storage) {
  let raw = null;
  try { raw = storage?.getItem(STORAGE_ENGINES) ?? null; } catch { raw = null; }
  if (raw == null) return [];
  let parsed;
  try { parsed = JSON.parse(raw); } catch { return []; }
  if (!Array.isArray(parsed)) return [];
  const known = new Set(engineIds());
  const out = [];
  for (const e of parsed) {
    if (typeof e !== 'string') continue;
    const id = e.toLowerCase();
    if (!known.has(id) && !out.includes(id)) out.push(id);
  }
  return out;
}

/** The stored selection, with the legacy single-string key as fallback.
 *  Order of trust: the list key → the legacy string → the historic default.
 *  An EMPTY stored list is a real state (the user unchecked everything) and is
 *  returned as such; only a missing/unusable key falls through. A list whose
 *  every engine is unknown right now (its plugin is off) is NOT that state: the
 *  user picked something, so the default engine stands in until the plugin is
 *  back — and the stored ids stay stored (writeEngines). */
export function readEngines(storage) {
  let raw = null;
  try { raw = storage?.getItem(STORAGE_ENGINES) ?? null; } catch { raw = null; }
  if (raw != null) {
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const known = canonicalEngines(parsed);
        if (known.length || !parsed.length) return known;
        const fallback = defaultEngine();
        return fallback ? [fallback] : [];
      }
    } catch { /* corrupt JSON: fall through to the legacy key */ }
  }
  let legacy = null;
  try { legacy = storage?.getItem(STORAGE_PRIMARY) ?? null; } catch { legacy = null; }
  const fromLegacy = canonicalEngines([legacy]);
  if (fromLegacy.length) return fromLegacy;
  const fallback = defaultEngine();
  return fallback ? [fallback] : [];
}

/** Persist the selection AND refresh the legacy mirror, so the ✎ modal and
 *  older single-engine profiles keep seeing a valid engine. Tile Retry reads
 *  its engine from the image row, not this mirror. The mirror is left untouched
 *  when nothing is selected: an empty selection generates nothing, while
 *  blanking the legacy preference would lose compatibility state.
 *  The ids the catalog does not know right now ride along untouched (see
 *  storedUnknownEngines): a plugin switched back on finds them where they were.
 *  Returns the KNOWN selection, which is what the screen offers. */
export function writeEngines(storage, engines) {
  const list = canonicalEngines(engines);
  try {
    storage?.setItem(STORAGE_ENGINES, JSON.stringify([...list, ...storedUnknownEngines(storage)]));
    if (list.length) storage?.setItem(STORAGE_PRIMARY, list[0]);
  } catch { /* private browsing / full storage: the in-memory state still works */ }
  return list;
}

export function readMode(storage) {
  let raw = null;
  try { raw = storage?.getItem(STORAGE_MODE); } catch { raw = null; }
  return MODES.includes(raw) ? raw : DEFAULT_MODE;
}

export function writeMode(storage, mode) {
  const value = MODES.includes(mode) ? mode : DEFAULT_MODE;
  try { storage?.setItem(STORAGE_MODE, value); } catch { /* ignore */ }
  return value;
}

/** The one engine single-engine consumers should use: first in canonical order.
 *  null when nothing is selected (callers keep their own fallback). */
export function primaryEngine(engines) {
  return canonicalEngines(engines)[0] || null;
}

/** Share `variations` between `engines`.
 *  - 'all'   : every engine renders EVERY shot (comparison — total = N × engines)
 *  - 'split' : round-robin, every shot goes to exactly ONE engine (variety —
 *              total = N, unchanged cost). 25 shots over 3 engines → 9/8/8.
 *  Returns [{ generator, variations }] in canonical order, with empty entries
 *  dropped (more engines than shots in split mode). One engine → a single entry
 *  holding all the shots, i.e. strictly the pre-existing behaviour. */
export function distributeVariations(variations, engines, mode) {
  const shots = Array.isArray(variations) ? variations : [];
  const list = canonicalEngines(engines);
  if (!list.length || !shots.length) return [];
  if (mode === 'all') return list.map((generator) => ({ generator, variations: [...shots] }));
  const buckets = list.map((generator) => ({ generator, variations: [] }));
  shots.forEach((shot, i) => { buckets[i % list.length].variations.push(shot); });
  return buckets.filter((b) => b.variations.length);
}

/** Dispatch order for the server: API engines first, the LOCAL ones LAST.
 *  The API batches are background threads that start returning images right
 *  away; a local engine holds the single GPU and runs its shots in series, so
 *  putting it first would make the whole batch look frozen. Local engines keep
 *  their canonical order between themselves (a stable sort). */
export function engineBatches(variations, engines, mode) {
  const batches = distributeVariations(variations, engines, mode);
  const localIds = localEngineIds();
  const local = (g) => (localIds.includes(g) ? 1 : 0);
  return [...batches].sort((a, b) => local(a.generator) - local(b.generator));
}

/** True when the run mixes a local GPU engine with at least one API engine —
 *  the case where the local shots visibly queue behind the API ones. */
export function localQueuesBehindApi(engines) {
  const list = canonicalEngines(engines);
  const local = localEngineIds();
  const api = apiEngineIds();
  return list.some((e) => local.includes(e))
    && list.some((e) => api.includes(e));
}

/** Every selected engine renders locally — the condition 🔞 shots need (the
 *  server refuses NSFW on API engines, so a mixed run would fail as a whole).
 *  False on an empty selection: nothing selected renders nothing. */
export function localOnly(engines) {
  const list = canonicalEngines(engines);
  const local = localEngineIds();
  return list.length > 0 && list.every((e) => local.includes(e));
}

/** Back-compat alias — `kleinQueuesBehindApi` was the only name for this and is
 *  imported elsewhere; it now answers for BOTH local engines. */
export const kleinQueuesBehindApi = localQueuesBehindApi;

/** How many images the batch will produce: shots × multiplier, per engine. */
export function totalImages(shotCount, engines, mode, multiplier = 1) {
  const n = Math.max(0, Number(shotCount) || 0);
  const mult = Math.max(1, Number(multiplier) || 1);
  const list = canonicalEngines(engines);
  if (!list.length || !n) return 0;
  return (mode === 'all' ? n * list.length : n) * mult;
}

/** Dollar estimate for the batch. A local engine contributes 0 (its rate), and
 *  so does any engine named in `free` — the catalog's freeEngines() for this
 *  run: a lane that spends a subscription's quota, not dollars. In split mode
 *  each engine only pays for ITS share — which is why the split is computed
 *  here rather than averaged. */
export function estimateCost(shotCount, engines, mode, { multiplier = 1, free = [] } = {}) {
  const n = Math.max(0, Number(shotCount) || 0);
  const mult = Math.max(1, Number(multiplier) || 1);
  const list = canonicalEngines(engines);
  if (!list.length || !n) return 0;
  const rate = (engine) => (free.includes(engine) ? 0 : engineRate(engine));
  if (mode === 'all') return list.reduce((sum, e) => sum + n * mult * rate(e), 0);
  // split: round-robin share, same arithmetic as distributeVariations.
  return list.reduce((sum, e, i) => {
    const share = Math.floor(n / list.length) + (i < n % list.length ? 1 : 0);
    return sum + share * mult * rate(e);
  }, 0);
}

/** The engines that actually BILL for this run — names the guard-rail confirm
 *  ("this will cost $X on …") without listing free lanes. */
export function billingEngines(engines, { free = [] } = {}) {
  return canonicalEngines(engines).filter(
    (e) => engineRate(e) > 0 && !free.includes(e));
}

/** Why Generate is unavailable, or null when it can run. The empty selection is
 *  a real, reachable state (every card unchecked), and it must SAY so instead of
 *  queueing an empty batch. `maxFanout` mirrors the server cap; it is read from
 *  /api/capabilities, never hardcoded here, and 0/undefined disables the check
 *  (the server stays the authority and refuses with its own message). */
export function generateBlockedReason({ engines, shotCount, mode, multiplier = 1, maxFanout = 0, maxLocalFanout = 0 }) {
  const list = canonicalEngines(engines);
  if (!list.length) return 'Pick at least one engine above';
  if (!Number(shotCount)) return 'Select at least one shot';
  const total = totalImages(shotCount, list, mode, multiplier);
  const local = localOnly(list) && maxLocalFanout > 0;
  const limit = local ? maxLocalFanout : maxFanout;
  if (limit > 0 && total > limit) {
    if (local) return `${total} images is over the ${limit}-image local queue limit — select fewer shots or raise it in Settings > Local tools > ComfyUI`;
    return `${total} images is over the ${limit}-per-batch limit — `
      + (mode === 'all' ? 'switch to Split, ' : '') + 'uncheck an engine or select fewer shots';
  }
  return null;
}
