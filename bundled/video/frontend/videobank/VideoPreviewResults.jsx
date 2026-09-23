import { useEffect, useRef, useState } from 'react'
import { previewLabel } from './videoPreviewSelection.js'
import { syncActions } from './videoSync.js'

/** Posters in the history; only the opened result (or comparison pair) plays. */
export default function VideoPreviewResults({ previews, filterKey = null, onClearFilter }) {
  const [activeId, setActiveId] = useState(null)
  const [compareId, setCompareId] = useState(null)
  const leader = useRef(null)
  const follower = useRef(null)
  const active = previews.find((p) => p.clip_id === activeId && p.status === 'done' && p.url)
  const compare = active && previews.find((p) => p.clip_id === compareId && p.status === 'done' && p.url)
  const sync = () => {
    const a = leader.current; const b = follower.current
    if (!a || !b) return
    for (const action of syncActions(a, b)) {
      if (action.type === 'seek') b.currentTime = action.value
      else if (action.type === 'rate') b.playbackRate = action.value
      else if (action.type === 'pause') b.pause()
      else if (action.type === 'play') b.play()?.catch(() => {})
    }
  }
  useEffect(() => { leader.current?.pause(); follower.current?.pause() }, [activeId, compareId])
  const play = (p, second = false) => (
    <figure className="min-w-0" key={p.clip_id}>
      <figcaption className="mb-1 text-xs font-semibold text-content">{second ? 'B' : 'A'} · {previewLabel(p.selector)}</figcaption>
      <video ref={second ? follower : leader} src={p.url} poster={p.poster_url || undefined}
        controls={!second} muted={second} playsInline preload="metadata"
        aria-label={`${second ? 'B' : 'A'} ${previewLabel(p.selector)}`}
        onPlay={second ? undefined : sync} onPause={second ? undefined : sync}
        onSeeked={second ? undefined : sync} onRateChange={second ? undefined : sync}
        onTimeUpdate={second ? undefined : sync} onLoadedMetadata={second ? sync : undefined}
        className="max-h-[45vh] w-full rounded-lg bg-black" />
      <p className="mt-1 text-[0.6875rem] text-content-muted">Seed {p.seed} · {p.generation_settings?.steps ?? '?'} steps · {p.generation_settings?.frames ?? '?'} frames</p>
      <p className="mt-1 whitespace-pre-wrap break-words text-xs text-content-muted">{p.prompt}</p>
      <details className="mt-1 text-xs text-content-subtle"><summary className="min-h-10 cursor-pointer lg:min-h-0">Render settings</summary>
        <pre className="whitespace-pre-wrap break-all">{JSON.stringify(p.generation_settings || {}, null, 2)}</pre>
      </details>
    </figure>
  )
  return <div className="flex min-w-0 flex-col gap-3">
    {filterKey && <button type="button" className="min-h-10 self-start rounded border border-border px-3 text-xs text-content lg:min-h-0" onClick={onClearFilter}>Show all checkpoints</button>}
    {!previews.length && <p className="text-sm text-content-muted">No rendered preview yet. Training samples remain available from each checkpoint.</p>}
    {active && <section className="rounded-lg border border-border bg-app p-3" aria-label="Preview playback">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-content-muted">
        <span>{compare ? 'Compare A / B · A controls both players' : 'Rendered preview'}</span>
        {compare && active.batch_id !== compare.batch_id && <span className="text-amber-200">Different batches — check prompts and settings.</span>}
        <button type="button" onClick={() => { setActiveId(null); setCompareId(null) }} className="ml-auto min-h-10 rounded border border-border px-2 lg:min-h-0">Close player</button>
      </div>
      <div className={compare ? 'grid min-w-0 gap-3 md:grid-cols-2' : ''}>{play(active)}{compare && play(compare, true)}</div>
    </section>}
    <ul className="grid list-none gap-2 p-0 sm:grid-cols-2 lg:grid-cols-3" aria-label="Rendered preview history">
      {previews.map((p) => <li key={p.clip_id} className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-surface p-3">
        <div className="flex flex-wrap justify-between gap-1 text-xs text-content"><strong>{previewLabel(p.selector)}</strong><span>{p.status}</span></div>
        {p.poster_url && <img loading="lazy" src={p.poster_url} alt="" className="aspect-video w-full rounded object-contain bg-black" />}
        <p className="text-[0.6875rem] text-content-subtle">Seed {p.seed} · clip #{p.clip_id}</p>
        {p.source_current === false && <p className="text-xs text-amber-200">Original save changed or removed</p>}
        <p className="line-clamp-3 break-words text-xs text-content-muted">{p.prompt}</p>
        {p.error && <p role="alert" className="break-words text-xs text-amber-200">{p.error}</p>}
        {p.status === 'done' && p.url && <div className="mt-auto flex flex-wrap gap-2">
          <button type="button" aria-label={`Play ${previewLabel(p.selector)} clip ${p.clip_id}`} onClick={() => { setActiveId(p.clip_id); setCompareId(null) }} className="min-h-10 rounded border border-primary/50 px-2 text-xs text-content lg:min-h-0">Play</button>
          {active && p.clip_id !== activeId && <button type="button" onClick={() => setCompareId(p.clip_id)} className="min-h-10 rounded border border-border px-2 text-xs text-content lg:min-h-0">Compare with A</button>}
          <a href={p.url} download className="flex min-h-10 items-center rounded border border-border px-2 text-xs text-content lg:min-h-0">Download</a>
        </div>}
      </li>)}
    </ul>
  </div>
}
