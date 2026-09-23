/* The Video Test Studio's request shapes, kept out of the components.
 *
 * Two reasons this is its own module rather than inline `fetch` calls:
 *
 *  - the payload has ten fields and four of them change what ComfyUI actually
 *    computes (turbo, sparse, the base swap, the upscale). A mistake there does
 *    not throw — it renders a perfectly good clip that answers a different
 *    question than the one that was asked. `node --test` can check this shape;
 *    it cannot check a component;
 *  - the panel and the history read the same clip objects, and the labels below
 *    are what stop "sparse: max" from being written three different ways.
 */

export const VIDEO_STUDIO_BASE = '/api/video-studio';

export const optionsUrl = () => `${VIDEO_STUDIO_BASE}/options`;
export const lorasUrl = () => `${VIDEO_STUDIO_BASE}/loras`;
export const deployUrl = () => `${VIDEO_STUDIO_BASE}/deploy`;

/** Where a LoRA the user already has is brought into the picker. */
export const loraImportUrl = () => '/api/video-studio/lora/import';

/** ↗ Smooth a finished clip — RIFE interpolation, as a new clip. */
export const clipVfiUrl = (id) => `/api/video-studio/clip/${id}/vfi`;
/** ⏭ Stage a finished clip's last frame as the next start frame (POST), and
 *  the same frame as a picture for the strip (GET). */
export const clipLastFrameUrl = (id) => `/api/video-studio/clip/${id}/last-frame`;
export const clipLastFramePngUrl = (id) => `/api/video-studio/clip/${id}/last-frame.png`;
/** ↗ The rates Smooth can make of a clip. RIFE interpolates by a WHOLE factor,
 *  so the choices are the source rate times 2, 3 and 4 — 48, 72, 96 fps for a
 *  clip authored at 24 — never an arbitrary number (that would mean dropping
 *  frames unevenly afterwards). `cost` is relative to the ×2 pass: the work
 *  grows with the frames written between each pair (1, 2, 3). */
export const SMOOTH_MULTIPLIERS = [2, 3, 4];
export function smoothTargets(clip) {
  const fps = Number(clip?.fps) > 0 ? Number(clip.fps) : 24;
  const frames = Number(clip?.frames) > 0 ? Number(clip.frames) : null;
  return SMOOTH_MULTIPLIERS.map((m) => ({
    multiplier: m,
    fps: Math.round(fps * m * 1000) / 1000,
    frames: frames ? (frames - 1) * m + 1 : null,
    cost: m - 1,
  }));
}

/** ✨ Neural render a finished clip — DLSS 5 Neural Rendering, as a new clip. */
export const clipNeuralRenderUrl = (id) => `/api/video-studio/clip/${id}/neural-render`;

/** ✨ The Motion field's two helpers: propose from the start frame, or enrich
 * what is already written. Both answer with a prompt the user can still edit —
 * neither is a launch. */
export const motionSuggestUrl = () => '/api/video-studio/motion/suggest';
/** ⏭🎞 What the ✨ writers get beyond the frame and the text: the clip a
 *  frame continues (the next part carries the take on) and the staged last
 *  frame (the motion lands on it). Null when absent — the server then adds
 *  nothing to the ask. Text-only has no frame to continue from. */
export function writerContext({ frame = null, endFrame = null, mode = 'i2v', references = [], refBase, refImageSize, refmods = false } = {}) {
  return {
    continues: mode === 't2v' ? null : (frame?.continues || null),
    end_image: endFrame?.image || null,
    ...(refmods ? { mode, refmods: true, references } : {}),
    ...(mode === 'ref2va' ? { mode, references, ref_base: refBase || 'official',
      ref_image_size: refImageSize || 'match' } : {}),
  };
}
/* ✨ One window, N frames. Entering the vision window makes ComfyUI drop its
   models, so writing per picture through the two single-frame routes would
   reload the video model once per picture. See the route's docstring. */
export const motionWriteBatchUrl = () => '/api/video-studio/motion/write-batch';
export const motionEnhanceUrl = () => '/api/video-studio/motion/enhance';

