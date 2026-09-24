// The video lane's Setup rows, install-menu items and one-click plan — the
// `setup.step` contribution of the bundled `video` plugin, moved verbatim from
// the core's useSetupSteps.js (2026-09-05). The core merges `rows(caps)` into
// its capability summary and `catalog(caps)` into its install menu, so a
// machine without the weights reads "not ready, here is the install" rather
// than a shorter list that certifies completeness by omission.
import { COMFYUI_OFF_NOTE, COMFYUI_WAITING_TOPIC } from '@lds/plugin-sdk/setup';
import { VIDEO_INSTALL_LABELS } from './videoInstallLabels.js'
import { REFERENCE_ACTIONS, referenceMissingActions } from '../studio/video/videoReferenceInstall.js'

const NOTE = COMFYUI_OFF_NOTE
const WAITING = COMFYUI_WAITING_TOPIC

/** The capability rows the Setup summary counts for this lane. */
export function videoSetupRows(caps) {
  const c = caps || {}
  const cu = c.comfyui || {}
  const comfyOff = !!cu.dir_valid && !cu.reachable
  // The Video lane's three doors (rows below): each is its own install, so
  // each is its own row. `videoWeightsThere` is the "weights on disk" half of
  // the pending rule the 🎬 row already applies — down only because ComfyUI
  // is; Smooth's packs are read from /object_info, unreadable while it is.
  // REQUIRED weights only — the list also carries the optional ones (10Eros,
  // the W4A8 base, the upscaler), and an install that has everything it needs
  // must not lose the note because it skipped an opt-in. Same filter as the
  // server's `video_studio_ready`.
  const videoWeightsThere = !(Array.isArray(cu.video_studio_missing)
    && cu.video_studio_missing.some((m) => m && m.required))
  const vfi = (cu.video_studio_options && cu.video_studio_options.vfi) || {}
  const smoothOk = !!cu.video_studio_ready && vfi.available === true
  return [
    // 🎬 Counted like Krea and Camera angles, and for the same reason: the Video
    // tab ships to every install, so a machine without the weights must read
    // "not ready, here is the install" rather than vanish from the denominator.
    // Its OPTIONS are not counted — each one degrades a checkbox, not the lane.
    { label: '🎬 Video Test Studio (beta)', what: 'Tests a LoRA in motion — image- or text-to-video clips with MiniMax H3', ok: !!cu.video_studio_ready,
      topic: 'setup-video-studio', waitingTopic: WAITING,
      ...(!cu.video_studio_ready
        && !(Array.isArray(cu.video_studio_missing) && cu.video_studio_missing.length)
        && comfyOff ? { pending: true, note: NOTE } : {}) },
    { label: '↗ Smooth (frame interpolation)', ok: smoothOk,
      what: "Doubles or triples a clip's frame rate — RIFE, two ComfyUI node packs",
      topic: 'setup-video-studio', waitingTopic: WAITING,
      ...(!smoothOk && videoWeightsThere && comfyOff ? { pending: true, note: NOTE } : {}) },
    // Counted for the same reason Krea is: the final screen used to certify
    // "12 of 12 ready" on a machine whose video lane could not open one file.
    // A capability that is absent must be visible and counted, never removed
    // from the denominator.
    { label: 'Video tools in LDS', what: 'Reading, analysis and video downloads inside LDS', ok: !!c.video_host_ready, topic: 'setup-quality' },
    { label: 'Video bank — reading files', what: 'Opens video files: length, thumbnails, quality, cuts (PyAV)', ok: !!c.video_decode, topic: 'setup-quality' },
    { label: 'Video bank — shot detection', what: 'Splits a video at its shot boundaries (TransNetV2)', ok: !!c.video_detect, topic: 'setup-quality' },
    // The THIRD video piece. capabilities.probe_video() reports decode / detect /
    // encode apart on purpose ("a single boolean would be a lie here"), and the
    // encoder fails on its own for a documented reason: imageio-ffmpeg answers
    // with a path whether or not its binary download ever finished, so `av` can
    // import (decode ✓) on a machine where no ffmpeg exists. Same install action
    // as decoding (`video` = PyAV + imageio-ffmpeg), so the fix is one ↻
    // Reinstall on the quality step, but it is a separate row because a green
    // "reading files" is not the answer to it.
    { label: 'Video bank — clip encoding', what: 'Cuts and exports clips (ffmpeg)', ok: !!c.video_encode, topic: 'setup-quality' },
  ]
}

/** One install-menu row, in the core's shape. */
function item(action, present, available, hint) {
  return {
    action, label: VIDEO_INSTALL_LABELS[action] || action,
    present: !!present, available: !!available, hint: available ? '' : hint,
  }
}

