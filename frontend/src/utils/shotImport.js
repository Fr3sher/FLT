/** Custom shot catalogs, imported from JSON — validation and export.
 *
 *  Idea by ashish.sinha (Discord): rather than typing 30-40 shots by hand, hand
 *  the exported catalog to an LLM, ask for more, import the result. Which means
 *  the input is UNTRUSTED by construction: a model-written file will be
 *  malformed, incomplete, or full of labels that collide with the shipped ones.
 *  The validation IS the feature, so it lives here — a pure module, no JSX, fully
 *  testable under `node --test`.
 *
 *  The load-bearing rule is label uniqueness. `prompt_by_label`,
 *  `aspect_for_label` and `is_nsfw_label` (backend) resolve a STORED label
 *  against the union of every catalog with the label alone — no subject_type
 *  threading. A shot whose label already exists anywhere (including the legacy
 *  French aliases still stored in old rows) would silently hijack that
 *  resolution: wrong prompt on regenerate, wrong aspect ratio, or an innocent
 *  shot flagged NSFW and forced onto the local engine. Hence: never import a
 *  collision, and name the offending label when refusing.
 *
 *  Two-stage on purpose. `parseShotImport` writes NOTHING — it reports what
 *  would land and what it refuses; the UI shows that summary and only then does
 *  `applyShotImport` produce the new list. So a 40-shot file whose 37th entry is
 *  bad can never leave 36 shots half-imported.
 */

export const SHOT_IMPORT_FORMAT = 'lds-shots/1';
/** The stored `FaceDatasetImage.framing` enum — the shipped catalogs use these
 *  same four keys for every subject type, so an imported shot must too. */
export const FRAMINGS = ['face', 'bust', 'body', 'back'];
export const MAX_IMPORT_BYTES = 512 * 1024;
export const MAX_IMPORT_SHOTS = 200;
export const MAX_LABEL_LEN = 80;
/** The backend truncates `variation_prompt` at 500 chars — refusing here is
 *  honest, silently storing a prompt that regenerates differently is not. */
export const MAX_PROMPT_LEN = 500;
/** Fields we understand. Anything else is reported as ignored (never dropped in
 *  silence) — `aspect` especially: the ratio is resolved server-side from the
 *  framing, so an imported `"aspect": "16:9"` would do nothing. */
const KNOWN_FIELDS = new Set(['id', 'label', 'prompt', 'framing', 'nsfw']);
const EXAMPLE_COUNT = 6;

const FRAMING_LIST = FRAMINGS.join(', ');
const key = (label) => String(label).trim().toLocaleLowerCase();
const isText = (v) => typeof v === 'string' && v.trim().length > 0;

const blocked = (code, message) => ({
  blocked: { code, message }, accepted: [], rejected: [], ignoredFields: [], skippedExamples: 0,
});

/**
 * Validate the text of a shot-catalog JSON file. Never throws, never mutates.
 *
 * @param {string} text            raw file contents
 * @param {object} opts
 * @param {string} opts.subjectType   the subject the user is importing INTO
 * @param {string[]} opts.reservedLabels  every built-in label across ALL catalogs,
 *        plus the legacy aliases (from /api/dataset/variation-labels)
 * @param {string[]} opts.existingLabels  labels of the shots already imported here
 * @param {number} [opts.byteLength]  file size, when known, checked before parsing
 * @returns {{blocked: ?{code,message}, accepted: object[],
 *            rejected: {index,label,code,message}[], ignoredFields: string[],
 *            skippedExamples: number}}
 */
