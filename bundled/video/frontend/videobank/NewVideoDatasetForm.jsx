import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { apiFetch, postJson, HelpBadge } from '@lds/plugin-sdk'
import { defaultFrames, frameOptions, sizeOptions, targetWarnings } from './videoTargetChoice.js'

export default function NewVideoDatasetForm() {
  const navigate = useNavigate()
  const [targets, setTargets] = useState([])
  const [targetKey, setTargetKey] = useState('')
  const [frames, setFrames] = useState('')
  const [sizeKey, setSizeKey] = useState('source')
  const [name, setName] = useState('')
  const [trigger, setTrigger] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let alive = true
    apiFetch('/api/video/targets').then((data) => {
      if (!alive) return
      const choices = (data.targets || []).filter((t) => t.fps && t.frame_default > 1)
      setTargets(choices)
      const first = choices.find((t) => t.training_verified) || choices[0]
      if (first) { setTargetKey(first.key); setFrames(defaultFrames(first)) }
    }).catch((e) => { if (alive) setError(e.message) })
    return () => { alive = false }
  }, [])
  const target = targets.find((t) => t.key === targetKey)
  const sizes = sizeOptions(target)
  const create = async (event) => {
    event.preventDefault()
    if (busy || !name.trim() || !target) return
    setBusy(true); setError('')
    try {
      const size = sizes.find((s) => s.key === sizeKey)
      const result = await postJson('/api/video-datasets', { name: name.trim(),
        trigger_word: trigger.trim(), target_profile: targetKey, frames: Number(frames),
        size: size?.width ? [size.width, size.height] : null })
      navigate(`/video-dataset/${result.id}?section=import`)
    } catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }
  const field = 'min-h-10 min-w-0 rounded border border-border bg-app/60 px-2 py-1.5 text-sm text-content'
  return (
    <form onSubmit={create} className="flex flex-col gap-3">
      <p className="text-xs text-content-muted">Create the set, then add video files or import videos from the web.<HelpBadge topic="video-dataset-import" /></p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Dataset name
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} className={field} />
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Trigger word (optional)
          <input maxLength={100} value={trigger} onChange={(e) => setTrigger(e.target.value)} className={field} />
        </label>
      </div>
      <label className="flex flex-col gap-1 text-xs text-content-muted">Target model
        <select aria-label="Target model" value={targetKey} disabled={busy} className={field} onChange={(e) => {
          setTargetKey(e.target.value); setFrames(defaultFrames(targets.find((t) => t.key === e.target.value))); setSizeKey('source')
        }}>
          {!targets.length && <option value="">Loading targets…</option>}
          {targets.map((t) => <option key={t.key} value={t.key}>{t.label}{t.training_verified ? '' : ' — training not verified'}</option>)}
        </select>
      </label>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Clip length
          <select aria-label="Clip length" value={frames} onChange={(e) => setFrames(e.target.value)} className={field}>
            {frameOptions(target).map((f) => <option key={f.frames} value={f.frames}>{f.label}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1 text-xs text-content-muted">Video size
          <select aria-label="Video size" value={sizeKey} onChange={(e) => setSizeKey(e.target.value)} className={field}>
            {sizes.map((s) => <option key={s.key} value={s.key}>{s.key === 'source' ? 'First video size (fit to model)' : s.label}</option>)}
          </select>
        </label>
      </div>
      {sizeKey === 'source' && <p className="text-xs text-content-subtle">The first imported video sets the size for this dataset. Later videos are resized to match.</p>}
      {targetWarnings(target).map((w) => <p key={w.key} className="text-xs text-content-muted">{w.text}</p>)}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <button type="submit" disabled={busy || !name.trim() || !target}
        className="min-h-10 self-end rounded-lg bg-gradient-primary px-4 py-1.5 text-sm font-semibold text-gray-950 disabled:opacity-40">
        {busy ? 'Creating…' : 'Create video dataset'}
      </button>
    </form>
  )
}