/** The one-by-one install menu's rows for this lane. */
export function videoInstallCatalog(caps) {
  const c = caps || {}
  const cu = c.comfyui || {}
  const dirValid = !!cu.dir_valid
  const kleinHint = 'Point the app at a valid ComfyUI folder first (the ComfyUI step).'
  // 🎬 The video engine's five files, one row each. `videoStudioMissing` holds
  // the ones absent from disk; anything not in it is present. Gated on a valid
  // ComfyUI folder, because that is where they land.
  const videoStudioMissing = (Array.isArray(cu.video_studio_missing)
    ? cu.video_studio_missing : []).map((m) => m && m.action).filter(Boolean)
  const refMissing = referenceMissingActions(cu.video_studio_reference)
  const h3AttentionMissing = Array.isArray(cu.h3_attention_nodes_missing)
    && cu.h3_attention_nodes_missing.length > 0
  const h3AttentionPresent = !!cu.h3_attention_nodes_installed
    || !!(cu.reachable && !h3AttentionMissing)
  const h3AttentionRestart = !!cu.h3_attention_nodes_installed && h3AttentionMissing
  return [
    // The video extras were installable through the API and NOWHERE on the
    // Setup screen once — the banner in the Video bank said "Install … from
    // Setup" and the menu had no such row. `video` (PyAV) goes into the app's
    // configured Python — no torch, always available. `video_host` explicitly
    // repairs the modules used inside LDS; `shot_detect` rides the scoring
    // environment, like the watermark detector. `video` installs BOTH halves
    // (PyAV + imageio-ffmpeg), so it is "present" only when both probes are
    // green: keyed on decoding alone it badged ✓ Installed on a machine whose
    // ffmpeg download never finished.
    item('video', c.video_decode && c.video_encode, true, ''),
    item('video_host', c.video_host_ready, true, ''),
    item('shot_detect', c.video_detect, true, ''),
    // The safe-zone pass's OCR half — CPU onnxruntime, into the app's own Python.
    // Listed even though the pass runs without it: a user who reads "bands only"
    // on the button needs a row to click.
    item('video_text', c.video_text, true, ''),
    // 🎬 Video Test Studio — five WEIGHT rows and no pack row, which is the
    // whole shape of this lane's install: the app downloads model files and
    // ClipProj's required node pack has its own reviewed installation action.
    ...['h3_base', 'h3_text_encoder', 'h3_clip_projection', 'h3_clipproj_nodes', 'h3_video_vae', 'h3_video_vae_int8', 'h3_audio_vae',
      'h3_turbo_lora', 'h3_parasyte_lora', 'h3_dareties_lora', 'h3_base_light',
      'h3_vdn_stage', 'h3_vdn_stage_int8'].map(
      (a) => item(a, dirValid && !videoStudioMissing.includes(a), dirValid, kleinHint)),
    ...REFERENCE_ACTIONS.map((a) => item(a,
      dirValid && !!cu.video_studio_reference && !refMissing.has(a), dirValid, kleinHint)),
    // 🔴 The block-attention switch: shipped with the app, copied into
    // custom_nodes (like the Krea preset sampler); a copy ComfyUI has not
    // loaded yet is a restart, not an install.
    {
      ...item('h3_attention_nodes', dirValid && h3AttentionPresent && !h3AttentionRestart,
        dirValid, kleinHint),
      ...(h3AttentionRestart ? { state: 'restart', stateLabel: '⟳ Restart ComfyUI' } : {}),
    },
  ]
}

// The Video Test Studio's one-click install: the REQUIRED weights and the
// small accelerations. A 12.5 GB opt-in belongs to its own row in the install
// menu, like 10Eros stays out of any grouped button.
export const VIDEO_STUDIO_INSTALL_ORDER = [
  'h3_base', 'h3_text_encoder', 'h3_clip_projection', 'h3_clipproj_nodes', 'h3_video_vae', 'h3_audio_vae', 'h3_turbo_lora',
  'h3_parasyte_lora', 'h3_dareties_lora',
]

export function videoStudioInstallPlan(caps) {
  const cu = (caps || {}).comfyui || {}
  if (!cu.dir_valid) return []
  // An entry with no `action` is a file the app will not fetch: it gets a
  // sentence in the card, never a button here.
  const missing = (Array.isArray(cu.video_studio_missing) ? cu.video_studio_missing : [])
    .map((m) => m && m.action).filter(Boolean)
  return VIDEO_STUDIO_INSTALL_ORDER.filter((a) => missing.includes(a))
}

// The Quality step's video-only install cards. Shared OCR stays in the core.
export const VIDEO_ML_CARDS = [
  { before: 'video_text', action: 'video', cap: ['video_decode', 'video_encode'], icon: '🎬',
    title: 'Video decoding (the 🎬 Video bank reads your files)',
    body: 'Installs decoding and analysis tools into the Video interpreter selected in settings, or LDS when no separate interpreter is configured. Checks decoding there and clip encoding inside LDS after installation. No torch or GPU is needed.' },
  { before: 'video_text', action: 'video_host', cap: 'video_host_ready', icon: '🎬',
    title: 'Video tools inside LDS',
    body: 'Repairs file reading, thumbnails, analysis and video downloads in LDS itself. Use this when the configured Video interpreter works but these tools are missing in LDS. This button installs only into the LDS interpreter.' },
  { before: 'video_text', action: 'shot_detect', cap: 'video_detect', icon: '🎞️',
    title: 'Shot detection (triage shots, not whole rushes)',
    body: 'Cuts each video at its shot boundaries (TransNetV2) so a two-hour file becomes hundreds of individually reviewable shots. Installs torch (CPU is fine — the network reads 48×27 frames) and one small package into the scoring Python it shares with ✨ Score. Without it you can still watch and triage whole files; you just cannot split them.' }
]
