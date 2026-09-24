import { useEffect, useState } from 'react'
import { apiFetch } from '@lds/plugin-sdk'
import { INPUT_CLASS } from '@lds/plugin-sdk/ui'

export default function ChatgptSubscriptionModels({ caps, config, setField }) {
  const sub = caps?.chatgpt_subscription || {}
  const [catalog, setCatalog] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const saved = (config.engines.chatgpt_subscription_model || '').trim()
  const selected = ['', 'auto', 'gpt-5.4-mini'].includes(saved) ? '' : saved

  useEffect(() => {
    let active = true
    setCatalog(null)
    setError('')
    setBusy(Boolean(sub.connected))
    if (sub.connected) {
      apiFetch(`/api/settings/chatgpt-oauth/models${refresh ? '?refresh=1' : ''}`, { background: true })
        .then((data) => { if (active) setCatalog(data) })
        .catch((err) => { if (active) setError(err.message || 'Could not load your ChatGPT models.') })
        .finally(() => { if (active) setBusy(false) })
    }
    return () => { active = false }
  }, [sub.connected, sub.email, refresh])

  const models = catalog?.models || []
  const choice = models.find((model) => model.id === (selected || catalog?.recommended))
  const missing = selected && !models.some((model) => model.id === selected)
  return (
    <div>
      <label htmlFor="chatgpt-subscription-model" className="block text-sm font-medium text-content">
        ChatGPT model — subscription
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <select id="chatgpt-subscription-model" className={`${INPUT_CLASS} min-w-0 flex-1`}
          value={selected} disabled={!sub.connected || busy}
          onChange={(event) => setField('engines', 'chatgpt_subscription_model', event.target.value)}>
          <option value="">Automatic — recommended for your account{catalog?.recommended ? ` (${catalog.recommended})` : ''}</option>
          {missing && <option value={selected}>{selected}{catalog ? ' — not in the current list' : ' — saved choice'}</option>}
          {models.map((model) => <option key={model.id} value={model.id}>{model.name} ({model.id})</option>)}
        </select>
        <button type="button" disabled={!sub.connected || busy} onClick={() => setRefresh((value) => value + 1)}
          className="rounded-md border border-border-strong px-3 py-1.5 text-xs text-content hover:bg-surface-raised disabled:opacity-50">
          {busy ? 'Loading…' : 'Refresh models'}
        </button>
      </div>
      {!sub.connected && <p className="mt-1 text-xs text-content-muted">Connect your ChatGPT account to list its available models.</p>}
      {error && <p role="alert" className="mt-1 text-xs text-danger">{error}</p>}
      {choice?.description && <p className="mt-1 text-xs text-content-muted">{choice.description}</p>}
      {missing && catalog && <p className="mt-1 text-xs text-warning">Your saved model is no longer listed. Choose an available model or Automatic.</p>}
      <p className="mt-2 text-xs text-content-muted">
        Automatic follows the first model recommended by OpenAI for your account as the list changes.
        A manual choice stays selected across updates. This model handles your request and reference photos;
        the GPT Image version that draws the result is selected by OpenAI for your subscription and cannot be chosen here.
        The API-key image model setting above does not apply to subscription generation.
      </p>
    </div>
  )
}
