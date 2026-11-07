// Which plugin contributions currently hold a LAYER over a host — a picker, a
// dialog — so the host can stand its own keys down (arrows, Escape) while any
// of them is open.
//
// One flag for the whole slot was the bug (measured in Chromium, 2026-09-05):
// two contributions on `lightbox.action`, each reporting its own layer through
// the same `onLayer`, and a re-render of the host replayed every panel's
// effect in slot order — the LAST contributor's `onLayer(false)` overwrote the
// first one's open picker, and the arrows walked the list under it. Tracking
// per contribution makes "closed" a statement about ONE contribution, never
// about the slot.
//
// Pure JS: a host keeps one tracker for the life of the component (a ref) and
// hands each contribution its own callback through PluginSlot's `itemProps`.
export function createLayerTracker(onChange) {
  const open = new Set()
  const callbacks = new Map()
  const any = () => open.size > 0
  return {
    /** The `onLayer(isOpen)` callback for ONE contribution — stable per key, so
     *  a panel's effect keyed on it does not re-run on every host render. */
    onLayerFor(key) {
      if (!callbacks.has(key)) {
        callbacks.set(key, (isOpen) => {
          const before = any()
          if (isOpen) open.add(key)
          else open.delete(key)
          const after = any()
          if (before !== after && typeof onChange === 'function') onChange(after)
        })
      }
      return callbacks.get(key)
    },
    /** Is any contribution holding a layer? */
    any,
    /** Which ones are (for a test, a debug line). */
    openKeys() { return [...open] },
    /** Forget every layer (a host that changes its subject wholesale). */
    reset() {
      const before = any()
      open.clear()
      if (before && typeof onChange === 'function') onChange(false)
    },
  }
}

/** The tracker key of one slot contribution. */
export function contributionKey(item) {
  return `${item.plugin}:${item.id}`
}
