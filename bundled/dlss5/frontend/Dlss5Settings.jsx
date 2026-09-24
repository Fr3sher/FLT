import { useCallback, useEffect, useState } from 'react'
import { apiFetch, postJson, useToast } from '@lds/plugin-sdk'
import { InstallRunner } from '@lds/plugin-sdk/ui'
import Dlss5InstallCard from './Dlss5InstallCard.jsx'

export default function Dlss5Settings() {
  const [facts, setFacts] = useState(null)
  const [python, setPython] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const refresh = useCallback(async () => {
    try {
      const [status, settings] = await Promise.all([
        apiFetch('/api/dlss5/status'), apiFetch('/api/dlss5/settings'),
      ])
      setFacts(status); setPython(settings.python || ''); setError('')
    } catch (err) { setError(err.message || 'Could not read DLSS preparation.') }
  }, [])
  useEffect(() => { refresh() }, [refresh])
  const save = async () => {
    setBusy(true)
    try { await postJson('/api/dlss5/settings', { python }); await refresh(); toast.success('DLSS settings saved.') }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const environment = facts?.environment
  return <div className="space-y-4">
    {error && <p role="alert" className="text-sm text-red-400">{error}</p>}
    <section className="rounded-xl border border-border bg-surface p-5">
      <h2 className="text-base font-semibold text-content">1. Prepare the DLSS engine</h2>
      <p className="mt-2 text-sm text-content-muted">A dedicated Python environment contains NumPy and the video encoder. Video lane, ComfyUI and other plugins are not required.</p>
      {environment?.action && <div className="mt-3"><InstallRunner action={environment.action}
        buttonLabel={environment.ready ? 'Repair DLSS engine' : 'Install DLSS engine'} onDone={refresh} /></div>}
      {environment?.reason && <p className="mt-2 text-sm text-content-muted">{environment.reason}</p>}
      <details className="mt-4">
        <summary className="cursor-pointer text-sm text-content-muted">Advanced: use an existing Python environment</summary>
        <label className="mt-3 block text-sm text-content">Python executable
          <input value={python} onChange={event => setPython(event.target.value)} placeholder="Use the managed DLSS engine"
            className="mt-1 min-h-10 w-full rounded-md border border-border bg-surface-raised px-3 text-content" />
        </label>
        <p className="mt-2 text-xs text-content-muted">Optional. This environment must contain NumPy and imageio-ffmpeg. Clear the field to use the managed engine. Your former Video interpreter choice is preserved once, and can then be changed independently.</p>
        <button type="button" disabled={busy || !facts} onClick={save}
          className="mt-3 min-h-10 rounded-md border border-border px-3 text-sm text-content disabled:opacity-50">Save DLSS settings</button>
      </details>
    </section>
    <Dlss5InstallCard caps={{ dlss5nr: facts?.status }} onDone={refresh} />
    <button type="button" onClick={refresh} className="min-h-10 rounded-md border border-border px-3 text-sm text-content">Check preparation again</button>
  </div>
}