export function parseShotImport(text, opts = {}) {
  const { subjectType, reservedLabels = [], existingLabels = [], byteLength = null } = opts;

  const size = byteLength == null ? String(text ?? '').length : byteLength;
  if (size > MAX_IMPORT_BYTES) {
    return blocked('too_large',
      `That file is ${Math.round(size / 1024)} KB — the limit is ${Math.round(MAX_IMPORT_BYTES / 1024)} KB. A shot catalog is a short list of prompts, not a data dump.`);
  }

  let payload;
  try {
    payload = JSON.parse(String(text ?? ''));
  } catch (error) {
    return blocked('not_json', `That file is not valid JSON (${error.message}).`);
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return blocked('not_object',
      'The file must be a JSON object with a "shots" array — not an array or a bare value.');
  }
  const shots = payload.shots;
  if (!Array.isArray(shots)) {
    return blocked('no_shots', 'The file has no "shots" array. Export your catalog to see the expected shape.');
  }
  if (!shots.length) {
    return blocked('empty', 'The "shots" array is empty — there is nothing to import.');
  }
  if (shots.length > MAX_IMPORT_SHOTS) {
    return blocked('too_many',
      `That file holds ${shots.length} shots — the limit is ${MAX_IMPORT_SHOTS}. Split it, or trim it down.`);
  }
  const fileSubject = isText(payload.subject_type) ? payload.subject_type.trim() : null;
  if (fileSubject && subjectType && fileSubject !== subjectType) {
    return blocked('subject_mismatch',
      `That file was written for the "${fileSubject}" subject type, but this dataset is "${subjectType}". Switch the subject type, or edit the file.`);
  }

  const reserved = new Set(reservedLabels.map(key));
  const taken = new Set(existingLabels.map(key));
  const seen = new Set();
  const accepted = [];
  const rejected = [];
  const ignored = new Set();

  shots.forEach((raw, i) => {
    const index = i + 1;
    const label = isText(raw?.label) ? raw.label.trim() : '';
    const refuse = (code, message) => rejected.push({ index, label, code, message });
    const named = label ? `“${label}”` : `entry #${index}`;

    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      refuse('not_object', `Entry #${index} is not an object.`);
      return;
    }
    Object.keys(raw).forEach((k) => { if (!KNOWN_FIELDS.has(k)) ignored.add(k); });

    if (!label) {
      refuse('missing_label', `Entry #${index} has no "label" (a short name shown on the card).`);
      return;
    }
    if (label.length > MAX_LABEL_LEN) {
      refuse('label_too_long', `${named}: the label is ${label.length} characters, the limit is ${MAX_LABEL_LEN}.`);
      return;
    }
    if (!isText(raw.prompt)) {
      refuse('missing_prompt', `${named} has no "prompt" — that is the text sent to the image engine.`);
      return;
    }
    const prompt = raw.prompt.trim();
    if (prompt.length > MAX_PROMPT_LEN) {
      refuse('prompt_too_long',
        `${named}: the prompt is ${prompt.length} characters, the limit is ${MAX_PROMPT_LEN} (longer prompts get truncated when a shot is regenerated).`);
      return;
    }
    if (raw.framing === undefined || raw.framing === null || raw.framing === '') {
      refuse('missing_framing', `${named} has no "framing". It must be one of: ${FRAMING_LIST}.`);
      return;
    }
    const framing = typeof raw.framing === 'string' ? raw.framing.trim().toLocaleLowerCase() : null;
    if (!FRAMINGS.includes(framing)) {
      refuse('bad_framing',
        `${named}: "${raw.framing}" is not a framing. It must be one of: ${FRAMING_LIST}.`);
      return;
    }
    if (raw.nsfw !== undefined && typeof raw.nsfw !== 'boolean') {
      refuse('bad_nsfw', `${named}: "nsfw" must be true or false, not "${raw.nsfw}".`);
      return;
    }
    const k = key(label);
    if (reserved.has(k)) {
      refuse('label_collides_builtin',
        `${named} is already a built-in shot label — rename it. Two shots sharing a label make the app resolve the wrong prompt when one is regenerated.`);
      return;
    }
    if (taken.has(k)) {
      refuse('label_collides_existing', `${named} is already one of your imported shots — rename it or remove the old one first.`);
      return;
    }
    if (seen.has(k)) {
      refuse('duplicate_label_in_file', `${named} appears twice in this file — labels must be unique.`);
      return;
    }
    seen.add(k);
    accepted.push({ label, prompt, framing, ...(raw.nsfw === true ? { nsfw: true } : {}) });
  });

  return {
    blocked: null,
    accepted,
    rejected,
    ignoredFields: [...ignored],
    skippedExamples: Array.isArray(payload.examples) ? payload.examples.length : 0,
  };
}

const slug = (label) => key(label).replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 24) || 'shot';

/**
 * Merge the ACCEPTED shots of a parse result into the existing list. Ids are
 * minted here and never taken from the file: an LLM happily reuses `bust_front`,
 * and ids are what saved presets store (`datasetCustomPresetsV1.selectedIds`).
 */
export function applyShotImport(existing, accepted) {
  const list = Array.isArray(existing) ? [...existing] : [];
  const used = new Set(list.map((s) => s?.id).filter(Boolean));
  for (const shot of accepted || []) {
    let id = `imp_${slug(shot.label)}`;
    let n = 2;
    while (used.has(id)) { id = `imp_${slug(shot.label)}_${n}`; n += 1; }
    used.add(id);
    list.push({
      id, label: shot.label, prompt: shot.prompt, framing: shot.framing,
      ...(shot.nsfw ? { nsfw: true } : {}), imported: true,
    });
  }
  return list;
}

/**
 * The file the user hands to an LLM — and their backup. It carries THEIR shots
 * (round-trips cleanly) plus a few built-ins under `examples`, which the importer
 * ignores by contract: without that, the model echoes the samples back and the
 * user eats six label collisions on their very first import.
 */
export function buildShotExport({ subjectType, shots = [], catalog = [] }) {
  const step = Math.max(1, Math.ceil(catalog.length / EXAMPLE_COUNT));
  const examples = catalog.filter((_, i) => i % step === 0).slice(0, EXAMPLE_COUNT)
    .map(({ label, framing, prompt }) => ({ label, framing, prompt }));
  return `${JSON.stringify({
    format: SHOT_IMPORT_FORMAT,
    subject_type: subjectType,
    instructions: `Add shots to the "shots" array. Each shot needs a unique "label" (max ${MAX_LABEL_LEN} chars), a "framing" among ${FRAMING_LIST}, and a "prompt" (max ${MAX_PROMPT_LEN} chars) describing the image to produce. Labels must not repeat a built-in label — see "examples", which this app ignores on import.`,
    shots: shots.map(({ label, framing, prompt }) => ({ label, framing, prompt })),
    examples,
  }, null, 2)}\n`;
}

