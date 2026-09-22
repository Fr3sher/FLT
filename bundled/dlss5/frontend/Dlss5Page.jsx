import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { apiFetch, postForm, postJson } from '@lds/plugin-sdk'
import NeuralRenderDialog from './NeuralRenderDialog.jsx'
import SideBySideVideo from './SideBySideVideo.jsx'

const base = '/api/dlss5/clips'
const active = clip => ['running', 'queued', 'cancelling'].includes(clip?.state)
const button = 'min-h-10 rounded-md border border-border px-3 py-2 text-sm text-content disabled:opacity-50'

export default function Dlss5Page() {
  const [clips, setClips] = useState([])
  const [status, setStatus] = useState(null)
  const [selected, setSelected] = useState(null)
  const [dialog, setDialog] = useState(null)
  const [compare, setCompare] = useState(null)
  const [busy, setBusy] = useState(false)
  const [openingFolder, setOpeningFolder] = useState(false)
  const [folderError, setFolderError] = useState('')
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const refresh = useCallback(async () => {
    try {
      const [list, preparation] = await Promise.all([apiFetch(base), apiFetch('/api/dlss5/status')])
      if (mounted.current) { setClips(list.clips || []); setStatus(preparation.status); setError('') }
    } catch (err) { if (mounted.current) setError(err.message || 'Could not load DLSS 5.') }
  }, [])
  useEffect(() => { mounted.current = true; refresh(); return () => { mounted.current = false } }, [refresh])
  const running = clips.some(active)
  useEffect(() => {
    if (!running) return undefined
    const timer = setInterval(refresh, 1500)
    return () => clearInterval(timer)
  }, [running, refresh])
  const upload = async event => {
    const file = event.target.files?.[0]
    if (!file) return
    setBusy(true); setError('')
    try {
      const form = new FormData(); form.append('file', file)
      const value = await postForm(base, form)
      setSelected(value.clip.id); await refresh()
    } catch (err) { setError(err.message || 'Could not import the video.') }
    finally { setBusy(false); event.target.value = '' }
  }
  const render = async params => {
    setBusy(true)
    try { await postJson(`${base}/${dialog.id}/render`, params); setDialog(null); await refresh() }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const cancel = async clip => {
    try { await postJson(`${base}/${clip.id}/cancel`, {}); await refresh() }
    catch (err) { setError(err.message) }
  }
  const openFolder = async clip => {
    setOpeningFolder(true); setFolderError('')
    try { await postJson(`${base}/${clip.id}/open-folder`, {}) }
    catch (err) { setFolderError(err.message || 'Could not open the video folder.') }
    finally { setOpeningFolder(false) }
  }
  const clip = clips.find(item => item.id === selected) || clips[0]
  return <main className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-2xl font-semibold text-content">DLSS 5 Neural Rendering</h1>
        <p className="mt-2 max-w-2xl text-sm text-content-muted">Improve a finished video, compare the detail and keep the original. This studio works independently of Video lane.</p></div>
      <Link to="/plugins/dlss5/settings" className={button}>Preparation &amp; settings</Link>
    </header>
    {error && <p role="alert" className="rounded-lg border border-red-500/40 p-3 text-sm text-red-400">{error}</p>}
    {folderError && <p role="alert" className="rounded-lg border border-red-500/40 p-3 text-sm text-red-400">{folderError}</p>}
    {status && !status.ready && <div role="status" className="rounded-lg border border-border bg-surface p-4 text-sm text-content-muted">
      <p>Complete DLSS preparation before rendering.</p><ul className="mt-2 list-inside list-disc">{status.missing?.map(text => <li key={text}>{text}</li>)}</ul>
      <Link to="/plugins/dlss5/settings" className="mt-3 inline-block text-primary">Prepare DLSS 5 →</Link>
    </div>}
    <section className="rounded-xl border border-border bg-surface p-5">
      <label className="block text-sm font-semibold text-content">Import a finished video
        <input aria-label="Import a finished video" type="file" accept="video/mp4,video/quicktime,video/x-matroska,video/webm,video/x-msvideo,.m4v"
          disabled={busy} onChange={upload} className="mt-3 block max-w-full text-sm" />
      </label>
      <p className="mt-2 text-xs text-content-muted">MP4, MOV, MKV, WebM, AVI or M4V · Up to 512 MB. The original stays untouched; each render starts from it.</p>
    </section>
    {clip ? <section className="grid min-w-0 gap-5 lg:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="min-w-0 rounded-xl border border-border bg-surface p-4">
        <h2 className="break-words text-base font-semibold text-content">{clip.name}</h2>
        <video key={`${clip.id}:${clip.has_result}:${clip.state}`} controls preload="metadata"
          className="mt-3 max-h-[60vh] w-full rounded-lg bg-black" src={`${base}/${clip.id}/media/${clip.has_result ? 'result' : 'original'}`} />
        <p role="status" className="mt-3 text-sm text-content-muted">{clip.state === 'done' ? 'Render complete' : clip.state}
          {active(clip) && clip.progress?.frame != null ? ` · Frame ${clip.progress.frame}${clip.progress.total ? ` / ${clip.progress.total}` : ''}` : ''}</p>
        {clip.error && <p className="mt-2 text-sm text-red-400">{clip.error}</p>}
        <div className="mt-4 flex flex-wrap gap-2">
          {active(clip) ? <button type="button" onClick={() => cancel(clip)} className={button}>Cancel render</button>
            : <button type="button" disabled={busy || running || !status?.ready} onClick={() => setDialog(clip)}
              className={`${button} bg-primary text-black`}>Render with DLSS 5</button>}
          {clip.has_result && <><button type="button" onClick={() => setCompare(clip)} className={button}>Compare original &amp; result</button>
            <a href={`${base}/${clip.id}/media/result?download=1`} className={button}>Download result</a></>}
          <button type="button" disabled={openingFolder} onClick={() => openFolder(clip)} className={button}
            title="Open this clip's folder on the computer running LDS, containing the original and any rendered result.">
            {openingFolder ? 'Opening folder…' : 'Open folder'}</button>
        </div>
      </div>
      <aside className="min-w-0"><h2 className="mb-3 font-semibold text-content">Your clips</h2>
        <div className="space-y-2">{clips.map(item => <button key={item.id} type="button" onClick={() => setSelected(item.id)} aria-pressed={item.id === clip.id}
          className={`w-full rounded-lg border p-3 text-left ${item.id === clip.id ? 'border-primary bg-surface-raised' : 'border-border bg-surface'}`}>
          <span className="block truncate text-sm text-content">{item.name}</span><span className="text-xs text-content-muted">{item.state}</span></button>)}</div>
      </aside>
    </section> : <p className="py-8 text-center text-content-muted">Import your first video to start.</p>}
    {dialog && <NeuralRenderDialog status={status} initial={dialog.params} subject={dialog.name}
      consequence="Creates a new result. Your original video remains untouched." busy={busy} onRender={render} onClose={() => setDialog(null)} />}
    {compare && <SideBySideVideo originalSrc={`${base}/${compare.id}/media/original`} renderSrc={`${base}/${compare.id}/media/result`}
      title={compare.name} exportHref={`${base}/${compare.id}/comparison`} onClose={() => setCompare(null)} />}
  </main>
}
