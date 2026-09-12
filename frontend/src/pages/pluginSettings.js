import { pluginActive, pluginDesired } from '../plugins/lifecycle.js'

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b)

// Settings are merged by the server. Send only changed leaves: a product may
// share a historical config section with another product or with the core.
export function settingsPatch(current = {}, saved = {}) {
  const patch = {}
  for (const [key, value] of Object.entries(current)) {
    if (same(value, saved?.[key])) continue
    patch[key] = object(value) && object(saved?.[key]) ? settingsPatch(value, saved[key]) : value
  }
  return patch
}

export function applySettingsPatch(config, patch) {
  const result = { ...config }
  for (const [key, value] of Object.entries(patch)) {
    result[key] = object(value) ? applySettingsPatch(result[key] || {}, value) : value
  }
  return result
}

function pendingAfterSave(pending, submitted) {
  const result = {}
  for (const [key, value] of Object.entries(pending)) {
    if (!Object.prototype.hasOwnProperty.call(submitted || {}, key)) result[key] = value
    else if (object(value) && object(submitted?.[key])) {
      const child = pendingAfterSave(value, submitted[key])
      if (Object.keys(child).length) result[key] = child
    }
  }
  return result
}

// Preserve unrelated drafts, including another key inside the same historical
// section, while accepting server normalization of the fields just saved.
export function reconcileSettings(current, saved, canonical, submitted, atSubmit = current) {
  const remaining = pendingAfterSave(settingsPatch(current, saved), submitted)
  return applySettingsPatch(applySettingsPatch(canonical, remaining), settingsPatch(current, atSubmit))
}

export function pluginSettingsPath(pluginId) {
  return `/plugins/${encodeURIComponent(pluginId)}/settings`
}

export function settingsApiUrl(pluginId, path = '/api/settings') {
  return pluginId ? `${path}?${new URLSearchParams({ plugin: pluginId })}` : path
}

export function pluginSettingsAvailability(plugin) {
  if (!plugin) return 'This plugin is not installed. Install it from the plugin store to access its settings.'
  if (plugin.pending_action) return 'Apply the pending plugin changes in My plugins, then reopen these settings.'
  if (!pluginDesired(plugin)) return 'Turn on this plugin in My plugins and apply the change to edit its settings. Its saved settings are kept.'
  if (!pluginActive(plugin)) return plugin.error || 'This plugin is not active. Check its status in My plugins, then apply the change or repair its installation.'
  return ''
}

// Old help URLs keep working from descriptor metadata. No product identifiers
// or field names belong in the host router. Ambiguous section-only URLs stay
// in general Settings, where their core settings still live.
export function legacyPluginSettingsTarget(section, focus, descriptors = [], activeIds = null) {
  if (!focus) return null
  const route = `/settings/${section}`
  const owners = descriptors.filter(({ descriptor }) =>
    (descriptor.help || []).some(topic => {
      const app = topic.app || {}
      return app.focus === focus && [app.route, app.legacyRoute, ...(app.legacyRoutes || [])]
        .some(value => typeof value === 'string' && value.split('?')[0] === route)
    }) || (descriptor.slots?.['settings.group'] || []).some(group =>
      group.section === section && `settings-group-${section}-${group.id}` === focus))
  if (owners.length === 1) return pluginSettingsPath(owners[0].descriptor.id)
  // Multiple products can expose an explicitly shared preference. A legacy
  // link may select any active owner of that same value, never an unrelated field.
  const sharedKeys = owners.map(({ descriptor }) => (descriptor.help || []).find(topic =>
    topic.app?.focus === focus && topic.app?.sharedSetting)?.app.sharedSetting)
  if (sharedKeys.length > 1 && sharedKeys[0] && sharedKeys.every(key => key === sharedKeys[0])) {
    const owner = owners.find(item => !activeIds || activeIds.includes(item.descriptor.id)) || owners[0]
    return pluginSettingsPath(owner.descriptor.id)
  }
  return null
}
