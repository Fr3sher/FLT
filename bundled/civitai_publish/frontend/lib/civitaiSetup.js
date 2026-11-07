// 📤 What the plugin contributes to the Setup wizard: the counted capability
// row ("not ready, here is the field" — never a shorter list that certifies
// completeness by omission) and the key field on the "Image generation" step.
// Pure module: the core's `setup.step` slot calls `rows(caps)`, the `setup.key`
// slot reads the field and asks `okWhen(caps)`.

/** The one Civitai credential — the core's (the scraper and the 🌐 prompt
 *  browser read it too), tested by the core's key-test button. This plugin puts
 *  the field on the wizard because publishing is what a fresh install misses
 *  without it. */
export const CIVITAI_KEY_FIELD = {
  key: 'CIVITAI_API_KEY', label: 'Civitai API key (optional)', engine: 'civitai',
  testTarget: 'civitai',
  href: 'https://civitai.com/user/account',
  help: 'Publishes your checkpoints as Civitai model pages and posts generated '
    + 'images under them from the app; also reads the prompts in the 🌐 Civitai '
    + 'browser and unlocks adult results in Civitai scans. A free account has one.',
}

export const CIVITAI_ROW_LABEL = '📤 Civitai publishing'

export function civitaiReady(caps) {
  const c = caps || {}
  return !!(c.civitai && c.civitai.ok)
}

/** The counted capability row. Its door is the key itself (a core help topic). */
export function civitaiSetupRows(caps) {
  return [{
    label: CIVITAI_ROW_LABEL,
    what: 'Posts checkpoints and images to Civitai; also the 🌐 prompt browser (API key)',
    ok: civitaiReady(caps), topic: 'CIVITAI_API_KEY',
  }]
}
