/* 🖥️ The Klein tuning dials of the generation panel — the pure half.

   `klein.generation_steps` was a Settings-only field while the Krea panel
   carried its own steps slider inches away on the same screen: the value that
   decides how long every Klein shot renders for was the one you had to leave the
   page to change. It is a SETTING, not a per-run argument (it changes every shot
   of the batch identically), so this panel both shows and edits it — the same
   contract, and the same warning, the Krea dials already state on screen.

   JSX-free so `node --test` can exercise the rules without a browser. */

// The range the backend accepts (config.DEFAULTS klein.generation_steps, 1–50).
export const KLEIN_STEPS_MIN = 1;
export const KLEIN_STEPS_MAX = 50;
export const KLEIN_STEPS_STEP = 1;

/* 5 is `klein.generation_steps`'s own shipped value, so a backend too old to
   publish config_defaults still lands where the graph actually runs — the same
   reasoning as clampSteps' 8 on the Krea side. */
export const clampKleinSteps = (v, fallback) => {
  const bound = (x, dflt) => {
    const n = Number(x);
    if (!Number.isFinite(n)) return dflt;
    return Math.min(KLEIN_STEPS_MAX, Math.max(KLEIN_STEPS_MIN, n));
  };
  return Math.round(bound(v, bound(fallback, 5)));
};

/** What the step count costs, in one phrase. A bare number is not a setting:
 *  the only thing this dial actually trades is time, and it trades it
 *  proportionally — 10 steps is twice the wait of 5, per image, every image. */
export function kleinStepsDescription(value) {
  const n = clampKleinSteps(value);
  if (n <= 4) return `${n} · faster than the shipped 5, expect rougher renders`;
  if (n === 5) return `${n} · the shipped default — what every Klein run used before this dial`;
  if (n <= 12) return `${n} · cleaner renders, and ${(n / 5).toFixed(1)}× the wait per image`;
  return `${n} · much longer waits, with little left to gain on this graph`;
}

/** The PUT /api/settings body for one Klein dial. Partial by design: the
 *  endpoint deep-merges, so a slider drag cannot touch the model file, the
 *  consistency LoRA or the preset sitting in the same section. */
export function kleinDialPayload(patch) {
  return { config: { klein: { ...patch } } };
}
