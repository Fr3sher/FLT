// Pure derivation of the guided Setup wizard state from live capabilities.
// No I/O — deterministic, so it is the single source of truth for card status.

export const SETUP_STEP_IDS = ['image', 'comfyui', 'ollama', 'quality', 'training']

// Tool reachable + its extra piece present -> ready; reachable only -> partial.
function gateStatus(reachable, complete) {
  if (reachable && complete) return 'ready'
  if (reachable) return 'partial'
  return 'available'
}

function imageStep(caps) {
  const e = caps.engines || {}
  const ready = e.nanobanana || e.chatgpt || e.klein
  return {
    id: 'image', title: 'Image generation', recommended: true,
    unlocks: ['Nano Banana (Gemini)', 'ChatGPT (gpt-image-2)', 'Klein (local)'],
    status: ready ? 'ready' : 'available',
    engines: { nanobanana: !!e.nanobanana, chatgpt: !!e.chatgpt, klein: !!e.klein },
  }
}

// The Klein engine needs three weights on disk (UNET + text-encoder + VAE); the
// consistency LoRA is only recommended, so it never gates readiness. The backend
// lists the setup_installer action names still absent in comfyui.klein_missing —
// that is the source of truth, mirroring capabilities.klein_ready. Older payloads
// (pre-klein_missing) fall back to the UNET-only scan.
const KLEIN_REQUIRED_ASSETS = ['klein_model', 'klein_text_encoder', 'klein_vae']

// setup_installer action name -> the short human word used in Setup/picker hints.
export const KLEIN_ASSET_LABELS = {
  klein_model: 'model',
  klein_text_encoder: 'text encoder',
  klein_vae: 'VAE',
}

// Human names of the REQUIRED Klein weights still missing (recommended LoRA
// excluded), in a stable canonical order — so both the Setup step header and the
// picker's Klein hint can say exactly what to download. Empty => the trio is on disk.
export function kleinMissingLabels(kleinMissing) {
  const m = Array.isArray(kleinMissing) ? kleinMissing : []
  return KLEIN_REQUIRED_ASSETS.filter((a) => m.includes(a)).map((a) => KLEIN_ASSET_LABELS[a])
}

function kleinMissingRequired(c) {
  if (Array.isArray(c.klein_missing)) {
    return c.klein_missing.filter((a) => KLEIN_REQUIRED_ASSETS.includes(a))
  }
  // Legacy fallback: judge on the UNET scan alone (the old, under-strict signal).
  return (c.models && c.models.klein && c.models.klein.length) ? [] : ['klein_model']
}

// The user's choice to "continue without ComfyUI" (Setup step). The backend
// derives `comfyui.skipped` = the stored flag AND no directory configured, so it
// self-annuls the moment a path is entered. We only treat the step as skipped when
// ComfyUI is ALSO not reachable — a running ComfyUI is worth surfacing (partial/
// ready) even if the user once clicked skip.
function comfyuiStep(caps) {
  const c = caps.comfyui || {}
  const missingRequired = kleinMissingRequired(c)
  // Present-but-INVALID required assets (a licence-gate HTML page saved as
  // .safetensors, a truncated download): the file exists so it is NOT in
  // klein_missing, yet it can't load. Without this the step would go green and let
  // a doomed generate crash ComfyUI (the #help "Expecting value: line 1 column 1").
  // Only *blocking* invalids gate readiness; the advisory too_small does not.
  const kleinInvalid = Array.isArray(c.klein_invalid) ? c.klein_invalid : []
  const blockingInvalid = kleinInvalid.filter(
    (i) => i && i.blocking && KLEIN_REQUIRED_ASSETS.includes(i.asset))
  // hasKlein now reflects FULL readiness (all three weights, each a real file), not
  // just the UNET — so the step no longer goes "nothing to do" while the TE/VAE are
  // still missing or while a present asset is actually an unusable stub.
  const hasKlein = missingRequired.length === 0 && blockingInvalid.length === 0
  // Which assets to still offer a download for (required trio + recommended LoRA),
  // so each button can grey out on its own once its file lands.
  const kleinMissing = Array.isArray(c.klein_missing)
    ? c.klein_missing
    : (hasKlein ? [] : ['klein_model'])
  // Skipped is neutral, not a warning — but only when there's genuinely nothing to
  // show (unreachable). It never overrides a reachable ComfyUI's real status.
  const skipped = !!c.skipped && !c.reachable
  const status = skipped ? 'skipped' : gateStatus(c.reachable, hasKlein)
  return {
    id: 'comfyui', title: 'ComfyUI — local generation & Test Studio', recommended: false,
    unlocks: ['Klein engine', 'Test Studio'],
    status, reachable: !!c.reachable, hasKlein, kleinMissing, kleinInvalid, apiUrl: c.api_url || '',
    skipped,
    // Whether comfyui.base_dir actually points at a ComfyUI install (main.py + models/):
    // a wrong/portable-wrapper path scans an empty models/ and finds no checkpoints.
    // baseDir = the path this verdict was PROBED against — the UI must not show the
    // verdict for a freshly typed (unsaved) path, it would judge the wrong string.
    dirConfigured: !!c.dir_configured, dirValid: !!c.dir_valid, resolvedDir: c.resolved_dir || '',
    baseDir: c.base_dir || '',
  }
}

