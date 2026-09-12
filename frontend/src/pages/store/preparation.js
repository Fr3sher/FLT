import { apiFetch, postJson } from '../../api/fetchClient.js'

export const preparationStatusUrl = actions => `/api/setup/install-all/status?${new URLSearchParams({ actions: actions.join(',') })}`

export function preparationState(actions, statuses) {
  const rows = actions.map(action => statuses?.[action]?.state)
  if (!rows.length) return 'idle'
  if (rows.every(state => state === 'success' || state === 'error')) {
    return rows.includes('error') ? 'error' : 'prepared'
  }
  return rows.some(state => state === 'running' || state === 'queued') ? 'running' : 'unknown'
}

export async function startPreparation(pluginId, actions) {
  const result = await postJson(`/api/plugins/${encodeURIComponent(pluginId)}/preparation`, { actions })
  if (!Array.isArray(result.plan) || !result.plan.length
      || result.plan.some(action => typeof action !== 'string' || !action)
      || new Set(result.plan).size !== result.plan.length) {
    throw new Error('The server did not return a preparation plan. Check the plugin before retrying.')
  }
  return { actions: result.plan, statuses: result.statuses || {} }
}

// A missing status is not completion. Stop displaying progress when the server
// cannot be reached, and let Retry status attach to the existing workers.
export async function watchPreparation(actions, { onStatus, signal,
  read = () => apiFetch(preparationStatusUrl(actions), { signal }),
  wait = () => new Promise(resolve => setTimeout(resolve, 1200)),
} = {}) {
  let failures = 0
  let missing = 0
  while (!signal?.aborted) {
    let result
    try { result = await read() } catch (error) {
      if (signal?.aborted) return 'cancelled'
      if (++failures >= 3) throw new Error(`Preparation status is unavailable. ${error.message || ''}`.trim())
      await wait()
      continue
    }
    failures = 0
    if (signal?.aborted) return 'cancelled'
    const statuses = result.statuses || {}
    const state = preparationState(actions, statuses)
    onStatus?.(statuses)
    if (state === 'prepared' || state === 'error') return state
    if (state === 'unknown' && ++missing >= 10) throw new Error('The server has no active status for this preparation. Check the components before retrying.')
    if (state === 'running') missing = 0
    await wait()
  }
  return 'cancelled'
}
