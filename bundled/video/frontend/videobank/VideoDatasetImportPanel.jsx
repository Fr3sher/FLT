import { useState } from 'react'
import { Link } from 'react-router'
import { postForm, postJson } from '@lds/plugin-sdk'
import { PluginSlot } from '@lds/plugin-sdk/ui'

export default function VideoDatasetImportPanel({ ds, refresh }) {
  const [sliceLong, setSliceLong] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const activity = ds.import_activity
  const importing = !!activity && !activity.finished
  const upload = async (event) => {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    if (!files.length || sending || importing) return
    const form = new FormData()
    for (const file of files) form.append('files', file)
    form.append('slice_long', String(sliceLong))
    setSending(true); setError('')
    try { await postForm(`/api/video-dataset/${ds.id}/import`, form); await refresh() }
    catch (e) { setError(e.message) }
    finally { setSending(false) }
  }
  const stop = async () => {
    try { await postJson(`/api/video-dataset/${ds.id}/import/cancel`, {}); await refresh() }
    catch (e) { setError(e.message) }
  }
  return (
    <div id="vds-import-sources" className="flex min-w-0 flex-col gap-3">
      <p className="text-xs text-content-muted">Videos are encoded to {ds.frames} frames at {ds.fps} fps. Files shorter than the chosen clip length are skipped. Add captions after importing.</p>
      <label className="flex min-h-10 items-center gap-2 text-sm text-content-muted">
        <input type="checkbox" checked={sliceLong} disabled={sending || importing} onChange={(e) => setSliceLong(e.target.checked)} />
        Split long videos into consecutive clips
      </label>
      <p className="text-xs text-content-subtle">{sliceLong ? 'Keeps every complete clip from each video; any shorter remainder is left out.' : 'Keeps the first clip of the chosen length from each video.'}</p>
      <label className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-3 text-sm text-content">
        Add video files
        <input type="file" multiple accept=".mp4,.mov,.mkv,.webm,.avi" disabled={sending || importing}
          onChange={upload} className="min-h-10 min-w-0 max-w-full text-xs" />
        <span className="text-xs text-content-subtle">MP4, MOV, MKV, WebM or AVI · 200 MB per file and 1 GB per upload.</span>
      </label>
      {sending && <p role="status" className="text-sm text-content-muted">Uploading videos…</p>}
      {activity && <div role="status" className="rounded-lg border border-border p-3 text-sm text-content-muted">
        {activity.cancelled ? 'Import stopped. ' : ''}{activity.error || activity.detail || 'Preparing videos…'}
        {importing && <span> · {activity.done}/{activity.total}</span>}
        {importing && <button type="button" onClick={stop} disabled={activity.cancelled}
          className="ml-2 min-h-10 rounded border border-border px-3">{activity.cancelled ? 'Stopping…' : 'Stop import'}</button>}
      </div>}
      {error && <p role="alert" className="text-sm text-rose-300">{error}</p>}
      <PluginSlot slot="sources.panel" surface="videoDataset" datasetId={ds.id}
        busy={sending || importing} sliceLong={sliceLong} onDone={refresh}
        fallback={<p className="text-sm text-content-muted">To scan website URLs here, enable Web scraping in <Link to="/plugins" className="underline">Plugins</Link>.</p>} />
    </div>
  )
}