// What "continue without ComfyUI" costs vs keeps — shown in the skip-confirmation
// panel BEFORE the user commits. Sourced from the real capability gates (n'invente
// rien): studio_visible / engines.klein / watermark_klein key on ComfyUI being
// reachable with its models; the training base listers and the LoRA preset picker
// resolve from comfyui.base_dir. Everything under KEPT is independent of ComfyUI.
export const COMFYUI_SKIP_LOST = [
  'Local Klein generation, including the uncensored (NSFW) local lane',
  'Watermark cleaning with Klein (LaMa inpainting and crop still work)',
  'Test Studio (comparing checkpoints, every model family)',
  'Training on your own ComfyUI base models (built-in and cloud bases still work)',
  'Picking LoRA presets from what is on disk (free-text entry still works)',
]
export const COMFYUI_SKIP_KEPT = [
  'Scraping and dataset curation',
  'Captioning (Ollama vision model or the API engines)',
  'Nano Banana and ChatGPT image engines',
  'LoRA training — local ai-toolkit and cloud (vast.ai)',
  'Publishing datasets and LoRAs to Hugging Face',
]

// Map a /api/setup/comfyui-dir verdict to the wizard's inline feedback: a tone
// (drives the colour) and an actionable message. `suggestion` is carried through so
// the caller can render an "adopt this folder" button for the launcher-folder case.
// Pure + exhaustive so node --test can lock every branch. `checking` is the UI's own
// in-flight state; `empty` (nothing typed) renders nothing here — the skip panel owns it.
export function comfyuiDirVerdict(check) {
  const c = check || {}
  const resolved = c.resolved || ''
  const suggestion = c.suggestion || ''
  switch (c.status) {
    case 'valid':
      return { tone: 'ok', suggestion: '',
        message: resolved ? `ComfyUI found at ${resolved}.` : 'ComfyUI found.' }
    case 'nested':
      return { tone: 'warn', suggestion,
        message: `This looks like the launcher/parent folder — did you mean ${suggestion}?` }
    case 'missing':
      return { tone: 'warn', suggestion: '',
        message: "That folder doesn't exist yet — check the path." }
    case 'empty_dir':
      return { tone: 'warn', suggestion: '',
        message: 'That folder is empty — point at the folder that holds main.py and a models/ folder.' }
    case 'not_comfyui':
      return { tone: 'warn', suggestion: '',
        message: "This folder isn't a ComfyUI install — it must contain main.py and a models/ folder. "
          + 'For the portable build, point at the inner …\\ComfyUI_windows_portable\\ComfyUI.' }
    default:
      return { tone: 'muted', suggestion: '', message: '' }
  }
}

