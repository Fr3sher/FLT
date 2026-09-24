// Only these coarse feature names may leave the browser. A route, search term,
// plugin name or dataset identifier is never an analytics property.
export const USAGE_FEATURES = new Set([
  'datasets', 'bank', 'training', 'studio', 'gallery',
  'setup', 'plugins', 'settings', 'guide',
])

export function usageFeature(pathname) {
  if (typeof pathname !== 'string') return null
  const path = pathname.split(/[?#]/, 1)[0].replace(/\/$/, '')
  if (path === '/datasets') return 'datasets'
  if (path === '/bank') return 'bank'
  if (path === '/cloud') return 'training'
  if (path === '/studio' || /^\/dataset\/studio\/[^/]+$/.test(path)) return 'studio'
  if (path === '/gallery') return 'gallery'
  if (path === '/setup') return 'setup'
  if (path === '/plugins' || /^\/plugins\/[^/]+\/settings$/.test(path)) return 'plugins'
  if (path === '/settings' || /^\/settings\/[^/]+$/.test(path)) return 'settings'
  if (path === '/guide' || path === '/help' || /^\/guide\/[^/]+$/.test(path)) return 'guide'
  return null
}

export function shouldSendUsageActivity({ enabled, trusted, visible, feature, now, lastSent }) {
  return enabled === true && trusted === true && visible === true
    && USAGE_FEATURES.has(feature) && Number.isFinite(now)
    && (lastSent === undefined || now - lastSent >= 60_000)
}
