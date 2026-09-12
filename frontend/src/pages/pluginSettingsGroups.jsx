import { useCallback, useEffect, useState } from 'react'
import { Puzzle } from 'lucide-react'
import { apiFetch } from '../api/fetchClient'
import { PluginPanel } from '../plugins/PluginSlot.jsx'
import { contributions } from '../plugins/registry.js'
import { SettingsGroup, useSettingsGroupProps } from '../components/settings/SettingsGroupsView'
import { InstallItem } from '../components/setup/InstallEverything'
import { cardInstalled } from '../components/setup/mlInstallCards'
import ImproveEnginePreference from '../components/settings/ImproveEnginePreference'
import PluginPreparation from './store/PluginPreparation.jsx'

function Group({ group, ...props }) {
  // Keep historical group ids and open preferences, including old deep links.
  const groupProps = useSettingsGroupProps(group.section)
  const view = { ...group, icon: typeof group.icon === 'function' ? group.icon : Puzzle,
    title: group.title || group.id.replaceAll('-', ' ') }
  return <SettingsGroup {...groupProps(view)}>
    <PluginPanel panelKey={`${group.plugin}:${group.id}:settings`} importer={group.panel} {...props} />
  </SettingsGroup>
}

export default function PluginSettingsGroups({ pluginId, groups, ...props }) {
  const [locations, setLocations] = useState([])
  const needsLocations = groups.some(group => group.section === 'storage')
  const loadLocations = useCallback(async () => {
    if (!needsLocations) return
    try {
      setLocations((await apiFetch('/api/storage/locations')).locations || [])
    } catch { /* Location editors still accept a configured folder. */ }
  }, [needsLocations])
  useEffect(() => { loadLocations() }, [loadLocations])
  const locationProps = key => ({
    ...props, current: locations.find(location => location.key === key)?.path,
    onChanged: loadLocations,
  })
  const preparation = contributions('setup.card', 'setup').filter(item => item.plugin === pluginId)
  const steps = contributions('setup.step', 'setup').filter(item => item.plugin === pluginId)
  const installs = new Map(steps.flatMap(step => typeof step.catalog === 'function'
    ? step.catalog(props.caps) || [] : []).map(item => [item.action, item]))
  for (const card of steps.flatMap(step => step.mlCards || [])) {
    if (!installs.has(card.action)) installs.set(card.action, {
      action: card.action, label: card.title, present: cardInstalled(card, props.caps), available: true,
    })
  }
  const onPrepared = () => props.refreshCaps?.(true)
  const improves = contributions('improve.engine').some(item => item.plugin === pluginId)
  const engines = contributions('engine.spec').filter(item => item.plugin === pluginId)
  return <div className="space-y-4">
    {engines.length > 0 && <fieldset className="rounded-lg border border-border p-4">
      <legend className="px-1 text-sm font-medium">Enabled engines</legend>
      <div className="flex flex-wrap gap-4">{engines.map(engine => <label key={engine.id} className="inline-flex min-h-10 items-center gap-2 text-sm">
        <input type="checkbox" checked={(props.config.engines?.enabled || []).includes(engine.id)}
          onChange={() => props.toggleEngine(engine.id)} />
        {engine.settingsLabel || engine.label}
      </label>)}</div>
    </fieldset>}
    {improves && <ImproveEnginePreference {...props} />}
    {groups.length === 0 && !improves && preparation.length === 0 && installs.size === 0 && <p className="text-sm text-content-muted">This plugin has no global settings. Its tools expose their options where you use them.</p>}
    {(preparation.length > 0 || installs.size > 0) && <details id="plugin-preparation" aria-label="Preparation" className="space-y-4 rounded-xl border border-border bg-surface p-4">
      <summary className="min-h-10 cursor-pointer text-base font-semibold">Preparation</summary>
      {installs.size > 0 && <PluginPreparation key={pluginId} pluginId={pluginId} items={[...installs.values()]} onPrepared={onPrepared} />}
      {preparation.filter(card => typeof card.panel === 'function').map(card =>
        <PluginPanel key={card.id} panelKey={`${card.plugin}:${card.id}:setup`} importer={card.panel}
          caps={props.caps} onDone={onPrepared} />)}
      {installs.size > 0 && <details className="rounded-xl border border-border bg-surface p-4">
        <summary className="min-h-10 cursor-pointer text-sm font-medium">Install or repair individual components</summary>
        <div className="mt-4 space-y-3">{[...installs.values()].map(item =>
          <InstallItem key={item.action} item={item} onDone={onPrepared} />)}</div>
      </details>}
    </details>}
    {groups.filter(group => typeof group.panel === 'function').map(group =>
      <Group key={`${group.section}:${group.id}`} group={group} {...props}
        locationProps={locationProps} onChanged={loadLocations} />)}
  </div>
}
