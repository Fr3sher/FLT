import { useEffect, useState } from 'react'
import { apiFetch, postJson } from '../../api/fetchClient'
import { StatusBadge } from '../settings/primitives'

/* The ChatGPT subscription (Codex OAuth) device-code login, as ONE component.
   It lives in common/ because two screens need it: Settings ▸ Image engines and
   the Setup wizard's image step. Setup used to offer only the pay-per-use API
   key, which read as "the ChatGPT engine costs money" on the very screen where a
   Plus/Pro subscriber decides what this app can do — while the subscription lane
   had shipped months earlier, three clicks away, on a page they had no reason to
   open yet.

   Device-code flow: the user opens the verification URL on ANY device, types the
   one-time code, and we poll the backend until it reports connected. */
export default function ChatgptSubscriptionConnect({ caps, refreshCaps, toast }) {
  const sub = (caps && caps.chatgpt_subscription) || {}
  const [device, setDevice] = useState(null)     // {verification_url, user_code}
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!device) return undefined
    const id = setInterval(async () => {
      try {
        const r = await apiFetch('/api/settings/chatgpt-oauth/poll', { background: true })
        if (r.status === 'connected') {
          setDevice(null)
          toast.success('ChatGPT subscription connected.')
          await refreshCaps(true)
        } else if (r.status === 'error') {
          setDevice(null)
          setError(r.detail || 'Login failed — try again.')
        }
      } catch { /* transient — keep polling */ }
    }, 3000)
    return () => clearInterval(id)
  }, [device, refreshCaps, toast])

  const run = async (fn, done) => {
    setBusy(true); setError(null)
    try {
      const r = await fn()
      if (done) { setDevice(null); done(r) } else { setDevice(r) }
      if (done) await refreshCaps(true)
    } catch (e) {
      setError(e.message || 'Request failed.')
    } finally {
      setBusy(false)
    }
  }

  const start = () => run(() => postJson('/api/settings/chatgpt-oauth/start', {}))
  const importCodex = () => run(
    () => postJson('/api/settings/chatgpt-oauth/import-codex', {}),
    () => toast.success('Codex CLI session imported.'))
  const disconnect = () => run(
    () => postJson('/api/settings/chatgpt-oauth/logout', {}),
    () => toast.success('ChatGPT subscription disconnected.'))

  const btn = 'rounded-md border border-border-strong px-3 py-1.5 text-xs font-medium ' +
    'text-content hover:bg-surface-raised disabled:opacity-50'

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <StatusBadge
          ok={!!sub.connected}
          okLabel={subscriptionLabel(sub)}
          missingLabel="Not connected"
        />
        <div className="flex flex-wrap gap-2">
          {!sub.connected && (
            <button type="button" onClick={start} disabled={busy || !!device} className={btn}>
              {device ? 'Waiting for you to enter the code…' : 'Connect ChatGPT subscription'}
            </button>
          )}
          {!sub.connected && sub.codex_cli_detected && (
            <button type="button" onClick={importCodex} disabled={busy || !!device} className={btn}>
              Import from Codex CLI
            </button>
          )}
          {sub.connected && (
            <button type="button" onClick={disconnect} disabled={busy} className={btn}>
              Disconnect
            </button>
          )}
        </div>
      </div>

      {device && (
        <div role="status" className="rounded-lg border border-primary/40 bg-primary/10 p-3 text-sm text-content">
          <p>1. Open <a href={device.verification_url} target="_blank" rel="noreferrer" className="font-medium underline">{device.verification_url}</a> on any device and sign in.</p>
          <p className="mt-1">2. Enter this one-time code (expires in 15 minutes):</p>
          <p className="mt-1 select-all font-mono text-lg font-semibold tracking-widest">{device.user_code}</p>
        </div>
      )}

      {error && <p className="text-xs text-rose-400"><span aria-hidden="true">✗</span> {error}</p>}
    </div>
  )
}

/* What a connected subscription is CALLED on screen. The plan is worth naming —
   the lane's limits (reference-image count, daily image cap) follow the plan, not
   the account — but neither field is guaranteed by the token, so each one only
   appears when the backend actually reported it. */
export function subscriptionLabel(sub) {
  const s = sub || {}
  const parts = [s.email, s.plan].filter((v) => typeof v === 'string' && v.trim())
  return parts.length ? `Connected — ${parts.join(' · ')}` : 'Connected'
}
