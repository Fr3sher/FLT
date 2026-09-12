import { contributions } from './registry.js'
import { IMPROVE_ENGINES } from '../utils/improveEngines.js'
import { INSTALL_ALL_ACTION_LABELS } from '../hooks/useSetupSteps.js'

// Stored results can still name a historical engine. Availability, however,
// belongs to the active plugin and is distinct from its preparation verdict.
export function improveEngine(id) {
  return contributions('improve.engine').find(engine => engine.id === id)
    || IMPROVE_ENGINES.find(engine => engine.id === id)
    || IMPROVE_ENGINES.find(engine => engine.id === 'klein')
}

export function availableImproveEngines() {
  return contributions('improve.engine')
}

export function improvementAvailable(engineId) {
  return availableImproveEngines().some(engine => !engineId || engine.id === engineId)
}

export function installActionLabel(action) {
  for (const step of contributions('setup.step', 'setup')) {
    const label = step.labels?.[action]
    if (typeof label === 'string' && label.trim()) return label
  }
  return INSTALL_ALL_ACTION_LABELS[action] || action
}
