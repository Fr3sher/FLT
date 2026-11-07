import { apiFetch, putJson } from '@lds/plugin-sdk'

const OWN_URL = '/api/settings?plugin=image_upscale'
const CORE_URL = '/api/settings'
const OWN_KEYS = {
  identity_prompts: ['klein_improve', 'klein_improve_enabled'],
  klein: ['improve_consistency_strength', 'improve_character_lora_strength', 'improve_steps',
    'improve_base_lora_strength', 'improve_megapixels', 'improve_lora_preset'],
}
const SHARED_KEYS = { klein: ['unet', 'generation_lora_presets'] }

function mergeConfig(core = {}, own = {}) {
  const out = { ...core }
  for (const [section, values] of Object.entries(own)) out[section] = { ...(core[section] || {}), ...values }
  return out
}

/** Keep the shared model/preset library in the core, and the Improve dials in this product. */
export async function readImproveSettings() {
  const [core, own] = await Promise.all([
    apiFetch(CORE_URL, { background: true }), apiFetch(OWN_URL, { background: true }),
  ])
  return { ...core, ...own, config: mergeConfig(core.config, own.config),
    config_defaults: mergeConfig(core.config_defaults, own.config_defaults) }
}

export async function saveImproveSettings(body) {
  const own = {}, shared = {}
  if (!body?.config || Object.keys(body).some(key => key !== 'config')) throw new Error('Invalid Improve settings change.')
  // Reject unknown fields before either write. The server retains its independent scope checks.
  for (const [section, values] of Object.entries(body.config)) {
    if (!values || typeof values !== 'object' || Array.isArray(values)) throw new Error('Invalid Improve settings section.')
    for (const [key, value] of Object.entries(values)) {
      const target = OWN_KEYS[section]?.includes(key) ? own : SHARED_KEYS[section]?.includes(key) ? shared : null
      if (!target) throw new Error('This setting is outside Klein Improve and its shared model library.')
      ;(target[section] ||= {})[key] = value
    }
  }
  const hasOwn = Object.keys(own).length > 0
  if (hasOwn) await putJson(OWN_URL, { config: own })
  if (Object.keys(shared).length) {
    try { await putJson(CORE_URL, { config: shared }) }
    catch (error) {
      if (hasOwn) throw new Error(`Improve settings were saved, but the shared model or presets were not saved: ${error.message}`)
      throw error
    }
  }
  try { return await readImproveSettings() }
  catch (error) { throw new Error(`Settings were saved, but their updated values could not be read: ${error.message}`) }
}
