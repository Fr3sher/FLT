// 📷 Camera angles — what the plugin contributes to the Setup screen: the
// one-click plan, the labels, the counted capability row and the install-menu
// rows. Pure module: the core's `setup.step` slot calls `rows(caps)` and
// `catalog(caps)` (src/hooks/useSetupSteps.js), the card calls the plan.
import {
  COMFYUI_OFF_NOTE, COMFYUI_WAITING_TOPIC, brokenOrMissing,
} from '@lds/plugin-sdk/setup'

// Weights only, like SeedVR2 (the graph is stock ComfyUI nodes, so there is no
// pack to clone and no restart state). Mirrors the backend's install group —
// registered by lds_camera_angles.register — which stays the authority.
// `krea_vae` is a member on purpose: the lane runs on the Krea 2 VAE, and
// camera_missing reports that file under the action that installs it — one
// file, one button, whichever engine asked first.
export const CAMERA_INSTALL_ORDER = [
  'camera_model', 'camera_lora', 'camera_speed_lora', 'camera_text_encoder',
  'krea_vae',
]

// The lane's VAE has no row of its own on purpose: it is the Krea 2 VAE (same
// file, same destination), which the core's menu already labels.
export const CAMERA_ACTION_LABELS = {
  camera_model: 'Camera angles model (Qwen-Image-Edit 2511)',
  camera_lora: 'Camera angles LoRA (96 positions)',
  camera_speed_lora: 'Camera angles speed LoRA (4-step)',
  camera_text_encoder: 'Camera angles text encoder (Qwen 2.5-VL)',
}

const CAMERA_ROWS = ['camera_model', 'camera_lora', 'camera_speed_lora', 'camera_text_encoder']
const DIR_HINT = 'Point the app at a valid ComfyUI folder first (the ComfyUI step).'

export function cameraInstallPlan(caps) {
  const cu = (caps || {}).comfyui || {}
  if (!cu.dir_valid) return []
  const missing = brokenOrMissing(cu.camera_missing, cu.camera_invalid)
  return CAMERA_INSTALL_ORDER.filter((a) => missing.includes(a))
}

/** The counted capability row. Same counting rule as Krea, for the same
 *  reason: the verb ships to every install that has this plugin, so a machine
 *  without the weights must read "not ready, here is the install" — never a
 *  shorter list that certifies completeness by omission. `camera_ready` is
 *  asset-only (no node pack, no per-run process), so unlike the two engines
 *  there is no restart state — just installed or not, plus the shared
 *  "ComfyUI is off" note. */
export function cameraSetupRows(caps) {
  const c = caps || {}
  const cu = c.comfyui || {}
  const comfyOff = !!cu.dir_valid && !cu.reachable
  const missing = Array.isArray(cu.camera_missing) && cu.camera_missing.length
  return [{
    label: '📷 Camera angles (local)',
    what: 'Re-shoots a picture from another viewpoint, in your ComfyUI',
    ok: !!cu.camera_ready,
    topic: 'setup-camera-install', waitingTopic: COMFYUI_WAITING_TOPIC,
    ...(!cu.camera_ready && !missing && comfyOff ? { pending: true, note: COMFYUI_OFF_NOTE } : {}),
  }]
}

/** The install menu's rows — four, not five: the Qwen VAE is the core's
 *  krea_vae row (one file, one button). They exist for the same reason the
 *  Krea ones do: the weights were installable through the 409 and NOWHERE on
 *  the screen where the user decides they are done. */
export function cameraCatalogItems(caps) {
  const cu = ((caps || {}).comfyui) || {}
  const dirValid = !!cu.dir_valid
  const missing = Array.isArray(cu.camera_missing) ? cu.camera_missing : []
  return CAMERA_ROWS.map((action) => ({
    action, label: CAMERA_ACTION_LABELS[action],
    present: dirValid && !missing.includes(action),
    available: dirValid, hint: dirValid ? '' : DIR_HINT,
  }))
}
