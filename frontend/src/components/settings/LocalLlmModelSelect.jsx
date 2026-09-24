import { useEffect, useState } from 'react'
import { postJson } from '../../api/fetchClient'
import { INPUT_CLASS } from './primitives'

export default function LocalLlmModelSelect({ id, label, provider, url, value, onChange, refreshKey }) {
  const [revision, setRevision] = useState(0)
  const [state, setState] = useState({ query: '', models: [], phase: 'loading' })
  const server = provider === 'lmstudio' ? 'LM Studio' : 'Ollama'
  const query = new URLSearchParams({ provider, url: (url || '').trim() }).toString()

  useEffect(() => {
    let alive = true
    const controller = new AbortController()
    setState({ query, models: [], phase: 'loading' })
    // URL edits query the draft without saving it. A late reply from the old
    // server must never supply choices for the new address.
    const timer = setTimeout(async () => {
      try {
        const result = await postJson('/api/local-llm/models', Object.fromEntries(new URLSearchParams(query)), {
          background: true, signal: controller.signal,
        })
        if (!alive) return
        const models = [...new Set((result.models || []).filter(m => typeof m === 'string' && m.trim()))]
        setState({ query, models, phase: result.reachable ? 'ready' : 'error' })
      } catch (error) {
        if (alive) setState({ query, models: [], phase: 'error', error: error.message })
      }
    }, 300)
    return () => { alive = false; clearTimeout(timer); controller.abort() }
  }, [query, revision, refreshKey])

  const current = value || ''
  const phase = state.query === query ? state.phase : 'loading'
  const models = state.query === query ? state.models : []
  const missing = current && !models.includes(current)
  const loading = phase === 'loading'
  const hintId = `${id}-hint`
  return (
    <div className="min-w-0">
      <label htmlFor={id} className="block text-sm font-medium text-content">{label}</label>
      <div className="flex flex-wrap items-center gap-2">
        <select id={id} value={current} onChange={event => onChange(event.target.value)}
          disabled={loading} aria-busy={loading} aria-describedby={hintId}
          className={`${INPUT_CLASS} min-w-0 flex-1`}>
          <option value="" disabled={provider !== 'lmstudio'}>
            {provider === 'lmstudio' ? 'Automatic — let LDS choose'
              : loading ? 'Loading models…' : 'Select an installed model'}
          </option>
          {missing && <option value={current}>{current}{phase === 'ready' ? ' — not detected' : ''}</option>}
          {models.map(model => <option key={model} value={model}>{model}</option>)}
        </select>
        <button type="button" disabled={loading} onClick={() => setRevision(n => n + 1)}
          aria-label={`Refresh ${server} models`}
          className="mt-1 min-h-10 rounded-md border border-border-strong px-3 py-2 text-xs font-medium text-content hover:bg-surface-raised disabled:opacity-50">
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      <div id={hintId} className="mt-1 space-y-1 text-xs text-content-muted" aria-live="polite">
        <p>Models detected at the URL above. Choose a model that supports images for vision tasks. Save to apply your selection.</p>
        {phase === 'error' && <p className="text-amber-300">
          {state.error || `${server} is not answering. Check the URL and start its server, then refresh.`}
          {provider === 'lmstudio' && ' If authentication is enabled, save its API key first.'}
          {' Your selection is kept.'}
        </p>}
        {phase === 'ready' && models.length === 0 && <p>
          No models detected. {provider === 'ollama' ? 'Pull a model in Ollama or from Setup' : 'Download a model in LM Studio or below'}, then refresh.
        </p>}
        {phase === 'ready' && missing && <p className="text-amber-300">
          The selected model is not in this server’s list. It is kept until you choose another.
        </p>}
      </div>
    </div>
  )
}
