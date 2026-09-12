// Saving a new storage root requires the move's explicit completion receipt.
// Losing progress does not mean the worker stopped or that its files arrived.
export async function waitForStorageMove(read, onState, {
  wait = () => new Promise(resolve => setTimeout(resolve, 700)),
  attempts = 100000, maxFailures = 6,
} = {}) {
  let failures = 0
  for (let i = 0; i < attempts; i += 1) {
    await wait()
    let state
    try { state = await read() }
    catch {
      failures += 1
      if (failures >= maxFailures) throw new Error('Move progress is unavailable. The folder was not changed; check the move before retrying.')
      continue
    }
    if (!state || !['scanning', 'copying', 'done', 'error'].includes(state.phase)) {
      throw new Error('Move progress is invalid. The folder was not changed.')
    }
    failures = 0
    onState(state)
    if (state.phase === 'error') throw new Error(state.error || 'The move failed.')
    if (state.phase === 'done') return state
  }
  throw new Error('The move has not confirmed completion. The folder was not changed.')
}
