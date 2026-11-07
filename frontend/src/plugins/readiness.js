import { contributions } from './registry.js'

// Reuse the product's own Setup verdicts; activation alone is not readiness.
export function productReadiness(pluginId, caps, { withTargets = false } = {}) {
  const rows = []
  for (const step of contributions('setup.step', 'setup').filter(item => item.plugin === pluginId)) {
    if (typeof step.rows !== 'function') continue
    try {
      for (const row of step.rows(caps) || []) {
        rows.push({ label: row.label, state: row.pending ? 'pending' : row.ok ? 'ready' : 'setup',
          note: row.note || '', what: row.what || '',
          ...(withTargets ? { topic: row.topic, waitingTopic: row.waitingTopic } : {}) })
      }
    } catch {
      rows.push({ label: 'Product setup', state: 'unknown', note: 'Open Setup to check these components.' })
    }
  }
  return rows
}
