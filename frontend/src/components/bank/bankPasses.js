/* WHAT EACH BANK PASS IS, told in the three blocks its launch window shows.
 *
 * WHY THREE BLOCKS AND NOT ONE "SETTINGS" PANEL. A window called "settings for
 * this pass" would be a lie, and it was measured: of the 12 knobs in 🎚 Filter
 * thresholds, the 🔎 Scan quality pass reads exactly ONE (dup_distance) — its
 * measuring code (services/image_quality.py) does not even import the config.
 * The other eleven decide how the GRID IS SORTED AND FLAGGED, and they re-sort on
 * save without any pass running. Mixing the two in one window would teach people
 * that nudging a slider costs a rescan, which is the opposite of true.
 *
 * So every window says three separate things:
 *   THIS RUN                 — where it runs and how big that is (the scope).
 *   SETTINGS THIS PASS READS — only what the CALCULATION consumes, and where
 *                              those values live (they are global — the same for
 *                              every bank — unless said otherwise).
 *   NOT DECIDED HERE         — what is re-read when the grid is sorted or
 *                              flagged, retunable with no pass at all.
 *
 * AND A FOURTH THING WHEN IT IS TRUE: `caveats`, for what the scope does NOT
 * cover. 🔎 Scan's duplicate re-grouping always covers the whole bank whatever
 * the scope; 🎨 Medium also runs chained inside ✨ Score with the default scope.
 * Both are stated rather than left for someone to discover.
 *
 * SCOPES THAT WOULD LIE ARE OFFERED DISABLED, WITH THE REASON. ✨ Score, 👥 Group
 * by person and ✂ Find crops & variants each produce a PARTITION of the whole
 * bank, renumbered on every run: handed a subset they would number a
 * sub-population from 1 and drop those ids on top of unrelated groups already in
 * the database. A wrong group is worse than a missing option — but a missing
 * option is worse than a disabled one, because the maintainer concluded a shipped
 * feature did not exist twice over from exactly that kind of silence.
 *
 * Plain .js (no JSX) so `node --test` can execute all of it.
 */
import { PASS_SCOPE_OPTIONS } from './bankPassScope.js';

/* The reason a whole-bank pass refuses a scope. One sentence, said the same way
   everywhere, because it is the same fact three times. */
const PARTITION_REASON = (what) =>
  `${what} is one numbering of the WHOLE bank, recomputed from scratch on every `
  + 'run. A pass handed part of the bank would number that part from 1 and land '
  + 'those ids on top of unrelated groups already saved — so this pass covers '
  + 'everything, always.';

/**
 * The passes, keyed by the id used in `payload.pass_scopes` and in the tests.
 *
 * `scopes: true`  — every option in PASS_SCOPE_OPTIONS is offered.
 * `scopes: string`— none are: the string is the reason, shown next to the one
 *                   immutable THIS RUN line.
 * `selection`     — true, or the reason it is refused.
 * `redo`          — the "run it again on rows that already have a result" line,
 *                   which is where "Rescan all" went: it was never an action of
 *                   its own, it was a SCOPE wearing a button's clothes.
 * `countable`     — false when no honest number exists (see ✂ below).
 */
