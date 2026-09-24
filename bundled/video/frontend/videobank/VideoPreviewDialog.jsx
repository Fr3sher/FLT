import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch, postJson } from '@lds/plugin-sdk';
import { useFocusTrap } from '@lds/plugin-sdk/ui';
import { HelpBadge } from '@lds/plugin-sdk';
import VideoOptionsPanel from '../studio/video/VideoOptionsPanel'
import VideoSourcePicker from '../studio/video/VideoSourcePicker'
import { clipsUrl, optionsUrl, pickAvailableAccel } from '../studio/video/videoStudioApi'
import { releasePreview } from '../studio/video/videoStartFrames'
import VideoPreviewResults from './VideoPreviewResults'
import {
  previewBatchNotice, previewChoices, previewKey, previewRequest, videoPreviewsUrl,
} from './videoPreviewSelection.js'

const INITIAL_OPTIONS = { accel: '', eros: false, light: false, sparse: '', latentUpscale: false,
  steps: '', frames: 56, megapixels: 0.3, seed: '' }

/** A shared take across saves. The Studio supplies its real inputs and render dials. */
export default function VideoPreviewDialog({ datasetId, tree, selected, onSelection,
  previews, initialTab = 'render', initialFilter = null, onRefresh, onQueued, onClose, loadError }) {
  const ref = useRef(null)
  const submitting = useRef(false)
  const [tab, setTab] = useState(initialTab)
  const [filterKey, setFilterKey] = useState(initialFilter)
  const [options, setOptions] = useState(null)
  const [studioHistory, setStudioHistory] = useState([])
  const [historyRefresh, setHistoryRefresh] = useState(0)
  const [opts, setOpts] = useState(INITIAL_OPTIONS)
  const [prompt, setPrompt] = useState('')
  const [mode, setMode] = useState('t2v')
  const [aspect, setAspect] = useState('landscape')
  const [source, setSource] = useState(null)
  const [endFrame, setEndFrame] = useState(null)
  const [strength, setStrength] = useState(1)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const choices = useMemo(() => previewChoices(tree), [tree])
  const sourceHistory = useMemo(() => {
    const ids = new Set(previews.map((p) => p.clip_id))
    return [...previews.map((p) => ({ ...p, id: p.clip_id })), ...studioHistory.filter((c) => !ids.has(c.id))]
      .sort((a, b) => b.id - a.id)
  }, [previews, studioHistory])
  useFocusTrap(ref)
  useEffect(() => {
    let alive = true
    apiFetch(clipsUrl()).then((d) => { if (alive) setStudioHistory(d.clips || []) })
      .catch((e) => { if (alive) setError(e.message || 'Could not read rendered clips. Refresh to try again.') })
    return () => { alive = false }
  }, [historyRefresh])
  useEffect(() => {
    let alive = true
    apiFetch(optionsUrl()).then((d) => {
      if (!alive) return
      setOptions(d)
      setOpts((v) => ({ ...v, accel: pickAvailableAccel('turbo', d.accelerations) }))
    }).catch((e) => { if (alive) setError(e.message || 'Could not check render availability.') })
    return () => { alive = false }
  }, [])
  // Upload blob previews belong to this dialog; staged images remain owned by the queue.
  useEffect(() => () => releasePreview(source), [source])
  useEffect(() => () => releasePreview(endFrame), [endFrame])
  useEffect(() => {
    const escape = (e) => { if (e.key === 'Escape' && !submitting.current) onClose() }
    window.addEventListener('keydown', escape)
    return () => window.removeEventListener('keydown', escape)
  }, [onClose])

  const toggle = (key) => onSelection(selected.includes(key)
    ? selected.filter((k) => k !== key) : [...selected, key])
  const submit = async () => {
    if (submitting.current) return
    setError(''); setNotice('')
    let body
    try { body = previewRequest({ choices, selected, prompt, mode, source, endFrame, aspect, strength, opts }) }
    catch (e) { setError(e.message); return }
    submitting.current = true; setBusy(true)
    try {
      const result = await postJson(videoPreviewsUrl(datasetId), body)
      setNotice(previewBatchNotice(result))
      // Never resubmit accepted items after a partial failure.
      const accepted = new Set((result.queued || []).map((p) => previewKey(p.selector)))
      onSelection(selected.filter((key) => !accepted.has(key)))
      onQueued(result)
      if (result.queued?.length) { setTab('history'); setFilterKey(null) }
    } catch (e) {
      setError(e.body?.failures?.length ? previewBatchNotice(e.body)
        : e.message || 'Could not queue previews. Refresh the history before retrying.')
      onRefresh()
    } finally { submitting.current = false; setBusy(false) }
  }
  const visiblePreviews = filterKey ? previews.filter((p) => previewKey(p.selector) === filterKey && p.source_current !== false) : previews
  return createPortal(<div className="fixed inset-0 z-[9000] flex items-center justify-center bg-black/80 p-2 sm:p-4"
    data-probe-layer data-probe-chrome="video-preview-dialog" role="dialog" aria-modal="true" aria-label="Checkpoint previews">
    <div ref={ref} className="flex max-h-full w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-border bg-surface-overlay">
      <header className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border p-3">
        <h2 className="text-sm font-semibold text-content">Checkpoint previews</h2>
        <HelpBadge topic="video-checkpoint-previews" />
        <button type="button" onClick={onClose} disabled={busy} aria-label="Close previews"
          className="ml-auto min-h-10 rounded border border-border px-3 text-xs text-content disabled:opacity-50 lg:min-h-0">Close</button>
        <div className="flex w-full flex-wrap gap-2">
          <button type="button" onClick={() => setTab('render')} aria-pressed={tab === 'render'} className="min-h-10 rounded border border-border px-3 text-xs text-content aria-pressed:border-primary lg:min-h-0">New previews{selected.length ? ` (${selected.length})` : ''}</button>
          <button type="button" onClick={() => setTab('history')} aria-pressed={tab === 'history'} className="min-h-10 rounded border border-border px-3 text-xs text-content aria-pressed:border-primary lg:min-h-0">History ({previews.length})</button>
          <button type="button" onClick={() => { onRefresh(); setHistoryRefresh((v) => v + 1) }} className="ml-auto min-h-10 rounded border border-border px-2 text-xs text-content-muted lg:min-h-0">Refresh</button>
        </div>
      </header>
      <div className="min-h-0 overflow-y-auto overscroll-contain p-3 sm:p-4">
        {error && <p role="alert" className="mb-3 break-words text-sm text-amber-200">{error}</p>}
        {loadError && <p role="alert" className="mb-3 break-words text-sm text-amber-200">{loadError}</p>}
        {notice && <p role="status" className="mb-3 break-words text-sm text-content">{notice}</p>}
        {tab === 'history' ? <VideoPreviewResults previews={visiblePreviews} filterKey={filterKey} onClearFilter={() => setFilterKey(null)} /> :
          <fieldset disabled={busy} className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="flex min-w-0 flex-col gap-4">
              <section className="rounded-lg border border-border p-3">
                <h3 className="text-sm font-semibold text-content">1. Checkpoints · {selected.length} selected</h3>
                <p className="my-2 text-xs text-content-muted">One clip per save, with the same prompt, seed and frames. Required LoRAs are copied into ComfyUI before rendering.</p>
                <div className="flex max-h-60 flex-col gap-1 overflow-y-auto">
                  {choices.map((c) => <label key={c.key} className={`flex min-h-10 items-start gap-2 rounded border border-border p-2 text-xs ${c.eligible ? 'cursor-pointer text-content' : 'text-content-subtle'}`}>
                    <input type="checkbox" checked={selected.includes(c.key)}
                      disabled={!c.eligible}
                      onChange={() => toggle(c.key)} className="mt-0.5 h-4 w-4 shrink-0 accent-primary" />
                    <span>{c.label}{!c.eligible && <span className="mt-1 block text-[0.6875rem]">{c.reason}</span>}</span>
                  </label>)}
                </div>
                {!!selected.length && <button type="button" onClick={() => onSelection([])} className="mt-2 min-h-10 rounded border border-border px-2 text-xs text-content lg:min-h-0">Clear selection</button>}
              </section>
              <section className="min-w-0 rounded-lg border border-border p-3">
                <h3 className="mb-2 text-sm font-semibold text-content">2. Shared motion</h3>
                <textarea aria-label="Shared motion prompt" maxLength={4000} rows={4} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the scene and motion to compare…"
                  className="w-full resize-y rounded border border-border bg-app p-2 text-sm text-content" />
                <label className="mt-2 flex flex-wrap items-center gap-2 text-xs text-content">LoRA strength
                  <input type="number" min={0} max={2} step={0.05} value={strength} onChange={(e) => setStrength(e.target.value)} className="min-h-10 w-24 rounded border border-border bg-app px-2 lg:min-h-0" />
                </label>
              </section>
              <section className="min-w-0 rounded-lg border border-border p-3">
                <h3 className="mb-2 text-sm font-semibold text-content">3. Shared frames</h3>
                <p className="mb-2 text-xs text-content-muted">For image-to-video, pick one start frame for every checkpoint. A new pick replaces it.</p>
                <VideoSourcePicker mode={mode} onMode={setMode} aspect={aspect} onAspect={setAspect} allowReferences={false} singleFrame
                  frames={source ? [source] : []} onAdd={(items) => { items.slice(0, -1).forEach(releasePreview); setSource(items.at(-1) || null) }}
                  onRemove={() => setSource(null)} onClear={() => setSource(null)}
                  history={sourceHistory} endFrame={endFrame} onSetEnd={setEndFrame} onClearEnd={() => setEndFrame(null)} />
              </section>
            </div>
            <VideoOptionsPanel options={options} value={opts} onChange={setOpts} />
          </fieldset>}
      </div>
      {tab === 'render' && <footer className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border bg-surface-overlay p-3">
        <p className="min-w-0 flex-1 text-xs text-content-muted">{selected.length} clip{selected.length === 1 ? '' : 's'} · one shared seed{opts.seed === '' ? ' (chosen at launch)' : `: ${opts.seed}`}</p>
        <button type="button" disabled={busy || !options || !selected.length} onClick={submit}
          className="min-h-10 rounded-md border border-primary bg-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{busy ? 'Queueing…' : 'Generate previews'}</button>
      </footer>}
    </div>
  </div>, document.body)
}
