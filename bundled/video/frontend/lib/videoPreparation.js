// HTTP admission/progress validation only; component selection stays on the server.
const STATES = new Set(['idle', 'queued', 'running', 'success', 'error'])
export function admittedVideoPlan(requested, response) {
  const plan = response?.plan
  if (!Array.isArray(plan) || !plan.length || new Set(plan).size !== plan.length
    || plan.some(action => !requested.includes(action))) {
    throw new Error('No valid Video preparation plan was returned. Re-check before retrying.')
  }
  return [...plan]
}
export function videoBatchProgress(actions, statuses) {
  if (!actions.length || !statuses || actions.some(a => !STATES.has(statuses[a]?.state))) {
    throw new Error('Video installation progress is incomplete. Re-check before retrying.')
  }
  const failed = actions.some(a => statuses[a].state === 'error')
  return { failed, done: actions.filter(a => statuses[a].state === 'success').length,
    terminal: failed || actions.every(a => statuses[a].state === 'success') }
}