// ── ai-toolkit: what the wizard says about the folder it was pointed at ───────
// The old copy said one thing — "set up its Python venv per the README" — which
// names a CAUSE the app never verified and a remedy that is a dead end for whole
// families of installs: conda, uv, the system Python, and the portable/embedded
// bundles that ship a `python_embeded\python.exe` instead of a venv. Someone
// running one of those reasonably concluded the app REQUIRED a venv and went
// asking in public (reported on Reddit by Psyko_2000) instead of filling in a
// setting that was three clicks away. So the copy below states the OBSERVATION
// ("no interpreter found here") and opens both doors with equal weight — make
// one, or name the one you already have. Pure strings + a shape: node --test
// locks the wording, which is the part that was wrong.
export const AITOOLKIT_PYTHON_SETTING = 'Settings ▸ Local tools ▸ ai-toolkit Python interpreter'

// The install path, before any folder is configured. Same rule: the venv is ONE
// way to give ai-toolkit a Python, not the definition of a working install.
export const AITOOLKIT_INSTALL_STEPS = [
  { text: 'Clone ai-toolkit, or install it with the script of your choice.',
    command: 'git clone https://github.com/ostris/ai-toolkit' },
  { text: 'Give it a Python. Its README walks through creating a venv in that '
      + 'folder — or, if you already run it with a conda or uv environment, the '
      + 'system Python, or a portable/embedded build, keep that one and name it '
      + `in ${AITOOLKIT_PYTHON_SETTING}.` },
  { text: 'Point the app at the folder that holds run.py, below.' },
]

export function aitoolkitVerdict(step, dir) {
  const s = step || {}
  const path = (dir || '').trim()
  const base = { candidates: [], settingsSection: 'local-tools' }
  if (s.valid) {
    return { ...base, kind: 'ready', tone: 'ok',
      headline: `ai-toolkit is set up at ${path}.`, body: 'Nothing to do here.' }
  }
  if (!path) return { ...base, kind: 'unconfigured', tone: 'muted', headline: '', body: '' }
  if (!s.dirValid) {
    return { ...base, kind: 'not_a_checkout', tone: 'warn',
      headline: `No run.py in ${path}, so this isn't an ai-toolkit folder.`,
      body: "Point at the folder ai-toolkit was installed into — the one holding run.py." }
  }
  return {
    ...base,
    kind: 'no_interpreter',
    tone: 'warn',
    // The finding, not a diagnosis. True for every install shape.
    headline: `ai-toolkit is here, but no Python interpreter was found in ${path}.`,
    body: "The app doesn't know which Python to run it with. Two ways forward, "
      + "both fine: create a venv inside that folder (ai-toolkit's README walks "
      + 'through it), or keep the Python you already run ai-toolkit with — a conda '
      + 'or uv environment, your system Python, or the python.exe of a portable / '
      + 'embedded build (python_embeded) — and tell the app where it is.',
    action: `Set the interpreter in ${AITOOLKIT_PYTHON_SETTING}`,
    candidates: s.pythonCandidates || [],
  }
}

function ollamaStep(caps) {
  const o = caps.ollama || {}
  const status = gateStatus(o.reachable, o.vision_model_ready)
  return {
    id: 'ollama', title: 'Ollama — captioning & auto-framing', recommended: false,
    unlocks: ['Captioning', 'Auto-classify framing', 'Auto head-crop'],
    status, reachable: !!o.reachable, visionModelReady: !!o.vision_model_ready,
    url: o.url || '', visionModel: o.vision_model || '',
    // Execution-independent install signal (binary on disk) vs `reachable` (server
    // answering): installed && !reachable -> "installed but stopped", offer a Start.
    installed: !!o.installed, binaryPath: o.binary_path || '',
  }
}

function qualityStep(caps) {
  // Four scoped ML capabilities now (face scoring, masks, watermark inpainting,
  // bank scoring) — each installs/repairs on its own. The step is ready only when
  // all of them are in.
  const parts = [!!caps.face_scoring, !!caps.masks, !!caps.watermark_inpaint,
    !!caps.bank_scoring]
  const ready = parts.every(Boolean)
  const partial = parts.some(Boolean)
  return {
    id: 'quality', title: 'Quality tools (ML extras)', recommended: false,
    unlocks: ['Face-similarity scoring', 'Person masks', 'Watermark inpainting',
      'Bank scoring (aesthetic · NSFW · style)'],
    status: ready ? 'ready' : (partial ? 'partial' : 'available'),
    faceScoring: !!caps.face_scoring, masks: !!caps.masks,
    watermarkInpaint: !!caps.watermark_inpaint,
    bankScoring: !!caps.bank_scoring,
  }
}

