import { useCallback, useEffect, useState } from 'react'
import { apiFetch, del, postJson } from '../../api/fetchClient'
import { useToast } from '../common/Toast'
import { HelpBadge } from '../../help/HelpMode'
import { clipLabel } from './videoClipFragment'

/** 🎬 Video training sets, in the library, next to the image datasets.
 *
 * Silent when there are none — a permanently empty section on every visit is how
 * a library stops being read. It appears the moment a bank is promoted.
 *
 * TWO FIELDS RIDE ON EVERY CARD and they are not decoration: `training_verified`
 * and `licence_note`. They are shown at the picker as well, but a dataset is
 * something you come BACK to weeks later, and "which of these can I actually
 * train, and which one am I not allowed to publish from where I live" is exactly
 * the question you have then.
 */
export default function VideoDatasetsPanel() {
  const toast = useToast()
  const [datasets, setDatasets] = useState(null)
  const [openId, setOpenId] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const d = await apiFetch('/api/video-datasets', { background: true })
      setDatasets(d.datasets || [])
    } catch {
      setDatasets([])          // never break the image library over this panel
    }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const remove = async (ds) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Delete the video dataset “${ds.name}”?\n\nThe encoded clips are deleted. The bank they came from keeps every shot and every decision — you can re-cut at another length without triaging again.`)) return
    try {
      await del(`/api/video-dataset/${ds.id}`)
      toast.success('Video dataset deleted — the bank’s shots are untouched.')
      if (openId === ds.id) setOpenId(null)
      refresh()
    } catch (e) {
      toast.error(e?.message || 'Could not delete that dataset.')
    }
  }

  if (!datasets?.length) return null

  return (
    <section className="flex flex-col gap-2">
      <h2 className="flex items-center gap-2">
        <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-content-subtle">
          <span aria-hidden>🎬</span> Video training sets
          <span className="font-normal normal-case tracking-normal"> ({datasets.length})</span>
        </span>
        <HelpBadge topic="video-datasets" />
      </h2>
      <ul className="grid gap-2 grid-cols-1 sm:grid-cols-2">
        {datasets.map((d) => (
          <li key={d.id}
            className="flex min-w-0 flex-col gap-1.5 rounded-lg border border-border bg-surface p-3">
            <div className="flex min-w-0 items-center gap-2">
              <button type="button" onClick={() => setOpenId(openId === d.id ? null : d.id)}
                aria-expanded={openId === d.id}
                className="min-w-0 flex-1 truncate text-left text-sm font-semibold text-content hover:underline">
                {d.name}
              </button>
              <button type="button" onClick={() => remove(d)}
                aria-label={`Delete video dataset ${d.name}`}
                className="px-1.5 text-content-subtle hover:text-rose-300">✕</button>
            </div>
            <p className="text-xs text-content-muted">
              {d.clips} clip{d.clips === 1 ? '' : 's'} · {d.target_label}
              {d.frames ? ` · ${d.frames} frames` : ''}
              {d.clip_seconds ? ` (${d.clip_seconds.toFixed(2)}s)` : ''}
              {d.fps ? ` @ ${d.fps} fps` : ''}
              {d.width && d.height ? ` · ${d.width}×${d.height}` : ' · source size'}
            </p>
            {!d.training_verified && (
              <p className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1 text-[0.6875rem] text-amber-100">
                ⚠ No LoRA trainer is known to exist for {d.target_label} yet.
              </p>
            )}
            {d.licence_note && (
              <p className="rounded border border-rose-500/60 bg-rose-500/10 px-2 py-1 text-[0.6875rem] text-rose-100">
                ⚖ {d.licence_note}
              </p>
            )}
            <p className="truncate font-mono text-[0.625rem] text-content-subtle" title={d.output_dir}>
              {d.output_dir}
            </p>
            {openId === d.id && <VideoDatasetClips datasetId={d.id} />}
          </li>
        ))}
      </ul>
    </section>
  )
}

/** The clips of one dataset, each replayable and each captionable.
 *
 * ONE <video> at a time here too, for the same reason as the bank's grid: a
 * hundred mounted players is past the browser's silent ceiling. The clip that is
 * expanded is the clip that is mounted.
 *
 * The caption box writes the .txt sidecar next to the .mp4 — the trainer never
 * reads our database, so a caption saved only here would train the previous text
 * while showing the new one. The server does both in one call and tells us
 * whether the disk write landed; a failed sidecar is said out loud.
 */
function VideoDatasetClips({ datasetId }) {
  const toast = useToast()
  const [items, setItems] = useState(null)
  const [playing, setPlaying] = useState(null)
  const [drafts, setDrafts] = useState({})

  useEffect(() => {
    let alive = true
    apiFetch(`/api/video-dataset/${datasetId}`, { background: true })
      .then((d) => { if (alive) setItems(d.items || []) })
      .catch(() => { if (alive) setItems([]) })
    return () => { alive = false }
  }, [datasetId])

  const save = async (item) => {
    const caption = drafts[item.id] ?? item.caption ?? ''
    try {
      const d = await postJson(
        `/api/video-dataset/${datasetId}/clip/${item.id}/caption`, { caption })
      setItems((list) => list.map((i) => (i.id === item.id ? { ...i, caption: d.caption } : i)))
      if (d.sidecar_written) toast.success('Caption saved.')
      // Not a detail: the trainer reads the FILE. A row saved without its
      // sidecar trains the old text with nothing anywhere to reveal it.
      else toast.warning('Caption saved in the app, but its .txt file could not be written — the trainer reads the file.')
    } catch (e) {
      toast.error(e?.message || 'Could not save that caption.')
    }
  }

  if (items == null) return <p className="text-xs text-content-muted">Loading clips…</p>
  if (!items.length) return <p className="text-xs text-content-muted">No clip in this dataset.</p>

  return (
    <ul className="mt-1 space-y-2 border-t border-border pt-2">
      {items.map((item) => (
        <li key={item.id} className="min-w-0 space-y-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <button type="button" onClick={() => setPlaying(playing === item.id ? null : item.id)}
              className="rounded border border-border bg-surface-raised px-1.5 py-0.5 text-[0.625rem] font-semibold text-content hover:bg-surface">
              {playing === item.id ? '⏹ Close' : '▶ Play'}
            </button>
            <span className="min-w-0 truncate font-mono text-[0.625rem] text-content-subtle"
              title={`${item.src_relpath} — ${clipLabel(item.start_s, item.end_s)}`}>
              {item.filename}
            </span>
          </div>
          {playing === item.id && (
            <video controls autoPlay preload="metadata"
              src={`/api/video-dataset/${datasetId}/clip/${item.id}/media`}
              className="w-full rounded bg-black">
              <track kind="captions" />
            </video>
          )}
          <textarea rows={2} value={drafts[item.id] ?? item.caption ?? ''}
            onChange={(e) => setDrafts((m) => ({ ...m, [item.id]: e.target.value }))}
            onBlur={() => save(item)}
            aria-label={`Caption for ${item.filename}`}
            placeholder="Describe the clip — this is written to the .txt next to it."
            className="w-full rounded border border-border bg-surface-raised px-2 py-1 text-[0.6875rem] text-content" />
        </li>
      ))}
    </ul>
  )
}
