import { brokenOrMissing } from '@lds/plugin-sdk/setup'
export const INSTALL_ALL_ACTION_LABELS = {
  seedvr2_nodes: 'SeedVR2 node pack and dependencies',
  seedvr2_model: 'SeedVR2 model (3B FP8)', seedvr2_vae: 'SeedVR2 VAE',
}
export const SEEDVR2_ACTIONS = Object.keys(INSTALL_ALL_ACTION_LABELS)
const nodePackPresent = cu => !!cu.seedvr2_nodes_installed || !!cu.reachable && !cu.seedvr2_nodes_missing?.length
export function seedvr2InstallPlan(caps) {
  const cu = caps?.comfyui || {}
  if (!cu.dir_valid) return []
  const missing = brokenOrMissing(cu.seedvr2_missing, cu.seedvr2_invalid)
  return SEEDVR2_ACTIONS.filter(action => action === 'seedvr2_nodes'
    ? !nodePackPresent(cu) : missing.includes(action))
}
export function seedvr2NeedsComfyuiRestart(caps) {
  const cu = caps?.comfyui || {}
  return !!(cu.seedvr2_nodes_installed && cu.seedvr2_nodes_missing?.length)
}
export function seedvr2PreparationPlan(value) {
  if (!Array.isArray(value) || value.some(action => !SEEDVR2_ACTIONS.includes(action))
      || new Set(value).size !== value.length) throw new Error('The SeedVR2 preparation plan could not be read. Re-check and try again.')
  return value
}
export function seedvr2PreparationState(actions, statuses) {
  if (actions.some(action => statuses[action]?.state === 'error')) return 'error'
  if (actions.every(action => statuses[action]?.state === 'success')) return 'prepared'
  if (actions.some(action => !['running', 'queued', 'success'].includes(statuses[action]?.state))) return 'unavailable'
  return 'running'
}
export function seedvr2PreparationError(actions, statuses) {
  const action = actions.find(key => statuses[key]?.state === 'error')
  const log = statuses[action]?.log
  const detail = Array.isArray(log) ? log.filter(line => typeof line === 'string').slice(-4).join('\n') : ''
  return detail || 'SeedVR2 preparation needs attention. Re-check the installation before retrying.'
}
export function setupRows(caps) {
  return [{ label: 'SeedVR2 restoration', what: 'Upscale pictures while preserving their look',
    ok: caps?.comfyui?.seedvr2_ready === true, topic: 'setup-seedvr2-install' }]
}
export function catalog(caps) {
  const cu = caps?.comfyui || {}
  const missing = brokenOrMissing(cu.seedvr2_missing, cu.seedvr2_invalid)
  return Object.entries(INSTALL_ALL_ACTION_LABELS).map(([action, label]) => ({
    action, label, present: !!cu.dir_valid && (action === 'seedvr2_nodes'
      ? nodePackPresent(cu) : !missing.includes(action)),
    available: !!cu.dir_valid,
    hint: cu.dir_valid ? '' : 'Connect a valid ComfyUI folder in Local tools first.',
  }))
}
