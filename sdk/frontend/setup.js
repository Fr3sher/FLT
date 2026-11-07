// Public readiness semantics. Only blocking integrity verdicts need a repair;
// advisory size warnings never turn a working model into a missing download.
import { runtime } from './runtime.js'
export const COMFYUI_OFF_NOTE = 'launch ComfyUI to enable'
export const COMFYUI_WAITING_TOPIC = 'comfyui.api_url'
export function brokenOrMissing(missing, invalid) {
  const out = Array.isArray(missing) ? [...missing] : []
  for (const item of Array.isArray(invalid) ? invalid : []) {
    if (item?.blocking && !out.includes(item.asset)) out.push(item.asset)
  }
  return out
}
export function fmtSize(bytes) {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(2)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`
  return `${Math.max(0, Math.round(bytes / 1e3))} KB`
}

// The local engines belong to the host. A plugin that asks one to repair an
// imported picture uses the same readiness decision as other work screens.
export function localEngineUnavailableReason(...args) {
  return runtime().localEngineUnavailableReason(...args)
}
