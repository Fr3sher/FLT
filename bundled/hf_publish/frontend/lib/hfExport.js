// The one row this plugin adds to the dataset workspace's Import & export
// section — as DATA the core's navigation reads (the rail entry, the deep link
// `?section=export&panel=hugging-face`, the "More ways out" summary) and the
// panel that draws it. Both read the same predicate, so the rail never offers
// a row the section does not show.
export const HF_EXPORT_ROW = Object.freeze({
  id: 'hugging-face',
  title: 'Publish to Hugging Face',
  targetId: 'ds-export-hugging-face',
  summary: 'Hugging Face',
})

/** The active plugin keeps its preparation visible in the dataset workspace.
 *  Token/image readiness changes the row's action, not its discoverability.
 *  The registry itself removes this contribution when the plugin is off. */
export function hfExportAvailable(context) {
  return context != null
}
