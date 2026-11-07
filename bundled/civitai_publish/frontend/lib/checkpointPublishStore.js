// Checkpoint dialog state outlives the popover and is cleared on navigation.
let current = null
const listeners = new Set()

function emit() {
  for (const fn of listeners) fn()
}

export function openCheckpointPublish(node, pill) {
  current = { node, pill }
  emit()
}

export function closeCheckpointPublish() {
  current = null
  emit()
}

export function getCheckpointPublish() {
  return current
}

/** The checkpoint context passed from the popover to its persistent dialog layer. */
export function publishContextOf(target) {
  if (!target) return null
  return { kind: 'checkpoint', node: target.node, pill: target.pill }
}

export function subscribeCheckpointPublish(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
