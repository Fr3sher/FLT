import { contributions } from '../../plugins/registry.js'
import { PluginPanel } from '../../plugins/PluginSlot.jsx'

function editor() { return contributions('improve.editor').find(item => item.id === 'klein') }
let pending = Promise.resolve()
function invoke(name, ...args) {
  const item = editor()
  if (!item) return Promise.resolve()
  pending = pending.catch(() => {}).then(() => item.panel()).then(module => module[name]?.(...args))
  return pending
}
export function flushImproveSettings() { return invoke('flushImproveSettings') }
export function whenImproveSettingsSettled() { return invoke('whenImproveSettingsSettled') }
export function readImproveSettings() {
  return editor() ? invoke('readImproveSettings') : Promise.reject(new Error('Enable Klein Improve before reading its settings.'))
}
export function saveImproveSettings(body) {
  return editor() ? invoke('saveImproveSettings', body) : Promise.reject(new Error('Enable Klein Improve before saving its settings.'))
}
export function publishSettings(payload) { return invoke('publishSettings', payload) }
export default function KleinImproveNote(props) {
  const item = editor()
  return item ? <PluginPanel panelKey={`${item.plugin}:${item.id}:editor`} importer={item.panel} {...props} /> : null
}
