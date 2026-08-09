/* 📐 The ONE output-size dial of the Generate-variations panel — the pure half.

   Klein and Krea used to size their shots by unrelated rules: Klein rescaled the
   reference to a hardcoded 2 MP and kept its shape, Krea asked for the card's
   shape but never spent more pixels than the reference itself held. A single
   dataset therefore mixed 2 MP tiles with 0.84 MP ones, in different shapes,
   with nothing on screen explaining either number.

   This dial replaces both rules with one budget, spent by BOTH local engines on
   the CARD's ratio. It is therefore not an engine setting and does not belong in
   either engine's tuning block — it sits above the shot cards, where what it
   governs is what you are looking at.

   JSX-free so `node --test` can exercise the rules without a browser, following
   kleinDials.js / kreaDials.js. */

// The range the backend accepts (config DEFAULTS variations.output_megapixels,
// clamped by services/output_geometry.variation_output_megapixels).
export const VARIATION_MP_MIN = 0.5;
export const VARIATION_MP_MAX = 2.0;
export const VARIATION_MP_STEP = 0.1;

/* 2.0 is BOTH the ceiling and the shipped default: it is where the Flux edit
   models start to drift, and it is the value Klein's workflow always hardcoded —
   so a backend too old to publish config_defaults still lands on the behaviour
   every install already had. */
export const clampVariationMegapixels = (v, fallback) => {
  const bound = (x, dflt) => {
    // `Number(null)` is 0, not NaN: without this an absent key would clamp to
    // the MINIMUM instead of falling back, i.e. a backend that never published
    // the setting would silently render everything at 0.5 MP.
    if (x === null || x === undefined || x === '') return dflt;
    const n = Number(x);
    if (!Number.isFinite(n)) return dflt;
    return Math.min(VARIATION_MP_MAX, Math.max(VARIATION_MP_MIN, n));
  };
  // Snapped to the slider's own step: a config holding 1.234567 must not be
  // announced to the tenth of a pixel it will never be rendered at.
  return Math.round(bound(v, bound(fallback, VARIATION_MP_MAX)) * 10) / 10;
};

/* Python's round() is half-to-even; the backend canvas is computed with it, and
   this function exists precisely to state the backend's answer. */
const roundHalfEven = (x) => {
  const floor = Math.floor(x);
  const diff = x - floor;
  if (diff !== 0.5) return Math.round(x);
  return floor % 2 === 0 ? floor : floor + 1;
};

const LATENT_MULTIPLE = 16;

/** The exact canvas the backend renders a card at — the JS twin of
 *  output_geometry._requested_canvas. Duplicated on purpose and pinned by
 *  contract tests on BOTH sides (see tests/variation-output-size-contract.test.mjs
 *  and backend/tests/test_variation_output_size.py): the panel promises a pixel
 *  size, and a promise the renderer does not keep is worse than no number. */
export function variationCanvas(megapixels, ratioText) {
  const [aw, ah] = String(ratioText).split(':').map(Number);
  const ratio = aw / ah;
  const budget = clampVariationMegapixels(megapixels) * 1_000_000;
  const cells = Math.max(1, Math.floor(budget / (LATENT_MULTIPLE ** 2)));
  const heightCells = Math.max(1, Math.floor(Math.sqrt(cells / ratio)));
  let wc = Math.max(1, roundHalfEven(ratio * heightCells));
  let hc = heightCells;
  while (wc * hc > cells) {
    if (wc / hc > ratio) wc = Math.max(1, wc - 1);
    else hc = Math.max(1, hc - 1);
  }
  return [wc * LATENT_MULTIPLE, hc * LATENT_MULTIPLE];
}

/** What the budget buys, in one phrase. The megapixel count means nothing on its
 *  own — the portrait card is the shape most of a dataset is made of, so its
 *  pixel size is what actually answers "how big will my images be". */
export function variationSizeDescription(value) {
  const mp = clampVariationMegapixels(value);
  const [w, h] = variationCanvas(mp, '3:4');
  const size = `${mp.toFixed(1)} MP · ${w} × ${h} on a portrait shot`;
  if (mp >= VARIATION_MP_MAX) {
    return `${size} — the default, and the most these edit models hold together at`;
  }
  if (mp <= 0.8) return `${size} — quick and light on VRAM, visibly softer for training`;
  return `${size} — smaller files and a shorter wait than the 2.0 default`;
}

/** The PUT /api/settings body for the dial. Partial by design: the endpoint
 *  deep-merges, so a slider drag cannot touch anything in klein/krea. */
export function variationOutputSizePayload(patch) {
  return { config: { variations: { ...patch } } };
}
