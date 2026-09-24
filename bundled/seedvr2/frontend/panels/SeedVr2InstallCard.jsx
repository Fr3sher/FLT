import { useEffect, useRef, useState } from 'react'
import { apiFetch, postJson, useToast, HelpBadge } from '@lds/plugin-sdk'
import {
  INSTALL_ALL_ACTION_LABELS, SEEDVR2_ACTIONS, seedvr2InstallPlan, seedvr2NeedsComfyuiRestart,
  seedvr2PreparationPlan, seedvr2PreparationState, seedvr2PreparationError,
} from '../lib/setup.js'
import { ceilingLine, tilingStatus, TTP_PACK, TTP_URL } from '../lib/seedvr2Tiling.js'
import { fmtSize } from '@lds/plugin-sdk/setup'

const POLL_MS = 1200
const MAX_POLL_FAILURES = 5
const PACK_URL = 'https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler'
const WEIGHTS_URL = 'https://huggingface.co/numz/SeedVR2_comfyUI'
const PROJECT_URL = 'https://github.com/ByteDance-Seed/SeedVR'
const STATUS_WORDS = { idle: 'waiting', queued: 'queued', running: 'preparing…', success: 'prepared', error: 'needs attention' }

export default function SeedVr2InstallCard({ caps, onDone }) {
  const toast = useToast()
  const [phase, setPhase] = useState('idle')
  const [tracked, setTracked] = useState([])
  const [statuses, setStatuses] = useState({})
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)
  const timer = useRef(null)
  const mounted = useRef(true)
  const generation = useRef(0)
  const starting = useRef(false)
  const cu = caps?.comfyui || {}
  const plan = seedvr2InstallPlan(caps)
  const ready = cu.seedvr2_ready === true
  const needsRestart = seedvr2NeedsComfyuiRestart(caps)
  const running = phase === 'running'
  const rows = ready && !running ? [] : phase === 'idle' ? plan : tracked
  const doneCount = rows.filter(action => statuses[action]?.state === 'success').length
  const tiling = tilingStatus(caps)
  const ceiling = ceilingLine(caps)
  const current = token => mounted.current && generation.current === token

  const settle = (actions, st) => {
    setStatuses(st)
    const state = seedvr2PreparationState(actions, st)
    if (state === 'running') return false
    clearTimeout(timer.current)
    if (state === 'prepared') {
      setPhase('prepared')
      onDone?.()
    } else {
      setPhase('error')
      setError(state === 'error' ? seedvr2PreparationError(actions, st)
        : 'Progress is unavailable. Re-check the connection before trying again.')
    }
    return true
  }

  const poll = async (actions, token, failures = 0) => {
    try {
      const reply = await apiFetch(`/api/setup/install-all/status?actions=${encodeURIComponent(actions.join(','))}`)
      if (!current(token)) return
      if (!settle(actions, reply.statuses || {})) timer.current = setTimeout(() => poll(actions, token), POLL_MS)
    } catch {
      if (!current(token)) return
      if (failures + 1 >= MAX_POLL_FAILURES) {
        setPhase('error')
        setError('Progress could not be reached. Preparation may still be running. Re-check the connection before trying again.')
      } else timer.current = setTimeout(() => poll(actions, token, failures + 1), POLL_MS)
    }
  }

  useEffect(() => {
    mounted.current = true
    const token = generation.current
    apiFetch(`/api/setup/install-all/status?actions=${encodeURIComponent(SEEDVR2_ACTIONS.join(','))}`).then(reply => {
      if (!current(token)) return
      const st = reply.statuses || {}
      // Reattach only to work the backend reports in flight, not stale probes.
      const active = SEEDVR2_ACTIONS.filter(action => ['running', 'queued'].includes(st[action]?.state))
      if (active.length) {
        setTracked(active); setStatuses(st); setPhase('running')
        poll(active, token)
      }
    }).catch(() => { /* Reading status does not authorize an installation. */ })
    return () => { mounted.current = false; generation.current += 1; clearTimeout(timer.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const start = async () => {
    if (starting.current) return
    starting.current = true
    clearTimeout(timer.current)
    const token = ++generation.current
    setPhase('running'); setError(''); setStatuses({}); setTracked([])
    try {
      const reply = await postJson('/api/setup/install-group/seedvr2', {})
      if (!current(token)) return
      const actions = seedvr2PreparationPlan(reply.plan)
      setTracked(actions)
      if (!settle(actions, reply.statuses || {})) poll(actions, token)
    } catch (failure) {
      if (!current(token)) return
      const message = failure.message || 'Could not start SeedVR2 preparation.'
      setPhase('error'); setError(message); toast.error(message)
    } finally { starting.current = false }
  }

  const recheck = async () => {
    setChecking(true)
    try { await onDone?.() } catch (failure) { toast.error(failure.message || 'Could not re-check ComfyUI.') }
    finally { if (mounted.current) setChecking(false) }
  }

  return (
    <section className="rounded-xl border border-border bg-surface p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-content">
          SeedVR2 — fidelity upscaler <HelpBadge topic="setup-seedvr2-install" className="ml-2" />
        </h3>
        {running && <span className="text-xs tabular-nums text-content-muted">Preparing {doneCount} / {rows.length || '…'}</span>}
      </div>
      <p className="mt-1 text-sm text-content-muted">
        Restore detail at a higher resolution while preserving the image’s look.
        Prepare the node pack, its dependencies and two model files (~3.9 GB) together.
        Compatible files already present are reused. No other LDS plugin is required.
      </p>
      <p className="mt-2 text-xs text-content-subtle">
        <a href={PACK_URL} target="_blank" rel="noreferrer" className="text-sky-300 underline hover:text-sky-200">Node pack →</a>
        {' · '}
        <a href={WEIGHTS_URL} target="_blank" rel="noreferrer" className="text-sky-300 underline hover:text-sky-200">Model weights →</a>
        {' · '}
        <a href={PROJECT_URL} target="_blank" rel="noreferrer" className="text-sky-300 underline hover:text-sky-200">SeedVR2 by ByteDance-Seed →</a>
        {' — Apache-2.0. Dependencies retain their own licences.'}
      </p>

      {!cu.dir_valid ? <p className="mt-3 text-sm text-content-muted">Choose a supported local ComfyUI installation in Local tools first.</p> : (
        <>
          {ready && !running ? <p className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-content">
            ✓ SeedVR2 is ready — ComfyUI reports the required nodes and models.
          </p> : !running && (needsRestart || phase === 'prepared' || plan.length === 0) && (
            <p className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-content">
              {phase === 'prepared' ? (plan.some(action => !tracked.includes(action))
                ? 'Selected steps prepared. Other components still need preparation. ' : 'Files prepared. ') : ''}
              {needsRestart || tracked.includes('seedvr2_nodes')
                ? 'Restart ComfyUI, then re-check. The node pack is on disk but its required classes have not been confirmed.'
                : 'Start ComfyUI and re-check. Its required nodes and models must be confirmed before SeedVR2 is ready.'}
            </p>
          )}
          {error && !ready && <p role="alert" className="mt-3 whitespace-pre-wrap break-words rounded-md border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-content">{error}</p>}
          {rows.length > 0 && (
            <ul className="mt-3 space-y-2" aria-label="SeedVR2 preparation steps">
              {rows.map(action => {
                const status = statuses[action] || {}
                const state = status.state || 'idle'
                const progress = status.progress
                return <li key={action} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-sm text-content-muted">
                  <span>{INSTALL_ALL_ACTION_LABELS[action]}</span>
                  <span className={`text-xs tabular-nums ${state === 'error' ? 'text-rose-300' : 'text-content-subtle'}`}>
                    {state === 'running' && progress?.total
                      ? `${progress.pct != null ? `${progress.pct}% · ` : ''}${fmtSize(progress.done)} / ${fmtSize(progress.total)}`
                      : STATUS_WORDS[state] || 'unknown'}
                  </span>
                </li>
              })}
            </ul>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {(running || (!ready && plan.length > 0)) && <button type="button" onClick={start} disabled={running}
              className="w-full rounded-lg border border-primary/50 bg-primary/10 px-4 py-2 text-sm font-semibold text-primary disabled:opacity-50 sm:w-auto">
              {running ? 'Preparing SeedVR2…' : 'Prepare SeedVR2'}
            </button>}
            {!running && <button type="button" onClick={recheck} disabled={checking}
              className="rounded-lg border border-border px-4 py-2 text-sm text-content-muted disabled:opacity-50">
              {checking ? 'Checking…' : 'Re-check ComfyUI'}
            </button>}
          </div>
          {!ready && !running && <p className="mt-2 text-xs text-content-subtle">
            Preparation does not restart ComfyUI. Finish any work there before restarting it.
          </p>}
        </>
      )}

      <details className="mt-4 rounded-md border border-border px-3 py-2 text-sm text-content">
        <summary className="cursor-pointer font-medium">Advanced: optional high-resolution tiling</summary>
        {ceiling && <p className="mt-2 text-content-muted">{ceiling}</p>}
        <p className="mt-2 text-content-muted">{tiling.text}</p>
        <p className="mt-2 text-xs text-content-subtle">
          <a href={TTP_URL} target="_blank" rel="noreferrer" className="text-sky-300 underline hover:text-sky-200">{TTP_PACK} →</a>
          {' — MIT. Tiling workflow contributed by SurpassHR (GitHub #32). This optional pack is not included in Prepare SeedVR2.'}
        </p>
      </details>
    </section>
  )
}
