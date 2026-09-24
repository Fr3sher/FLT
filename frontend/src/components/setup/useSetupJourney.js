import { useMemo, useSyncExternalStore } from 'react'
import { normalizeJourney } from './setupJourney.js'

export const JOURNEY_STORAGE_KEY = 'lds_setup_journey_v1'
const EVENT = 'lds-setup-journey-changed'
let transient = null

function snapshot() {
  if (transient !== null) return transient
  try { return window.localStorage.getItem(JOURNEY_STORAGE_KEY) || '' } catch { return '' }
}
function subscribe(callback) {
  const storage = event => { if (!event.key || event.key === JOURNEY_STORAGE_KEY) callback() }
  window.addEventListener(EVENT, callback)
  window.addEventListener('storage', storage)
  return () => { window.removeEventListener(EVENT, callback); window.removeEventListener('storage', storage) }
}
export function saveSetupJourney(value) {
  const journey = normalizeJourney(value)
  const raw = journey ? JSON.stringify(journey) : ''
  let persisted = true
  try {
    if (raw) window.localStorage.setItem(JOURNEY_STORAGE_KEY, raw)
    else window.localStorage.removeItem(JOURNEY_STORAGE_KEY)
    transient = null
  } catch { transient = raw; persisted = false }
  window.dispatchEvent(new Event(EVENT))
  return persisted
}
export function useSetupJourney() {
  const raw = useSyncExternalStore(subscribe, snapshot, () => '')
  return useMemo(() => {
    try { return normalizeJourney(JSON.parse(raw)) } catch { return null }
  }, [raw])
}