/** ⚙ The model that writes the motion — listed, and chosen. */
export const motionModelsUrl = () => '/api/video-studio/motion/models';
export const motionModelUrl = () => '/api/video-studio/motion/model';
export const motionDialsUrl = () => '/api/video-studio/motion/dials';
/** ⚙ How reference VIDEOS are read before the writer sees them: the vision
 *  model's two frames, or JoyCaption on three separate stills. */
export const motionObserverUrl = () => '/api/video-studio/motion/reference-observer';
export const sourceUrl = () => `${VIDEO_STUDIO_BASE}/source`;
export const generateUrl = () => `${VIDEO_STUDIO_BASE}/generate`;
/** The history, newest first: one page of `limit`, `before` (a clip id) for the
 * page after it. The server appends the SOURCE of every listed render, so the
 * pair a comparison needs is always on screen together. */
/** The newest page REPLACES what it covers and KEEPS what it does not.
 *  `keepOlderThan` is the boundary of the page PROPER (the server's
 *  `oldest_id`), never the oldest id on the page: a source that rode along
 *  with its render is older by construction, and taking it as the boundary
 *  dropped every loaded clip between the two at every poll. Deleted rows
 *  leave through the page they belonged to, which the fresh page no longer
 *  carries. */
export function mergeClipPages(prev, fresh, keepOlderThan) {
  const byId = new Map();
  (fresh || []).forEach((c) => byId.set(c.id, c));
  (prev || []).forEach((c) => { if (c.id < keepOlderThan && !byId.has(c.id)) byId.set(c.id, c); });
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

export const clipsUrl = (limit = 24, before = null) =>
  `${VIDEO_STUDIO_BASE}/clips?limit=${limit}${before ? `&before=${before}` : ''}`;
export const clipUrl = (id) => `${VIDEO_STUDIO_BASE}/clip/${id}`;
export const clipVideoUrl = (id) => `${VIDEO_STUDIO_BASE}/clip/${id}/video`;
export const clipRateUrl = (id) => `${VIDEO_STUDIO_BASE}/clip/${id}/rate`;
/** ⬇ A render and its source as ONE side-by-side mp4 (404 when the clip is
 * not a render, or its source is gone). */
export const clipComparisonUrl = (id) => `${VIDEO_STUDIO_BASE}/clip/${id}/comparison`;

/* The sparse levels, in the order they cost adherence. The wording says what
 * each one DOES to the picture rather than naming a budget: "0.3 video budget"
 * is the node's vocabulary, not a user's, and the only decision here is how
 * much prompt fidelity to trade for speed. */
export const SPARSE_CHOICES = [
  { value: '', label: 'Off', hint: 'Dense attention — the reference render.' },
  { value: 'conservative', label: 'Conservative',
    hint: 'Faster, edges of the schedule kept dense. Safest with a prompt that matters.' },
  { value: 'default', label: 'Default',
    hint: 'The node author\'s defaults — roughly 1.6× faster.' },
  { value: 'max', label: 'Max',
    hint: 'Sparse on every pass, including the one that sets the composition. '
        + 'Fastest, and the prompt is followed less closely.' },
];

/* Whether a clip is still on its way. One predicate, so the poller, the button
 * and the tile cannot disagree about what "running" means. */
export const isRunning = (clip) => !!clip && (clip.status === 'pending');

/** The body of POST /generate.
 *
 * Only what was actually chosen is sent: an option left off is ABSENT rather
 * than `false`, so the server's defaults stay the single definition of "off"
 * and a future default change does not have to be mirrored here.
 *
 * `image` is dropped in t2v even when one was picked earlier, because the
 * server would otherwise be handed a start frame for a mode that has no start
 * frame — the kind of mismatch that gets answered with a clip nobody can
 * explain rather than an error.
 */
/** 🎬 How many shots the writers cut the clip into — the server's
 *  MAX_SHOTS, mirrored (pinned both ways by a test that reads both files). 1 is
 *  one continuous take: H3's format gives Shot 1 no timecode, so a single shot
 *  never has one; 2 or more cut the clip at even timecodes ("[Shot 2] At
 *  00:05.000, the camera cuts to …"). */
export const SHOT_CHOICES = [1, 2, 3, 4, 5, 6];

/** The most shots a clip of `seconds` can hold — the server's own rule
 *  (`shot_count`: never more than one per second on four seconds or less; a
 *  cut every 0.7 s is a flicker). Mirrored so the panel greys what the server
 *  would silently trim. */
export function shotCap(seconds) {
  const x = Number(seconds);
  if (!Number.isFinite(x) || x <= 0) return SHOT_CHOICES.length;
  // Python's round() rounds halves to EVEN; Math.round rounds them up. The
  // server's clip_seconds is the former, so the same rule lives here —
  // and, like it, a known length is never less than one second.
  const lo = Math.floor(x);
  const frac = x - lo;
  const s = Math.max(1, frac > 0.5 ? lo + 1 : (frac < 0.5 ? lo : (lo % 2 === 0 ? lo : lo + 1)));
  if (s <= 4) return Math.min(SHOT_CHOICES.length, s);
  return SHOT_CHOICES.length;
}

export function buildGeneratePayload(state) {
  const s = state || {};
  const mode = s.mode === 'ref2va' ? 'ref2va' : s.mode === 't2v' ? 't2v' : 'i2v';
  const body = { mode, prompt: (s.prompt || '').trim() };
  if (mode === 'i2v') {
    if (s.image) body.image = s.image;
    if (s.ratio) body.ratio = s.ratio;
  } else if (s.aspect) {
    body.aspect = s.aspect;
  }
  if (mode === 'ref2va') {
    body.references = s.references || [];
    body.ref_base = s.refBase || 'official';
    body.ref_image_size = s.refImageSize || 'match';
    if (s.image) body.image = s.image;
  }
  if (mode !== 'ref2va' && s.refmods) {
    body.refmods = true;
    body.references = s.references || [];
  }
  if (s.lora) {
    body.lora = s.lora;
    body.lora_strength = Number(s.loraStrength ?? 1);
    if (s.runId) body.run_id = s.runId;
    if (s.datasetId) body.dataset_id = s.datasetId;
  }
  if (s.frames) body.frames = Number(s.frames);
  if (s.megapixels) body.megapixels = Number(s.megapixels);
  if (s.seed !== '' && s.seed !== null && s.seed !== undefined) {
    body.seed = Number(s.seed);
  }
  if (s.steps) body.steps = Number(s.steps);
  // ✨ Enrich at launch: the SERVER rewrites the motion and records what ran,
  // so a clip never claims a prompt that is not the one it was made from.
  if (s.enhance) body.enhance = true;
  // 🎞 The picture the clip ENDS on (H3 first-last conditioning): a staged
  // name, sent only when one was picked.
  if (s.endImage) body.end_image = String(s.endImage);
  // 🎬 The shot plan for that server-side rewrite: sent only when it is not
  // the default, so a launch that never touched the control reads as before.
  if (Number(s.shots) > 1) body.shots = Number(s.shots);
  // ⚡ The acceleration by name; `turbo` rides along for the older servers'
  // boolean when the name is larryvrh's.
  if (mode === 'ref2va') {
    body.accel = ['ref4', 'ref8', 'vdn'].includes(s.accel) ? s.accel : '';
  } else if (s.accel) {
    body.accel = s.accel;
    if (s.accel === 'turbo') body.turbo = true;
  } else if (s.turbo) {
    body.turbo = true;
  }
  // ⚡ The sparse level IN FORCE, not the one kept in state: VDN-H3 and sparse
  // attention patch the same path, the server refuses the pair, and the panel,
  // the readback and this payload all read the same helper so none of them
  // can claim a level the clip will not render with.
  const sparse = sparseInForce(s, mode === 'ref2va');
  if (sparse) body.sparse = sparse;
  if (mode !== 'ref2va') {
    if (s.eros) body.eros = true;
    if (s.light) body.light = true;
    if (s.latentUpscale) body.latent_upscale = true;
  }
  for (const key of ['h3_attention', 'h3_spectrum', 'h3_video_vae', 'h3_video_writer']) {
    if (s[key] !== undefined) body[key] = s[key];
  }
  if (s.fused && mode !== 'ref2va') body.fused = true;
  // ⏭ The clip this launch continues: the render is joined behind it.
  if (mode !== 't2v' && s.continues) body.continues = Number(s.continues);
  return body;
}

/** ⚡ The Render panel's acceleration choices, as the server names them —
 *  this list is only the shape shown before the options arrive (and in tests);
 *  the server's `accelerations` carries availability, arena rank and hint. */
export const ACCELERATIONS = [
  { id: 'taomate_3step', label: 'TaoMate H3 · 3 steps', arena: '', steps: 3 },
  { id: 'fasth3_v02', label: 'FastH3 v0.2', arena: '', steps: 4 },
  { id: 'turbo', label: 'larryvrh Turbo v4', arena: '#1 · I2V 1103 / T2V 1110', steps: 6 },
  { id: 'parasyte', label: 'Parasyte Turbo', arena: '#2 · I2V 1106 / T2V 1094', steps: 6 },
  { id: 'dareties', label: 'DARE-TIES merge', arena: '#3 · I2V 1107 / T2V 1085', steps: 6 },
  // ⚡ Not an arena row (it postdates it): OpenVDN's hybrid attention over the
  // base, 8 steps on the base's own shift. `arena` empty = no rank printed;
  // the hint is the server's first sentence, so the static shape never wears
  // the LoRA fallback while /options is on its way (or down).
  { id: 'vdn', label: 'VDN-H3 hybrid attention', arena: '', steps: 8,
    hint: "OpenVDN's linear-attention branch over the base: 8 steps on the base's own shift, "
      + 'not faster than turbo on one card — compare quality and long clips.' },
];
/** The sparse level a launch will actually carry: none while VDN-H3 is picked
 *  in every mode, since the two patch the same attention path and
 *  the server refuses the pair. The panel's select, the readback beside
 *  Generate and the payload all read this, so a level kept in state from an
 *  earlier pick is shown as off everywhere, not just greyed in one place. */
export function sparseInForce(state) {
  if (!state?.sparse) return '';
  if (state.accel === 'vdn' || state.h3_attention === 'sage' || state.h3_spectrum) return '';
  return state.sparse;
}
/** The option line of the ⚡ select: the rank when the arena has one, the
 *  bare label when it does not (VDN-H3 postdates the arena). */
export const accelOptionText = (a) => `${a.label}${a.arena ? ` · arena ${a.arena}` : ''}${
  a.available === false ? ' — not installed' : ''}`;
export const accelLabel = (id) => ({ ref4: 'Reference Turbo 4', ref8: 'Reference Turbo 8' }[id])
  || (ACCELERATIONS.find((a) => a.id === id) || {}).label
  || (id ? String(id) : '');
/** The acceleration a clip ran with: the stored name, or `turbo` from the
 *  flag on rows older than the choice. */
export const clipAccel = (clip) => (clip?.accel || (clip?.turbo ? 'turbo' : ''));
/** What the panel should hold once the server said what is on this machine:
 *  the current pick if it is available (or unknown), else the first available
 *  one, else the dense base. `null` availability (probe unreachable) keeps
 *  the pick — an unknown is not a no. */
export function pickAvailableAccel(current, accelerations) {
  const rows = Array.isArray(accelerations) ? accelerations : [];
  if (!current) return '';
  const row = rows.find((a) => a.id === current);
  if (!row || row.available !== false) return current;
  const other = rows.find((a) => a.available === true);
  return other ? other.id : '';
}

/** How long the clip will be, in seconds, at the target's own fps.
 * N frames span N-1 intervals — the same arithmetic the training lane uses, so
 * a 39-frame clip reads as the same duration in both places. */
export { clipSeconds } from '@lds/plugin-sdk/h3';

/** The one-line summary under a finished clip.
 *
 * Ordered by how much each thing changed the render: the base first (it is a
 * different model), then the LoRA and its strength, then the accelerators.
 * Options that were off contribute nothing — a row of "turbo: no, sparse: no"
 * is noise in a list whose entire job is showing what differed.
 */
export function clipSummary(clip) {
  if (!clip) return '';
  const bits = [];
  if (clip.eros) bits.push('🔥 10Eros');
  if (clip.light) bits.push('🪶 W4A8');
  if (clip.lora) {
    const name = String(clip.lora).replace(/\\/g, '/').split('/').pop()
      .replace(/\.safetensors$/i, '');
    bits.push(`${name} @ ${clip.lora_strength ?? 1}`);
  } else {
    bits.push('no LoRA');
  }
  const accel = clipAccel(clip);
  if (accel) bits.push(accel === 'turbo' ? '⚡ turbo' : `⚡ ${accelLabel(accel)}`);
  if (clip.sparse) bits.push(`sparse ${clip.sparse}`);
  if (clip.latent_upscale) bits.push('🔬 upscale');
  if (clip.continues_of) bits.push(`⏭ continues #${clip.continues_of}`);
  if (clip.end_image) bits.push('🎞 ends on a picture');
  bits.push(`${clip.steps} steps`);
  if (clip.seed !== null && clip.seed !== undefined) bits.push(`seed ${clip.seed}`);
  return bits.join(' · ');
}

/** Every legal clip length the STUDIO may generate, not the ones training uses.
 *
 * The dropdown was built from `frame_choices` — the TRAINING catalogue, which
 * stops at 209 frames because that is where training clip lengths stop being
 * useful. The model renders to about 15 s, the server has always accepted it
 * (FRAMES_MIN/FRAMES_MAX = 22/362, and its own comment says capping the studio
 * at 8.7 s would be "a reason that has nothing to do with the studio") — the
 * list on screen was simply the wrong table. Generated from the bounds and the
 * VAE's own rule (≡ 5 mod 17), so there is one source of truth and no third
 * copy of the ladder.
 */
export { studioFrameChoices } from '@lds/plugin-sdk/h3';

// ⏱ The launch advice, as two sentences. The server decides WHETHER to speak
// (video_test_studio.launch_advice: the flag missing, a ComfyUI that knows it,
// a machine whose RAM cannot hold the weights); this only phrases what it
// sent, and never spells a flag of its own — every name comes from the payload,
// so a second flag on the server side needs no change here.
export function launchAdviceLines(advice) {
  if (!advice || !advice.flag) return null;
  const { flag, add, remove } = advice;
  const title = remove
    ? `ComfyUI is running with ${remove}, which switches off the loader ${flag} relies on`
    : `ComfyUI is running without ${flag}`;
  let change;
  if (remove && add) change = `Remove ${remove} and add ${flag}`;
  else if (remove) change = `Remove ${remove} (${flag} is already on the command line)`;
  else change = `Add ${flag}`;
  return {
    title,
    action: `${change} on the command that starts ComfyUI, then start it again.`,
  };
}

// ⏱ Render time as a person reads it: "24 s", "5 min 48 s", "2 min", "1 h 12 min".
// The number is the queue's own measurement (claim → settled, model loading
// included); null for anything that is not a positive number, so a card never
// prints "rendered in null" for a clip the queue could not time. A measured
// fraction of a second reads "1 s" — a real measurement is rounded, never hidden.
export function renderTimeLabel(seconds) {
  const s = Number(seconds);
  if (!Number.isFinite(s) || s <= 0) return null;
  const t = Math.max(1, Math.round(s));
  if (t < 60) return `${t} s`;
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const r = t % 60;
  if (h) return m ? `${h} h ${m} min` : `${h} h`;
  return r ? `${m} min ${r} s` : `${m} min`;
}

/** 🔍 A start frame as a library row — what the SHARED viewer needs before its
 *  verbs (✨ improve, 🔍 upscale, ✦ repair, 📷 camera angles, 📤 Civitai) can
 *  address the picture. A frame picked from the Gallery keeps ITS row — no
 *  copy, its own prompt and facts; anything else (an upload, a bank portrait,
 *  a dataset clip's first frame, a clip's last frame) travels as the staged
 *  name and the server copies the picture once, by content. */
export const frameAdoptUrl = () => `${VIDEO_STUDIO_BASE}/frame/adopt`;
/** The image dataset an adopted frame belongs to — the PAGE's, or nothing.
 *  Never the LoRA's: a video LoRA's dataset_id names a row of another table
 *  (video datasets), and sent to a route that resolves image datasets it
 *  would land the frame in an unrelated one. null lets the server use its
 *  holding dataset — the video lane lives on /studio, under no dataset. */
export function frameDatasetIdOf({ pageDatasetId = null } = {}) {
  const n = Number(pageDatasetId);
  return Number.isInteger(n) && n > 0 ? n : null;
}
export function frameAdoptBody(frame, datasetId) {
  const m = /^gallery:(\d+)$/.exec(String(frame?.key || ''));
  if (m) return { gallery_image_id: Number(m[1]) };
  return { dataset_id: datasetId == null ? null : Number(datasetId), image: frame?.image || '' };
}
