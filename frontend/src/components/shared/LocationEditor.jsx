import { useEffect, useState } from 'react'
import { apiFetch, postJson } from '../../api/fetchClient.js'
import { Card, INPUT_CLASS } from '../settings/primitives.jsx'
import ResetToDefault from '../settings/ResetToDefault.jsx'
import { moveLabel, movePercent, relocationChoices } from '../settings/storageLocations.js'
import { waitForStorageMove } from './storageMoveCompletion.js'

export function LocationEditor({
  id, storageKey, label, help, section, field, current, sizeBytes,
  config, setField, configDefaults, saveConfigPatch, toast, onChanged,
}) {
  const stored = (config[section] || {})[field] || ''
  const [draft, setDraft] = useState(stored)
  const [check, setCheck] = useState(null)
  const [checking, setChecking] = useState(false)
  const [job, setJob] = useState(null)

  useEffect(() => { setDraft(stored) }, [stored])

  const validate = async () => {
    setChecking(true)
    try {
      setCheck(await postJson('/api/storage/validate', { key: storageKey, path: draft }))
    } catch (e) {
      setCheck({ ok: false, reason: e.message || 'Could not check that folder.' })
    } finally {
      setChecking(false)
    }
  }

  const persist = async (value) => {
    // Saved through the explicit patch, not setField + a section save: the state
    // update is not visible to this callback, so that version saved nothing at
    // all while reporting success (caught headless before it shipped).
    await saveConfigPatch(section, { [field]: value })
    onChanged?.()
  }

  const adopt = async () => {
    try {
      await persist(check?.default ? '' : (check?.path || draft))
      toast?.success(check?.default ? 'Back to the default folder.' : 'New folder in use.')
      setCheck(null)
    } catch (e) {
      toast?.error(e.message || 'Could not save the new location.')
    }
  }

  const move = async () => {
    let started
    try {
      started = await postJson('/api/storage/move', { key: storageKey, path: check.path })
    } catch (e) {
      toast?.error(e.message || 'Could not start the move.')
      return
    }
    setJob({ phase: 'scanning' })
    try {
      await waitForStorageMove(async () =>
        (await apiFetch(`/api/storage/move/progress?job_id=${encodeURIComponent(started.job_id)}`,
          { background: true })).job, setJob)
    } catch (error) {
      setJob({ phase: 'unknown' })
      toast?.error(error.message)
      return
    }
    // The config only points at the new folder once every byte is there.
    try {
      await persist(check.path)
      toast?.success('Files moved and the new folder is in use.')
      setCheck(null)
    } catch (e) {
      toast?.error(e.message || 'Files moved, but the location could not be saved.')
    }
  }

  const choices = relocationChoices({ validation: check, currentSize: sizeBytes })
  const busy = job && ['scanning', 'copying', 'unknown'].includes(job.phase)
  return (
    <Card title={label} help={help}>
      <p className="break-all text-xs text-content-subtle">
        <span className="text-content-muted">In use now:</span> {current || '—'}
      </p>
      <div>
        <label htmlFor={id} className="block text-sm font-medium text-content">
          Folder (leave empty for the default)
        </label>
        {/* Column on a phone: a path field and two buttons never share 400 px. */}
        <div className="mt-1 flex flex-col gap-2 sm:flex-row">
          <input id={id} type="text" value={draft} disabled={busy}
            onChange={(e) => { setDraft(e.target.value); setCheck(null) }}
            placeholder="Defaults to the app’s data folder"
            className={`${INPUT_CLASS} sm:flex-1`} />
          <button type="button" onClick={validate} disabled={checking || busy}
            className="shrink-0 rounded-md border border-border-strong px-3 py-1.5 text-sm font-medium text-content hover:bg-surface-raised disabled:opacity-50">
            {checking ? 'Checking…' : 'Check folder'}
          </button>
        </div>
        <div className="mt-1">
          <ResetToDefault label={label} section={section} field={field}
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
      </div>

      {check && !check.ok && (
        <p className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-2 text-xs text-rose-200">
          <span aria-hidden>⚠</span> {check.reason}
        </p>
      )}

      {choices.length > 0 && !busy && (
        <div className="space-y-2 rounded-lg border border-border bg-surface-raised p-3">
          <p className="text-xs text-content-muted">
            {check.default
              ? 'This goes back to the folder inside the app’s data directory.'
              : `${check.path} is writable${check.empty === false ? ' and already has files in it' : ''}.`}
          </p>
          {choices.map((choice) => (
            <div key={choice.id} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
              <p className="min-w-0 text-xs text-content-subtle">{choice.detail}</p>
              <button type="button" disabled={choice.disabled}
                onClick={() => (choice.id === 'move' ? move() : adopt())}
                className="shrink-0 self-start rounded-md border border-border-strong px-3 py-1.5 text-xs font-medium text-content hover:bg-surface-raised disabled:opacity-40">
                {choice.label}
              </button>
            </div>
          ))}
        </div>
      )}

      {job && (
        <div className="space-y-1" role="status" aria-live="polite">
          <p className="text-xs text-content-muted">{job.phase === 'unknown'
            ? 'Move status is unknown. The folder was not changed; reload to check before starting another move.'
            : moveLabel(job)}</p>
          {busy && (
            <div className="h-1.5 w-full max-w-sm overflow-hidden rounded-full bg-surface-raised">
              <div className="h-full rounded-full bg-gradient-primary transition-[width] duration-300"
                style={{ width: `${movePercent(job) ?? 15}%` }} />
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
