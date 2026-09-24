import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '../../api/fetchClient.js'
import { preparationState, preparationStatusUrl, startPreparation, watchPreparation } from './preparation.js'

export default function PluginPreparation({ pluginId, items, onPrepared }) {
  const [selected, setSelected] = useState(() => items.filter(item => item.available && !item.present).map(item => item.action))
  const [tracked, setTracked] = useState([])
  const [statuses, setStatuses] = useState({})
  const [phase, setPhase] = useState('idle')
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const done = useRef(onPrepared)
  done.current = onPrepared
  const allActions = items.map(item => item.action).join(',')

  useEffect(() => {
    const controller = new AbortController()
    const actions = allActions.split(',').filter(Boolean)
    if (actions.length) apiFetch(preparationStatusUrl(actions), { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return
      const active = actions.filter(action => ['queued', 'running'].includes(result.statuses?.[action]?.state))
      if (active.length) { setTracked(active); setStatuses(result.statuses || {}); setPhase('running') }
    }).catch(() => { /* No worker is started by visiting this page. */ })
    return () => controller.abort()
  }, [pluginId, allActions])

  useEffect(() => {
    if (phase !== 'running' || !tracked.length) return
    const controller = new AbortController()
    watchPreparation(tracked, { signal: controller.signal, onStatus: setStatuses }).then(state => {
      if (controller.signal.aborted) return
      setPhase(state)
      done.current?.()
    }).catch(problem => {
      if (!controller.signal.aborted) { setError(problem.message); setPhase('status-error') }
    })
    return () => controller.abort()
  }, [phase, tracked, attempt])

  const start = async () => {
    setError(''); setPhase('starting')
    try {
      const result = await startPreparation(pluginId, selected)
      setTracked(result.actions); setStatuses(result.statuses)
      const state = preparationState(result.actions, result.statuses)
      setPhase(state === 'prepared' || state === 'error' ? state : 'running')
      if (state === 'prepared' || state === 'error') done.current?.()
    } catch (problem) { setError(problem.message || 'Could not prepare this plugin.'); setPhase('idle') }
  }
  const busy = phase === 'running' || phase === 'starting'
  return <section aria-label="Prepare selected components" className="space-y-3 rounded-lg border border-border p-4">
    <h3 className="text-sm font-semibold">Prepare selected components</h3>
    <p className="text-sm text-content-muted">Choose the downloads and tools for this plugin. LDS checks the whole selection before starting. Existing files stay available for repair.</p>
    <div className="space-y-2">{items.map(item => <label key={item.action} className="flex min-h-10 items-start gap-2 text-sm">
      <input type="checkbox" className="mt-1" checked={selected.includes(item.action)} disabled={busy || !item.available}
        onChange={() => setSelected(current => current.includes(item.action) ? current.filter(action => action !== item.action) : [...current, item.action])} />
      <span>{item.label}{item.present ? ' — installed' : ''}{!item.available && item.hint && <span className="block text-xs text-content-muted">{item.hint}</span>}</span>
    </label>)}</div>
    {tracked.length > 0 && <ul aria-live="polite" className="space-y-1 text-sm">{tracked.map(action => <li key={action}>
      {items.find(item => item.action === action)?.label || action}: {statuses[action]?.state === 'success' ? 'prepared' : statuses[action]?.state || 'waiting for status'}
      {statuses[action]?.state === 'error' && <pre className="mt-1 max-h-36 overflow-auto whitespace-pre-wrap break-words text-xs text-danger">{statuses[action]?.error || statuses[action]?.log?.slice(-4000) || 'Preparation failed. Review the component and retry.'}</pre>}
    </li>)}</ul>}
    {phase === 'prepared' && <p role="status" className="text-sm text-content-muted">The selected components are prepared. Re-check the plugin below; custom nodes may require a ComfyUI restart before they become available.</p>}
    {phase === 'error' && <p role="alert" className="text-sm text-danger">Some components need attention. Select them to retry, or repair them individually below.</p>}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    {phase === 'status-error' ? <button type="button" className="min-h-10 rounded-md border border-border px-3 text-sm"
      onClick={() => { setError(''); setAttempt(value => value + 1); setPhase('running') }}>Retry status</button>
      : <button type="button" onClick={start} disabled={busy || !selected.length}
        className="min-h-10 rounded-md bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50">{busy ? 'Preparing…' : `Prepare selection (${selected.length})`}</button>}
  </section>
}
