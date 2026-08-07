/* Krea 2 Edit's two hidden dials — `krea.ref_boost` and
   `krea.identity_lora_strength` — made adjustable from the screen where they
   are actually judged. PURE JS (no JSX) so `node --test` can exercise it, the
   same split as kreaEngine.js.

   WHY THESE TWO WERE UNREACHABLE
   ------------------------------
   Both are real config keys the graph reads on every Krea run
   (krea_edit_helper._ref_boost / _identity_strength), both are clamped
   server-side, and NEITHER had an input anywhere in the app. So the only way to
   move them was to hand-edit config.json — which meant that when likeness came
   out too weak, the one lever that fixes it was the one nobody could touch.
   `grounding_px` and `ref_boost` used to ship as a matched pair (v1 = 1024/4.0,
   v2 = 512/1.0); raise the first alone and you land on a combination no shipped
   profile ever calibrated, with no way to bring the second along.

   SCOPE: these write the GLOBAL setting, exactly like the Settings page does.
   There is no per-run copy — see the panel comment in VariationCatalog.jsx for
   why a second truth would be worse than a wide one.

   The SERVER stays the authority: it re-clamps every value it is sent. The
   bounds here only stop the UI from offering a number that would be silently
   corrected. */

// Mirrors krea_edit_helper._ref_boost's clamp: _clamp(..., 0.0, 10.0, 0.25).
export const KREA_REF_BOOST_MIN = 0;
export const KREA_REF_BOOST_MAX = 10;
export const KREA_REF_BOOST_STEP = 0.25;

// Mirrors krea_edit_helper._identity_strength's clamp: _clamp(..., 0.0, 1.5, 1.0).
export const KREA_IDENTITY_STRENGTH_MIN = 0;
export const KREA_IDENTITY_STRENGTH_MAX = 1.5;
export const KREA_IDENTITY_STRENGTH_STEP = 0.05;

/** A finite number inside [min, max], or `fallback` when the value is unusable.
 *  null/undefined/'' are ABSENT, not zero — `Number(null)` is 0, and a dial
 *  still waiting for /api/settings must not render as "off". */
export function clampDial(value, min, max, fallback) {
  if (value === null || value === undefined || value === '') return fallback;
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, n));
}

/** Slider values arrive as strings and float steps produce 0.30000000000000004.
 *  Two decimals is finer than either step, so this never loses a stop. */
const round2 = (n) => Math.round(n * 100) / 100;

/* `fallback` is the SERVER's config_defaults value when we have it. The literal
   here is the last resort — it mirrors the fallback the server's own clamp
   applies (_ref_boost / _identity_strength), so a backend too old to send
   config_defaults still lands on the value the graph would have used. */
export const clampRefBoost = (v, fallback) =>
  round2(clampDial(v, KREA_REF_BOOST_MIN, KREA_REF_BOOST_MAX,
    clampDial(fallback, KREA_REF_BOOST_MIN, KREA_REF_BOOST_MAX, 0.25)));

export const clampIdentityStrength = (v, fallback) =>
  round2(clampDial(v, KREA_IDENTITY_STRENGTH_MIN, KREA_IDENTITY_STRENGTH_MAX,
    clampDial(fallback, KREA_IDENTITY_STRENGTH_MIN, KREA_IDENTITY_STRENGTH_MAX, 1.0)));

/** What the reference-pull dial currently means, in one short phrase. A bare
 *  number is not a setting — same reasoning as groundingDescription. */
export function refBoostDescription(value) {
  const n = clampRefBoost(value);
  if (n === 0) return '0 · off — the reference is not pushed back in at all';
  if (n < 0.5) return `${n} · light pull, the prompt and shot card stay in charge`;
  if (n < 2) return `${n} · noticeably stronger likeness`;
  if (n < 5) return `${n} · reference-dominated, it starts copying pose and outfit`;
  return `${n} · the reference wins, expect it to ignore the card`;
}

/** Same for the identity LoRA's weight. */
export function identityStrengthDescription(value) {
  const n = clampIdentityStrength(value);
  if (n === 0) return '0 · identity LoRA off — no face transfer';
  if (n < 1) return `${n} · softened identity, more room for the prompt`;
  if (n === 1) return `${n} · the weight the LoRA was trained for`;
  return `${n} · pushed past its training weight, can look waxy or blocky`;
}

/** The PUT /api/settings body for one dial. Partial by design: the endpoint
 *  deep-merges, so this touches nothing else in the krea section. */
export function kreaDialPayload(patch) {
  return { config: { krea: { ...patch } } };
}

/** Coalescing saver for the sliders.
 *
 *  A drag emits dozens of change events; each one must NOT become a settings
 *  write. Pending values from both dials merge into ONE patch and one request,
 *  so moving both and letting go sends a single PUT carrying both keys.
 *
 *  `save(patch)` is called with the merged `{field: value}` object.
 *  Timer functions are injectable so tests don't have to wait in real time. */
export function createDialSaver(save, {
  delay = 400,
  setTimeoutFn = setTimeout,
  clearTimeoutFn = clearTimeout,
} = {}) {
  let pending = null;
  let timer = null;
  const fire = () => {
    timer = null;
    if (!pending) return;
    const patch = pending;
    pending = null;
    save(patch);
  };
  return {
    schedule(field, value) {
      pending = { ...(pending || {}), [field]: value };
      if (timer !== null) clearTimeoutFn(timer);
      timer = setTimeoutFn(fire, delay);
    },
    /** Send whatever is pending right now (unmount, or an explicit reset). */
    flush() {
      if (timer !== null) { clearTimeoutFn(timer); timer = null; }
      fire();
    },
    cancel() {
      if (timer !== null) { clearTimeoutFn(timer); timer = null; }
      pending = null;
    },
    get pending() { return pending; },
  };
}
