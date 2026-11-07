import { postJson } from '../../api/fetchClient'

export async function completeCoreSetup(goal) {
  await postJson('/api/setup-state/complete', goal === 'dataset' ? { goal } : {})
  try { sessionStorage.setItem('lds_setup_redirected', '1') } catch { /* The server remembers completion even when browser storage is disabled. */ }
}
