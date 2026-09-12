import { brokenOrMissing } from '@lds/plugin-sdk/setup'
export const INSTALL_ALL_ACTION_LABELS = {
  seedvr2_model: 'SeedVR2 model (3B FP8)', seedvr2_vae: 'SeedVR2 VAE',
}
export function seedvr2InstallPlan(caps) {
  const cu = caps?.comfyui || {}
  if (!cu.dir_valid) return []
  const missing = brokenOrMissing(cu.seedvr2_missing, cu.seedvr2_invalid)
  return Object.keys(INSTALL_ALL_ACTION_LABELS).filter(action => missing.includes(action))
}
export function seedvr2NeedsComfyuiRestart(caps) {
  const cu = caps?.comfyui || {}
  return !!(cu.seedvr2_nodes_installed && cu.seedvr2_nodes_missing?.length)
}
export function setupRows(caps) {
  return [{ label: 'SeedVR2 restoration', what: 'Upscale pictures while preserving their look',
    ok: caps?.comfyui?.seedvr2_ready === true, topic: 'setup-seedvr2-install' }]
}
export function catalog(caps) {
  const cu = caps?.comfyui || {}
  const missing = brokenOrMissing(cu.seedvr2_missing, cu.seedvr2_invalid)
  return Object.entries(INSTALL_ALL_ACTION_LABELS).map(([action, label]) => ({
    action, label, present: !!cu.dir_valid && !missing.includes(action),
    available: !!cu.dir_valid,
    hint: cu.dir_valid ? '' : 'Connect a valid ComfyUI folder in Local tools first.',
  }))
}
