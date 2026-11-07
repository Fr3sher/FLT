import { contributions } from '../plugins/registry.js'
/* Which engine runs the ✨ Upscale & improve pass, and how the UI says what the
   difference IS.

   The whole point of issue #32 (SurpassHR) is that the two passes are not two
   qualities of the same thing: Klein REWRITES (a diffusion edit that re-renders
   skin and micro-detail — it fixes a soft photo and it changes it), SeedVR2
   RESTORES (one-step super-resolution that leaves the content alone). Someone
   picking blind will pick wrong on a dataset built around an exact look, so the
   one-line positioning lives here, next to the ids, rather than being retyped in
   each surface where it could drift apart.

   Pure module, no JSX — the contract tests run under `node --test`. */

export const IMPROVE_ENGINES = []
const HISTORICAL_ENGINES = {
  klein: { id: 'klein', label: 'Klein', emoji: '✨' },
  seedvr2: { id: 'seedvr2', label: 'SeedVR2', emoji: '🔍' },
}

const DEFAULT_IMPROVE_ENGINE = 'klein'

export function improveEngine(id) {
  return [...IMPROVE_ENGINES, ...contributions('improve.engine')].find((e) => e.id === id)
    || HISTORICAL_ENGINES[id] || HISTORICAL_ENGINES[DEFAULT_IMPROVE_ENGINE]
}

/** Active plugins remain discoverable before their engines are prepared.
    Launch guards below still enforce readiness; absent/disabled plugins have
    no contribution and therefore no action or preparation link. */
export function availableImproveEngines() {
  return [...IMPROVE_ENGINES, ...contributions('improve.engine')]
}

function preparationReason(engine, caps) {
  return typeof engine.ready === 'function' && !engine.ready(caps)
    ? engine.blockedReason || `${engine.label} needs preparation.` : null
}

/** The registry supplies the owner, so preparation opens that plugin's own
    settings even when it is the only installed restoration plugin. */
export function improvePreparations(caps) {
  return availableImproveEngines().flatMap(engine => {
    const reason = preparationReason(engine, caps)
    return reason ? [{ id: engine.id, plugin: engine.plugin, label: engine.label, reason }] : []
  })
}

/** Why an engine's bulk button is disabled, or null when it can run. */
export function improveEngineBlockedReason(engineId, { caps, engines, eligibleCount } = {}) {
  if (engineId === 'klein' && engines && engines.klein === false) {
    return 'Klein is not available in this setup'
  }
  {
    const engine = contributions('improve.engine').find(item => item.id === engineId)
    if (!engine) return 'This restoration plug-in is not active. Open the Store.'
    const preparation = preparationReason(engine, caps)
    if (preparation) return preparation
  }
  if (!eligibleCount) return 'No selected image is eligible.'
  return null
}

/** The confirm text for a bulk run. States the engine's trade in the sentence
    the user reads immediately before committing a long batch. */
export function improveConfirmMessage(engineId, { eligibleCount = 0, exclusionSummary = '',
  excludedCount = 0 } = {}) {
  const engine = improveEngine(engineId)
  const skipped = excludedCount
    ? `\n\n${excludedCount} selected image(s) will be skipped: ${exclusionSummary}.`
    : ''
  return `${engine.confirm} for ${eligibleCount} image(s)?\n\n${engine.summary}${skipped}`
    + '\n\nThey are queued a few at a time in the background — you can close this tab,'
    + ' and ⏹ Stop generation ends the batch.'
    + '\n\nOriginal images stay unchanged until you review the candidates.'
}

/** Toast wording for a launched batch: what the server took, what it dropped,
    and which engine actually ran (the server echoes it, so a stale tab cannot
    claim the wrong one). */
export function describeImproveLaunch({ queued = 0, skipped = 0, engine } = {}) {
  const name = improveEngine(engine).label
  const tail = skipped ? ` · ${skipped} not eligible and skipped` : ''
  return `${name}: processing ${queued} image(s) in the background${tail} — originals stay intact.`
    + ' You can close this tab; ⏹ Stop generation ends the batch.'
}

/** Live progress line for a bulk button, from the dataset's server activity.
    `null` when no improve batch is running. The engine comes from the activity
    (the server records it at begin()), so the label names the run that is
    ACTUALLY going, not whichever button you are hovering. */
export function improveBatchLabel(activity) {
  if (!activity || activity.kind !== 'improve') return null
  const engine = improveEngine(activity.engine)
  const total = Number(activity.total) || 0
  const done = Number(activity.done) || 0
  if (activity.cancelling) return `${engine.emoji} Stopping…`
  return total
    ? `${engine.emoji} ${engine.label} ${done}/${total}`
    : `${engine.emoji} ${engine.label}…`
}

/** The per-image ✨ buttons for ONE image in the lightbox: one entry per engine
    this install can run, in display order.

    The lightbox is an EXPLICIT per-image choice, so both engines are offered
    side by side and neither is decided by the `improve.engine` setting — that
    setting only governs surfaces with a single ✨ button. This is the same rule
    the bulk toolbar follows, expressed once.

    `{id, label, title, disabled, showKleinNote}` per engine:
      * `label` reflects the IMAGE's state (a candidate already waiting for
        review, one still rendering) before the engine's own name, because that
        state blocks every engine equally and is what the user needs to read.
      * `showKleinNote` is true for Klein alone. The amber anime/drawn warning is
        about Klein's INSTRUCTION ("detailed texture, sharp details") pulling
        drawn skin towards realism — SeedVR2 sends no instruction at all, so
        repeating the warning under it would be false and would push people away
        from the very pass that fixes their case.

    Pure: no JSX, no capabilities probing of its own — `node --test` covers it. */
export function lightboxImproveButtons({ caps, engines, improving = false,
  improvePending = false, improveReady = false, busy = false,
  // Which dataset pass is holding this image, when the caller knows. "Another
  // action is running" is true and useless; the named pass tells you how long.
  busyReason = null } = {}) {
  const active = improving || improvePending
  // Blocked for reasons that have nothing to do with WHICH engine: one
  // improvement per image at a time, and one waiting result must be reviewed
  // before another is made.
  const imageBlocked = busy || active || improveReady
    ? (improveReady
        ? 'A new version is waiting for validation.'
        : active
          ? 'An improvement is already running for this image.'
          : (busyReason || 'Another action is running on this image.'))
    : null
  return availableImproveEngines(caps).map((engine) => {
    // `eligibleCount: 1` — the lightbox always acts on exactly this image, so
    // the shared reason function is asked only about engine readiness.
    const engineBlocked = improveEngineBlockedReason(engine.id, {
      caps, engines, eligibleCount: 1,
    })
    const reason = imageBlocked || engineBlocked
    return {
      id: engine.id,
      label: improveReady
        ? '✓ Review improvement first'
        : active
          ? `${engine.emoji} Improving…`
          : `${engine.emoji} ${engine.action}`,
      title: reason
        ? `${reason} ${engine.summary}`
        : `${engine.summary} The original stays intact — a separate candidate is created for you to validate.`,
      disabled: !!reason,
      showKleinNote: engine.id === 'klein',
    }
  })
}

export function improvementAvailable(engineId) {
  return contributions('improve.engine').some(engine => !engineId || engine.id === engineId)
}