function trainingStep(caps) {
  const a = caps.aitoolkit || {}
  return {
    id: 'training', title: 'LoRA training — ai-toolkit', recommended: false,
    unlocks: ['LoRA training', 'JoyCaption captioning (bonus)'],
    status: a.valid ? 'ready' : 'available',
    valid: !!a.valid,
    // dirValid = run.py is there. Told apart from `valid` so the wizard can say
    // WHICH of the two problems it hit instead of one blanket sentence.
    dirValid: !!a.dir_valid,
    pythonCandidates: Array.isArray(a.python_candidates) ? a.python_candidates : [],
  }
}

export function deriveSetupSteps(caps) {
  const c = caps || {}
  return [imageStep(c), comfyuiStep(c), ollamaStep(c), qualityStep(c), trainingStep(c)]
}

// The user's live capability checklist (Summary card). Watermark inpainting is a
// distinct ML extra (simple-lama-inpainting) — an existing install that never ran
// it must SEE it as still missing here, not be told "everything's ready".
export function deriveCapabilitySummary(caps) {
  const c = caps || {}
  const e = c.engines || {}
  const o = c.ollama || {}
  const cap = c.captioners || {}
  // "Configured but ComfyUI isn't running" is NOT a missing capability: the
  // install is fine, the process just isn't up. Those rows show as OK with a
  // "launch ComfyUI to enable" note instead of a discouraging ✗.
  const cu = c.comfyui || {}
  const comfyOff = !!cu.dir_valid && !cu.reachable
  const NOTE = 'launch ComfyUI to enable'
  return [
    { label: 'Nano Banana (Gemini)', ok: !!e.nanobanana },
    { label: 'ChatGPT (gpt-image-2)', ok: !!e.chatgpt },
    { label: 'Klein (local)', ok: !!e.klein,
      ...(!e.klein && comfyOff ? { pending: true, note: NOTE } : {}) },
    { label: 'Captioning', ok: !!(cap.joycaption || cap.ollama) },
    { label: 'Auto-framing & head-crop', ok: !!(o.reachable && o.vision_model_ready) },
    { label: 'Face-similarity scoring', ok: !!c.face_scoring },
    { label: 'Person masks', ok: !!c.masks },
    { label: 'Watermark inpainting', ok: !!c.watermark_inpaint },
    { label: 'LoRA training', ok: !!c.training_visible },
    { label: 'Test Studio', ok: !!c.studio_visible,
      ...(!c.studio_visible && comfyOff ? { pending: true, note: NOTE } : {}) },
  ]
}

export function recommendedMet(caps) {
  const e = (caps && caps.engines) || {}
  return !!(e.nanobanana || e.chatgpt || e.klein)
}

// --- "Install everything" plan -------------------------------------------------
// Mirror of setup_installer.install_all_plan (backend — the AUTHORITY that the
// POST /api/setup/install-all recomputes and queues). Kept here so the Setup page can
// show the plan and an accurate "X / N" reactively from caps, without a round-trip, the
// same way deriveSetupSteps mirrors the backend gates. Both MUST stay in step: the set
// is the MISSING components the app can install ITSELF right now — the ML extras, the
// Ollama vision model when Ollama is already up, and the Klein weights when a valid
// ComfyUI folder is set. It never installs ComfyUI/Ollama themselves or pastes API keys
// (those are external tools / credentials), so those stay on the step-by-step path.

// Setup-installer action -> the short human label shown in the Install-everything list.
export const INSTALL_ALL_ACTION_LABELS = {
  face_scoring: 'Face-similarity scoring',
  masks: 'Person masks',
  watermark_inpaint: 'Watermark inpainting',
  ollama_model: 'Vision model (captioning)',
  klein_model: 'Klein model (local generation)',
  klein_text_encoder: 'Klein text encoder',
  klein_vae: 'Klein VAE',
  klein_lora: 'Klein consistency LoRA',
}

