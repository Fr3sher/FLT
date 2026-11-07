import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { apiFetch } from '../api/fetchClient'
import { contributions } from '../plugins/registry.js'
import { pluginSettingsAvailability } from './pluginSettings.js'
import SettingsPage from './SettingsPage'

export default function PluginSettingsPage() {
  const { pluginId } = useParams()
  const [result, setResult] = useState(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let alive = true
    apiFetch('/api/plugins/', { cache: 'no-store' }).then(data => {
      if (alive) setResult({ pluginId, plugin: data.plugins?.find(plugin => plugin.id === pluginId),
        stale: Boolean(data.boot_id && window.lds?.bootId && data.boot_id !== window.lds.bootId) })
    }).catch(error => {
      if (alive) setResult({ pluginId, error: error.message || 'Could not read the plugin status.' })
    })
    return () => { alive = false }
  }, [pluginId, attempt])
  if (result?.pluginId !== pluginId) return <p role="status">Loading plugin settings…</p>
  const loadProblem = window.lds?.loadProblems?.find(item => item.plugin === pluginId)
  const reason = result.error || (result.stale && 'LDS has restarted. Reload this page to use its current plugins.')
    || pluginSettingsAvailability(result.plugin)
    || (loadProblem && 'This plugin’s interface did not load. Reload the page, or repair the plugin from Plugins.')
  if (reason) return <div className="space-y-4" data-plugin-settings-unavailable={pluginId}>
    <Link to="/plugins?tab=installed" className="inline-flex min-h-10 items-center text-sm text-primary hover:underline">← Plugins</Link>
    <h1 className="text-xl font-semibold">{result.plugin?.name || 'Plugin settings'}</h1>
    <p role={result.error ? 'alert' : 'status'} className="text-sm text-content-muted">{reason}</p>
    {result.error && <button type="button" onClick={() => setAttempt(value => value + 1)}
      className="min-h-10 rounded-md border border-border px-3 py-2 text-sm">Retry</button>}
    {(result.stale || loadProblem) && <button type="button" onClick={() => window.location.reload()}
      className="min-h-10 rounded-md border border-border px-3 py-2 text-sm">Reload page</button>}
  </div>
  const groups = contributions('settings.group', 'settings').filter(group => group.plugin === pluginId)
  return <SettingsPage key={pluginId} plugin={result.plugin} groups={groups} />
}