export const BANK_PASSES = {
  scan: {
    id: 'scan',
    label: '🔎 Scan quality',
    verb: '🔎 Scan',
    endpoint: 'scan',
    what: 'Measures sharpness, noise, flatness, size and effective detail, hashes '
      + 'every image, then groups the exact duplicates. CPU only.',
    scopes: true,
    selection: true,
    redo: {
      key: 'rescan',
      label: 'Also re-measure images that were already scanned',
      note: 'This is where “Rescan all” went. It was never a second pass — it was '
        + 'this scope, with a button of its own.',
    },
    settings: [
      { name: 'Duplicate distance (🎚 Filter thresholds ▸ dup_distance)',
        note: 'The only stored setting this pass reads, and it is read by the '
          + 'duplicate GROUPING at the end, not by the measuring.' },
    ],
    notHere: [
      'Sharpness / noise / flat / small / detail thresholds — those decide which '
        + 'measured images get FLAGGED and how the grid sorts. Change them and the '
        + 'grid re-sorts on save; no rescan is needed.',
    ],
    caveats: [
      'The scope chooses what is MEASURED. The duplicate grouping at the end of '
        + 'the pass always covers the whole bank, because it works from the stored '
        + 'hashes and renumbers all of them together.',
    ],
    binCost: 'a rejected image is re-read from disk and re-measured',
  },

  score: {
    id: 'score',
    label: '✨ Score',
    verb: '✨ Score',
    endpoint: 'score',
    what: 'Rates every image for aesthetics (1–10), flags NSFW and groups the bank '
      + 'by visual style — one CLIP pass, resumed from its cache.',
    scopes: PARTITION_REASON('The style grouping'),
    selection: PARTITION_REASON('The style grouping'),
    fixedScopeLine: 'The whole bank except the bin — every kept and undecided image.',
    redo: {
      key: 'rescore',
      label: 'Throw the cached embeddings away and recompute everything',
      note: 'For a new model, or scores you no longer trust. Costs a full pass; '
        + 'without it the run resumes and skips what is already computed.',
    },
    settings: [
      { name: 'Style threshold (🎚 Filter thresholds ▸ style_threshold)',
        note: 'Decides how tight the style groups are.' },
      { name: 'Bank scoring models folder + Python (Setup ▸ Quality tools)' },
      { name: 'Scoring device (CPU / GPU, resolved from this machine)',
        note: 'On the GPU the pass takes the exclusive window: ComfyUI is unloaded '
          + 'and training cannot start for its duration.' },
    ],
    notHere: [
      'Aesthetic minimum and NSFW maximum — they only decide which scored images '
        + 'get flagged and how the grid sorts. Retunable with no pass at all.',
    ],
    caveats: [],
  },

  faces: {
    id: 'faces',
    label: '👥 Group by person',
    verb: '👥 Group',
    endpoint: 'faces',
    what: 'Embeds the dominant face of every image and clusters the bank by person '
      + '— no reference photo needed.',
    scopes: PARTITION_REASON('A person clustering'),
    selection: PARTITION_REASON('A person clustering'),
    fixedScopeLine: 'The whole bank except the bin, minus the folders you declared '
      + 'to be a single person (those are skipped — that is what the declaration '
      + 'is for).',
    redo: null,
    settings: [
      { name: 'Face threshold (🎚 Filter thresholds ▸ face_threshold)',
        note: 'How sure the detector must be before a face counts.' },
      { name: 'Face scoring models folder, Python and device (Setup ▸ Quality tools)' },
    ],
    notHere: [
      'Which folders count as “one person” — that is 👤 Single person here, on the '
        + 'subfolder panel, and it takes effect without a pass.',
    ],
    caveats: [],
  },

  angles: {
    id: 'angles',
    label: '⤢ Measure head angles',
    verb: '⤢ Measure',
    endpoint: 'angles',
    what: 'Re-runs the face detector on images that were face-scanned by a build '
      + 'that computed the head angle and threw it away. Writes the angle and '
      + 'nothing else.',
    scopes: true,
    selection: true,
    redo: null,
    settings: [
      { name: 'Face scoring models folder, Python and device (Setup ▸ Quality tools)' },
      { name: 'Time estimate — NOT configurable',
        note: 'The ~2 s per image the estimate uses is a measured constant in the '
          + 'code, not a setting.' },
    ],
    notHere: [
      'The ⤢ angle filter buckets (front / three-quarter / profile) read the '
        + 'measured value; they need no re-measure.',
    ],
    caveats: [
      'This lane has always reached the bin — its pool never filtered on status at '
        + 'all. Leaving the scope alone keeps that exactly; picking one narrows it '
        + 'for the first time.',
    ],
    binCost: 'the face detector runs again on each rejected image',
  },

  watermark: {
    id: 'watermark',
    label: '🚩 Find watermarks',
    verb: '🚩 Scan',
    endpoint: 'watermark',
    what: 'Looks for overlaid watermarks and logos, and locates them so the '
      + 'cleaning levels below can crop or repaint them.',
    scopes: true,
    selection: true,
    redo: {
      key: 'rescan',
      label: 'Also re-check images that were already scanned',
      note: 'Images you dismissed as “not watermarked” are never re-examined, '
        + 'whichever line you pick — that is why the two numbers here are not the '
        + 'pile size.',
    },
    settings: [],   // filled at render time: the ROUTE decides (see below)
    notHere: [
      'Which watermarked images get rejected, and the ✂ crop / 🖌 repaint levels — '
        + 'those are their own actions on the watermark panel.',
    ],
    caveats: [],
    binCost: 'each rejected image is put through the detector',
  },

  framing: {
    id: 'framing',
    label: '📐 Classify framing',
    verb: '📐 Classify',
    endpoint: 'framing',
    what: 'Tags each shot face / bust / body / back with the vision model, feeding '
      + 'the 📐 filter chips and the coverage advice.',
    scopes: true,
    selection: true,
    redo: {
      key: 'rescan',
      label: 'Also re-classify images that already have a framing',
    },
    settings: [
      { name: 'Vision model + Ollama URL (Settings ▸ Local tools)' },
      { name: 'Vision concurrency (Settings ▸ Local tools)' },
      { name: 'The prompt — NOT configurable',
        note: 'It is the same fixed classifier prompt the datasets use.' },
    ],
    notHere: [
      'The coverage advice and the framing target — they read the stored framing '
        + 'and recompute on the spot.',
    ],
    caveats: [],
    binCost: 'each rejected image costs one vision-model call',
  },

  medium: {
    id: 'medium',
    label: '🎨 Classify medium',
    verb: '🎨 Classify',
    endpoint: 'medium',
    what: 'Sorts scored images into photograph / anime / 3D render / illustration '
      + '— or an honest “unsure” — by reading the embeddings ✨ Score already '
      + 'cached. No image is looked at again and the GPU stays free.',
    scopes: true,
    selection: true,
    redo: {
      key: 'rescan',
      label: 'Also re-classify images that already have a verdict',
    },
    settings: [
      { name: 'The decision margins — NOT configurable',
        note: 'They are fixed constants in the code (0.005 for photographs, 0.030 '
          + 'for the rest). An empty block here would read as “we did not look”.' },
      { name: 'CLIP text encoder (its phrase cache is written once per install)' },
    ],
    notHere: [
      'The 🎨 medium chips re-read the stored verdict and its margin, so a borderline '
        + 'call can be reconsidered without running this again.',
    ],
    caveats: [
      '✨ Score runs this pass automatically when it finishes, always with the '
        + 'default scope — a scope picked here belongs to this run only and is '
        + 'stored nowhere.',
    ],
    binFree: true,
  },

  semantic_dedup: {
    id: 'semantic_dedup',
    label: '✂ Find crops & variants',
    verb: '✂ Find crops & variants',
    endpoint: 'semantic-dedup',
    what: 'Groups crops and re-compressed variants of the SAME shot that the exact '
      + 'hash misses, from the ✨ Score embeddings. No GPU.',
    scopes: PARTITION_REASON('The “same shot” grouping'),
    selection: PARTITION_REASON('The “same shot” grouping'),
    fixedScopeLine: 'Every image ✨ Score has an embedding for — rejected ones '
      + 'included. That pool lives in the score cache, so this window cannot put a '
      + 'number on it without inventing one.',
    countable: false,
    redo: null,
    settings: [
      { name: 'Same-shot threshold (🎚 Filter thresholds ▸ semantic_dup_threshold)',
        note: 'Overridable for one run from the 🎚 panel.' },
      { name: 'Style threshold (🎚 Filter thresholds ▸ style_threshold)',
        note: 'Not a threshold here — it decides how the comparison is BLOCKED. '
          + 'Set looser than the same-shot threshold and the pass falls back to '
          + 'comparing everything against everything.' },
    ],
    notHere: [
      'How a group is resolved (keep best / keep first) — that is the ✂ Same shot '
        + 'chip’s own action.',
    ],
    caveats: [],
  },

  caption: {
    id: 'caption',
    label: '🏷️ Caption',
    verb: '🏷️ Caption',
    endpoint: 'caption',
    what: 'Describes each image so it becomes searchable, and the description rides '
      + 'along when you promote it to a dataset.',
    scopes: true,
    selection: true,
    // Caption's "redo" is 🔄 Re-caption: a destructive second launch with its own
    // confirmation and its own two figures, so it is NOT a tick box here.
    redo: null,
    settings: [
      { name: 'Captioning engine (Settings ▸ Captioning & quality)',
        note: 'Overridden for this run by the Engine picker below.' },
      { name: 'Vision model + Ollama URL (Settings ▸ Local tools)',
        note: 'Overridden for this run by the Model picker below.' },
      { name: 'Vision concurrency (Settings ▸ Local tools)' },
    ],
    notHere: [
      'The 🔍 search and the 🏷️ tag chips read the captions that exist; they never '
        + 'ask for a pass.',
    ],
    caveats: [],
    binCost: 'each rejected image costs a full captioning call, the slowest of them all',
  },
};