// Grouped by capability area (ML extras → vision model → Klein weights). The backend
// serializes pip and parallelizes downloads regardless of fire order, so this order
// only drives the progress list; it must match the backend's _INSTALL_ALL_ORDER.
export const INSTALL_ALL_ORDER = [
  'face_scoring', 'masks', 'watermark_inpaint', 'ollama_model',
  'klein_model', 'klein_text_encoder', 'klein_vae', 'klein_lora',
]

export function installAllPlan(caps) {
  const c = caps || {}
  // face_scoring/masks install into the app's OWN Python, so they need it inside the ML
  // wheel range; on a newer interpreter they'd only source-build and fail. Absent python
  // info => assume supported (older payloads). watermark_inpaint builds its own venv, so
  // it stays runnable regardless.
  const mlOk = !(c.python && c.python.ml_supported === false)
  const o = c.ollama || {}
  const cu = c.comfyui || {}
  const kleinMissing = Array.isArray(cu.klein_missing) ? cu.klein_missing : []
  const needed = (a) => {
    if (a === 'face_scoring' || a === 'masks') return mlOk && !c[a]
    if (a === 'watermark_inpaint') return !c.watermark_inpaint
    if (a === 'ollama_model') {
      return !!(o.reachable && !o.vision_model_ready && (o.vision_model || '').trim())
    }
    // klein_* — only into a validated ComfyUI tree.
    return !!cu.dir_valid && kleinMissing.includes(a)
  }
  return INSTALL_ALL_ORDER.filter(needed)
}

// The FULL one-by-one install menu (Setup "install" step). Unlike installAllPlan — which
// lists only what's MISSING and satisfiable now, i.e. what the "Install everything" shortcut
// queues — this lists EVERY app-installable component with its live state, so the menu stays
// visible and each item can be (re)installed on its own even once green (repairing a broken
// venv is the whole point of the reinstall button). Per item:
//   present   — the capability is already in place (drives the ✓ Installed / ✗ badge)
//   available — can be (re)installed from HERE right now (its precondition is met): ML extras
//               need the app's Python in the wheel range OR an already-present env to repair;
//               the vision model needs Ollama reachable + a model name; Klein weights need a
//               validated ComfyUI tree. Unavailable items render their `hint` instead of a
//               button, pointing back at the config step that unblocks them.
export function installCatalog(caps) {
  const c = caps || {}
  const mlOk = !(c.python && c.python.ml_supported === false)
  const mlRange = (c.python && c.python.ml_range) || '3.10–3.12'
  const mlHint = `Needs Python ${mlRange} — install it into a separate 3.10–3.12 env and set its path in Settings.`
  const o = c.ollama || {}
  const modelName = (o.vision_model || '').trim()
  const cu = c.comfyui || {}
  const dirValid = !!cu.dir_valid
  const kleinMissing = Array.isArray(cu.klein_missing) ? cu.klein_missing : []
  const kleinHint = 'Point the app at a valid ComfyUI folder first (the ComfyUI step).'
  const item = (action, present, available, hint) => ({
    action, label: INSTALL_ALL_ACTION_LABELS[action] || action,
    present: !!present, available: !!available, hint: available ? '' : hint,
  })
  const mlItem = (action) => {
    const present = mlOk ? !!c[action] : !!c[action]
    // Install fresh only when the app's Python supports the wheels; ALWAYS allow a
    // repair of one that's already present (its install targets whatever env it lives in).
    return item(action, present, mlOk || present, mlHint)
  }
  return [
    mlItem('face_scoring'),
    mlItem('masks'),
    item('watermark_inpaint', c.watermark_inpaint, true, ''),   // auto-provisions its own venv
    item('ollama_model', o.vision_model_ready, o.reachable && modelName,
      !o.reachable ? 'Start Ollama first (the Captioning step).'
        : !modelName ? 'Set a vision model name first (the Captioning step).' : ''),
    ...['klein_model', 'klein_text_encoder', 'klein_vae', 'klein_lora'].map(
      (a) => item(a, dirValid && !kleinMissing.includes(a), dirValid, kleinHint)),
  ]
}
