// Slots are named by FEATURE and mounted on every surface that carries the
// feature. This table is DATA, not a naming convention: it is what makes the
// Bank↔Dataset parity rule ("a shared feature ships on both surfaces at full
// parity", CLAUDE.md) expressible for a plugin contribution, and what
// parity.contract.test.js reads. A contribution to a paired slot renders on
// every surface listed here unless the plugin writes a `paritySkip`
// { slot, surface, reason } — an exception on paper, never a silent gap.
export const PAIRED_SURFACES = Object.freeze({
  'resource_monitor.readout': ['header', 'canvas'],
  'sources.panel': ['dataset', 'bank', 'videoBank'],   // "import or scrape" panels
  'more.menu': ['dataset', 'bank'],                    // the ⋯ More menus
  'lanes': ['bank', 'videoBank'],                      // the Images / Video lane tabs
  // The ☁ launch of a training on a rented GPU (the cloud plugin's): on the
  // dataset's Training panel and on the video set's training block — the
  // same feature on both kinds of set, at parity.
  'training.launch': ['dataset', 'video'],
  // Shared extension points; their providers remain separately installed.
  'video.neural-render-dialog': ['dataset', 'studio'],
  'video.neural-compare': ['dataset', 'studio'],
  'lightbox.action': ['dataset', 'bank', 'gallery'],   // verbs on a generated image
  // The checkpoint popover's rows, and the layer its hosts keep mounted for a
  // row's dialog — on the two surfaces that mount the shared popover, and on
  // the video dataset's checkpoints (its list and its own graph popover).
  'checkpoint.action': ['graph', 'canvas', 'video'],
  'checkpoint.layer': ['graph', 'canvas', 'video'],
})

// Slots that live on ONE surface by nature (no parity to keep).
export const SINGLE_SURFACE_SLOTS = Object.freeze({
  'runs.hub': 'runs',
  'training.tool': 'dataset',
  // The Training panel's seams for the cloud lane (wave 10): a DATA lane of
  // the Continue dialog `{ id, label, availability(ctx), resume(payload, ctx) }`,
  // the mirrored cloud saves under the local set, the full-model panel.
  'training.continue.lane': 'dataset',
  'training.dense': 'dataset',
  'studio.tab': 'studio',
  'settings.section': 'settings',
  'settings.group': 'settings',
  'settings.credential.help': 'settings',
  'settings.registry': 'settings',
  'setup.step': 'setup',
  'setup.card': 'setup',
  // A key field on the wizard's Image generation step: `{ id, field, capabilityLabel, okWhen }`.
  'setup.key': 'setup',
  // A row of the dataset workspace's Import & export section ("More ways
  // out"): `{ id, title, targetId, summary, when(context), panel }` — the core
  // reads the data for its rail and deep links, mounts the panel for the row.
  // Dataset-only by nature: a Bank has nothing captioned to export.
  'export.action': 'dataset',
  // The dense (full-model) lane lends two places to model tools: under the
  // recipe card, aimed at the model the run delivered (props `disabled`,
  // `target`, `suggestedPath`), and on each delivered full model's card
  // (`entry`, `busy`, `actions` — the core's verdict on what the entry allows).
  'dense.recipe.tool': 'dense',
  'dense.model.tool': 'dense',
  // The Datasets page's list of the other kinds of training set a plugin
  // brings (the video lane's video datasets), under the image datasets.
  'datasets.section': 'datasets',
  'capabilities.row': 'setup',
  // Data, not a component: an engine's catalog entry (src/engines/catalog.js
  // merges the enabled plugins' specs into the core's at each read).
  'engine.spec': 'catalog',
  'improve.editor': 'catalog',
  'improve.engine': 'catalog', // API 1.9: complete restoration choices on every shared image surface
})

// Stable category IDs carried by settings.group descriptors. Since API 1.12,
// all categories render in the owning plugin's Settings page; these IDs also
// preserve old Settings deep links and saved group preferences.
export const SETTINGS_GROUP_SECTIONS = Object.freeze(['engines', 'scraping', 'storage', 'training', 'local-tools'])

export const KNOWN_SLOTS = Object.freeze([
  ...Object.keys(PAIRED_SURFACES),
  ...Object.keys(SINGLE_SURFACE_SLOTS),
])

/** The surfaces a contribution to `slot` mounts on: the paired list, or the
 *  single surface, narrowed by an explicit `surfaces` on the item. */
export function surfacesOf(slot, item = {}) {
  const all = PAIRED_SURFACES[slot] || (SINGLE_SURFACE_SLOTS[slot] ? [SINGLE_SURFACE_SLOTS[slot]] : [])
  if (Array.isArray(item.surfaces) && item.surfaces.length) {
    return all.filter((s) => item.surfaces.includes(s))
  }
  return all
}

/** Parity verdict for one descriptor: every paired slot it contributes to
 *  must cover every surface of the pair, or carry a written skip. Returns the
 *  list of gaps (empty = parity kept). */
export function parityGaps(descriptor) {
  const gaps = []
  const skips = Array.isArray(descriptor.paritySkip) ? descriptor.paritySkip : []
  const slots = descriptor.slots || {}
  for (const [slot, surfaces] of Object.entries(PAIRED_SURFACES)) {
    const items = slots[slot]
    if (!Array.isArray(items) || !items.length) continue
    for (const item of items) {
      const covered = new Set(surfacesOf(slot, item))
      for (const surface of surfaces) {
        if (covered.has(surface)) continue
        const skip = skips.find((s) => s.slot === slot && s.surface === surface)
        if (skip && skip.reason) continue
        gaps.push({ plugin: descriptor.id, slot, item: item.id || '(unnamed)', surface })
      }
    }
  }
  return gaps
}
