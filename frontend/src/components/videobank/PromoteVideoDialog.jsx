import { useEffect, useMemo, useState } from 'react'
import { apiFetch, postJson } from '../../api/fetchClient'
import { useToast } from '../common/Toast'
import {
  frameOptions, defaultFrames, needsManualFrames, sizeOptions,
  promoteProblem, promotePayload, promoteScopeLabel,
} from './videoTargetChoice'
import { passBlockedBy } from './videoCapability'
import VideoTargetPicker from './VideoTargetPicker'

/** 🎬 Turn the shots you kept into a training set.
 *
 * THE TWO FIELDS THAT MAKE THIS SCREEN WORTH ITS SPACE are `training_verified`
 * and `licence_note`, and they are rendered NEXT TO THE CHOICE, not in a doc:
 *
 *  · exactly one target in the catalogue is known to have a working LoRA
 *    trainer. Picking one of the other three and finding out afterwards costs a
 *    week of cutting, captioning and GPU time on a dataset nothing can read;
 *  · MiniMax H3's licence grants NO rights in the EU, the UK, South Korea or the
 *    USA, and that restriction reaches the OUTPUTS — so keeping the training
 *    private is not a way around it. Someone must not learn that from a forum
 *    thread after building the set.
 *
 * The length selector offers ONLY the catalogue's frame counts. Never a free
 * field in seconds: the frame rule is a property of each model's VAE (29 frames
 * is legal for Wan and illegal for LTX; MiniMax wants f % 17 == 5), and no
 * trainer refuses an illegal count — they floor it in latent space, in silence.
 */
export default function PromoteVideoDialog({
  bankId, capability, keepCount, selectedIds, onClose, onDone,
}) {
  const toast = useToast()
  const [targets, setTargets] = useState(null)
  const [targetKey, setTargetKey] = useState('')
  const [name, setName] = useState('')
  const [frames, setFrames] = useState(null)
  const [sizeKey, setSizeKey] = useState('source')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    apiFetch('/api/video/targets')
      .then((d) => {
        if (!alive) return
        const list = d.targets || []
        setTargets(list)
        // Default to the one target known to be trainable rather than to the
        // first row — the default is a recommendation whether we mean it to be
        // one or not.
        const preferred = list.find((t) => t.training_verified) || list[0]
        if (preferred) { setTargetKey(preferred.key); setFrames(defaultFrames(preferred)) }
      })
      .catch((e) => { if (alive) setError(e?.message || 'Could not load the target list.') })
    return () => { alive = false }
  }, [])

  const target = useMemo(
    () => (targets || []).find((t) => t.key === targetKey) || null, [targets, targetKey])
  const options = frameOptions(target)
  const sizes = sizeOptions(target)
  const manualFrames = needsManualFrames(target)
  const blocked = passBlockedBy(capability, 'promote')
  const problem = blocked ? blocked.why : promoteProblem({ name, target, frames })
  const size = sizes.find((s) => s.key === sizeKey) || sizes[0]

  const pick = (key) => {
    const next = (targets || []).find((t) => t.key === key)
    setTargetKey(key)
    setFrames(defaultFrames(next))
    setSizeKey('source')
  }

  const submit = async (e) => {
    e.preventDefault()
    if (busy || problem) return
    setBusy(true)
    setError(null)
    try {
      const d = await postJson(`/api/video-bank/${bankId}/promote`,
        promotePayload({ name, targetKey, frames, size, ids: selectedIds }))
      toast.success(`Building “${d.name}” — ${d.clips} clip(s) being encoded.`)
      onDone?.(d)
      onClose?.()
    } catch (err) {
      // The server's 400 NAMES a legal length or a valid size. Showing it beats
      // any message we could invent from here.
      setError(err?.message || 'Could not start the export.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label="Build a video training set"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 sm:p-4">
      <form onSubmit={submit}
        className="w-full max-w-lg max-h-[90vh] space-y-4 overflow-y-auto rounded-xl border border-border bg-surface-overlay p-4 shadow-2xl sm:p-5">
        <h2 className="text-base font-bold text-content">🎬 Build a video training set</h2>
        <p className="text-sm text-content-muted">
          Encodes {promoteScopeLabel((selectedIds || []).length, keepCount)} into a flat
          folder of clips with caption sidecars. This is the only step that writes
          video files — your source folder is never touched.
        </p>

        <div>
          <label htmlFor="video-ds-name" className="block text-sm font-medium text-content">Name</label>
          <input id="video-ds-name" value={name} onChange={(e) => setName(e.target.value)}
            placeholder="wan 14b — city rushes" required
            className="mt-1 w-full rounded-md border border-border bg-surface-raised px-3 py-1.5 text-sm text-content" />
        </div>

        <fieldset>
          <legend className="text-sm font-medium text-content">Target model</legend>
          {/* Its own component so a test can mount it with the real catalogue
              and prove the licence note and the "no trainer" label are on
              screen — see VideoTargetPicker. */}
          <VideoTargetPicker targets={targets} targetKey={targetKey} onPick={pick} />
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="video-ds-frames" className="block text-sm font-medium text-content">
              Clip length
            </label>
            {manualFrames ? (
              <>
                <input id="video-ds-frames" type="number" min="1" step="1"
                  value={frames ?? ''} onChange={(e) => setFrames(Number(e.target.value) || null)}
                  className="mt-1 w-full rounded-md border border-border bg-surface-raised px-3 py-1.5 text-sm text-content" />
                {/* "No presets", never "any length is fine": we have no verified
                    lengths for this target, which is not the same claim. */}
                <p className="mt-1 text-xs text-content-muted">
                  In frames. We have no verified lengths for this target, so nothing is
                  suggested — check what your trainer expects.
                </p>
              </>
            ) : (
              <>
                <select id="video-ds-frames" value={frames ?? ''}
                  onChange={(e) => setFrames(Number(e.target.value) || null)}
                  className="mt-1 w-full rounded-md border border-border bg-surface-raised px-3 py-1.5 text-sm text-content">
                  {options.map((o) => (
                    <option key={o.frames} value={o.frames}>{o.label}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-content-muted">
                  Only lengths this model’s VAE can ingest. Seconds are shown at its own
                  frame rate — they are not something you type.
                </p>
              </>
            )}
          </div>
          <div>
            <label htmlFor="video-ds-size" className="block text-sm font-medium text-content">
              Size
            </label>
            <select id="video-ds-size" value={sizeKey} onChange={(e) => setSizeKey(e.target.value)}
              className="mt-1 w-full rounded-md border border-border bg-surface-raised px-3 py-1.5 text-sm text-content">
              {sizes.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            <p className="mt-1 text-xs text-content-muted">
              Suggestions mirror the model’s own inference sizes — they are not training
              limits. Keeping the source size is fine.
            </p>
          </div>
        </div>

        {error && (
          <p role="alert" className="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </p>
        )}

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button type="button" onClick={onClose}
            className="rounded-md border border-border px-3 py-1.5 text-sm text-content hover:bg-surface-raised">
            Cancel
          </button>
          <button type="submit" disabled={busy || !!problem} title={problem || undefined}
            className="rounded-md bg-gradient-primary px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-40">
            {busy ? 'Starting…' : `🎬 Encode ${promoteScopeLabel((selectedIds || []).length, keepCount)}`}
          </button>
        </div>
        {problem && <p className="text-right text-xs text-content-muted">{problem}</p>}
      </form>
    </div>
  )
}