/** Every pass id, in the order the panel lists its buttons. */
export const BANK_PASS_ORDER = ['scan', 'faces', 'score', 'medium', 'framing',
  'semantic_dedup', 'watermark', 'angles', 'caption'];

export function bankPass(passId) {
  return BANK_PASSES[passId] || null;
}

/**
 * Is this scope available for this pass, and why not?
 * @returns {{ok: boolean, reason: string}}
 *
 * NEVER returns "absent". An option a pass cannot honour is rendered disabled
 * with this reason next to it — the whole point of the disabled state is that the
 * user can see the capability was considered and read the objection, instead of
 * concluding the feature does not exist.
 */
export function passScopeAvailability(passId, scopeId) {
  const spec = bankPass(passId);
  if (!spec) return { ok: false, reason: 'Unknown pass.' };
  if (spec.scopes === true) return { ok: true, reason: '' };
  return { ok: false, reason: String(spec.scopes) };
}

/** Can a selection drive this pass, and why not? */
export function passSelectionAvailability(passId) {
  const spec = bankPass(passId);
  if (!spec) return { ok: false, reason: 'Unknown pass.' };
  if (spec.selection === true) return { ok: true, reason: '' };
  return { ok: false, reason: String(spec.selection) };
}

/** The scope lines a dialog draws: every option, each with its availability. */
export function passScopeRows(passId) {
  return PASS_SCOPE_OPTIONS.map((o) => ({
    ...o, ...passScopeAvailability(passId, o.id),
  }));
}

/** Which watermark route will actually run, and the settings IT reads.
 *
 *  The pass picks between two engines at launch, and the settings are not the
 *  same for both — so the window names the one that is going to run rather than
 *  listing both and letting the user guess which half applies. */
export function watermarkSettings(detectorReady) {
  if (detectorReady) {
    return {
      route: 'The dedicated watermark detector (SigLIP2) — installed, so this is '
        + 'the route this run will take. ~0.14 s per image.',
      settings: [
        { name: 'Detector threshold (Settings ▸ Captioning & quality ▸ watermark_detect)' },
        { name: 'Detector models folder, Python and device (Setup ▸ Quality tools)' },
      ],
    };
  }
  return {
    route: 'The vision model (Ollama) — the detector extra is not installed, so '
      + 'this run falls back to the route that has always worked. ~1.7 s per image.',
    settings: [
      { name: 'Vision model + Ollama URL (Settings ▸ Local tools)' },
      { name: 'Vision concurrency (Settings ▸ Local tools)' },
      { name: 'The prompt — NOT configurable' },
    ],
  };
}
