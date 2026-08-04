import { useCallback, useEffect, useRef, useState } from 'react'
import { apiFetch, postJson } from '../../api/fetchClient'
import { useToast } from '../common/Toast'
import { HelpBadge } from '../../help/HelpMode'
import {
  videoBankUrl, videoClipsUrl, videoPassUrl,
} from './videoBankApi'
import { passBlockedBy } from './videoCapability'
import {
  countsSummary, countsProblems, activityLine, activityPercent, isBusy,
  resumeSafetyNote,
  announcement, nextStep, passLabel, PASS_LABELS,
} from './videoBankStatus'
import {
  STATUS_FILTERS, statusFilterCount, toggleSelection, selectRange,
  triagePayload, triageAllPayload, triageAllConfirmation, emptyGridMessage,
  hasMore,
} from './videoTriage'
import VideoCapabilityStrip from './VideoCapabilityStrip'
import VideoSourceList from './VideoSourceList'
import VideoClipGrid from './VideoClipGrid'
import VideoClipLightbox from './VideoClipLightbox'
import PromoteVideoDialog from './PromoteVideoDialog'

const PAGE = 120
const POLL_MS = 2000

/** 🎬 One video bank — sources, passes, and the shot gallery.
 *
 * A DELIBERATELY SEPARATE COMPONENT TREE from the image bank's workspace. The
 * two look alike from a distance and are not the same job: this one cuts one
 * file into hundreds of shots, stores BOUNDS rather than files, and encodes only
 * at promotion. Folding it into the image workspace (already 2500 lines) would
 * have bought shared chrome at the price of every conditional in it.
 *
 * The poll is the same 2 s contract as the image lane, on the payload that
 * already carries the live job — so a running pass costs one request, not two.
 */
export default function VideoBankWorkspace({ bankId, onBack, onGone }) {
  const toast = useToast()
  const [bank, setBank] = useState(null)
  const [clips, setClips] = useState([])
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState('all')
  const [sourceId, setSourceId] = useState(null)
  const [selected, setSelected] = useState([])
  const [anchor, setAnchor] = useState(null)
  const [openIndex, setOpenIndex] = useState(null)
  const [promoting, setPromoting] = useState(false)
  const [loadingClips, setLoadingClips] = useState(false)
  // The last job we announced, so a finished pass is toasted ONCE instead of on
  // every poll for as long as the server keeps its snapshot.
  const announced = useRef(null)

  const loadBank = useCallback(async (refresh = false) => {
    try {
      const d = await apiFetch(videoBankUrl(bankId, { refresh }),
        refresh ? {} : { background: true })
      setBank(d)
      return d
    } catch (e) {
      if (e?.status === 404) { onGone?.(); return null }
      // A failed POLL says nothing (apiFetch already owns the offline banner);
      // a failed OPEN is worth a line.
      if (refresh) toast.error(e?.message || 'Could not load this bank.')
      return null
    }
  }, [bankId, onGone, toast])

  const loadClips = useCallback(async (append = false) => {
    setLoadingClips(true)
    try {
      const d = await apiFetch(videoClipsUrl(bankId, {
        status, sourceId, offset: append ? clips.length : 0, limit: PAGE,
      }), { background: true })
      setClips((prev) => (append ? [...prev, ...(d.clips || [])] : (d.clips || [])))
      setTotal(d.total || 0)
    } catch {
      if (!append) { setClips([]); setTotal(0) }
    } finally {
      setLoadingClips(false)
    }
  }, [bankId, status, sourceId, clips.length])

  // Open: one refreshing read (the folder is LIVE — people keep dropping files
  // into it) plus the first page of shots.
  useEffect(() => { loadBank(true) }, [bankId])          // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setSelected([]); setAnchor(null); loadClips(false) },
    [bankId, status, sourceId])                           // eslint-disable-line react-hooks/exhaustive-deps

  // The 2 s poll. Never sends refresh=1: that re-walks the whole source tree
  // server-side, and doing it every two seconds on a folder of rushes is a
  // directory scan per tick for an answer that changes once an hour.
  useEffect(() => {
    const t = setInterval(() => { loadBank(false) }, POLL_MS)
    return () => clearInterval(t)
  }, [loadBank])

  // A pass that ended: say what it produced ONCE, and refresh the gallery it
  // just changed. `announcement` owns both halves of that (see its docstring —
  // the naive version either repeats on every poll or swallows a second
  // identical run).
  const activity = bank?.activity || null
  useEffect(() => {
    const { announce, marker, outcome } = announcement(announced.current, activity)
    announced.current = marker
    if (!announce) return
    if (outcome) toast[outcome.tone](outcome.text)
    loadClips(false)
  }, [activity])                                          // eslint-disable-line react-hooks/exhaustive-deps

  const counts = bank?.counts || {}
  const capability = bank?.capability || null
  const busy = isBusy(activity)
  const step = nextStep(counts, capability, passBlockedBy)

  const startPass = async (pass, body = {}) => {
    const blocked = passBlockedBy(capability, pass)
    if (blocked) { toast.warning(blocked.why); return }
    try {
      await postJson(videoPassUrl(bankId, pass), body)
      loadBank(false)
    } catch (e) {
      // 409 carries busy_kind — name the pass that owns the bank rather than
      // repeating "busy", which does not tell you what to wait for.
      if (e?.status === 409 && e.body?.busy_kind) {
        toast.warning(`${passLabel(e.body.busy_kind)} is already running on this bank.`)
      } else {
        toast.error(e?.message || `Could not start ${passLabel(pass)}.`)
      }
    }
  }

  const cancel = async () => {
    try {
      const d = await postJson(videoPassUrl(bankId, 'cancel'), {})
      // `cancelled: false` just means nothing was running — not an error, and
      // certainly not a red toast.
      toast.info(d.cancelled ? 'Stopping…' : 'Nothing was running.')
      loadBank(false)
    } catch (e) {
      toast.error(e?.message || 'Could not stop the pass.')
    }
  }

  const rescan = async () => {
    try {
      const d = await postJson(videoPassUrl(bankId, 'refresh'), {})
      toast.success(d.added
        ? `${d.added} new file(s) inventoried.`
        : 'No new file — the bank already knows this folder.')
      if (d.missing) toast.warning(`${d.missing} file(s) are no longer where the bank left them.`)
      loadBank(false)
    } catch (e) {
      toast.error(e?.message || 'Could not rescan the folder.')
    }
  }

  const triage = async (ids, next) => {
    const body = triagePayload(ids, next)
    // null = empty selection. Posting it would retag EVERY clip in the bank.
    if (!body) { toast.info('Select some shots first.'); return }
    await applyTriage(body, ids.length)
  }

  const triageEverything = async (next) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(triageAllConfirmation(next, counts.clips || 0))) return
    await applyTriage(triageAllPayload(next), counts.clips || 0)
  }

  const applyTriage = async (body, howMany) => {
    try {
      const d = await postJson(videoPassUrl(bankId, 'triage'), body)
      setBank((b) => (b ? { ...b, counts: d.counts || b.counts } : b))
      const touched = new Set(body.ids?.length ? body.ids : null)
      setClips((list) => list.map((c) => (
        !body.ids?.length || touched.has(c.id) ? { ...c, status: body.status } : c)))
      setSelected([])
      toast.success(`${d.updated ?? howMany} shot(s) → ${body.status}.`)
    } catch (e) {
      toast.error(e?.message || 'Could not save that decision.')
    }
  }

  const onToggle = (id, e) => {
    if (e?.shiftKey && anchor != null) {
      setSelected((s) => selectRange(s, clips.map((c) => c.id), anchor, id))
    } else {
      setSelected((s) => toggleSelection(s, id))
    }
    setAnchor(id)
  }

  const openAt = (clip) => setOpenIndex(clips.findIndex((c) => c.id === clip.id))
  const openClip = openIndex != null ? clips[openIndex] : null
  const triageOpen = async (next) => {
    if (!openClip) return
    await triage([openClip.id], next)
    setOpenIndex((i) => (i != null && i + 1 < clips.length ? i + 1 : i))
  }

  if (!bank) return <p className="text-sm text-content-muted">Loading…</p>
  const problems = countsProblems(counts)

  return (
    <div className="space-y-4">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <button type="button" onClick={onBack}
          className="rounded-md border border-border bg-surface-raised px-2.5 py-1 text-sm text-content hover:bg-surface">
          ← Banks
        </button>
        <h1 className="min-w-0 truncate text-lg font-bold text-content">🎬 {bank.name}</h1>
        <HelpBadge topic="page-video-bank" />
        <button type="button" onClick={rescan}
          title="Re-walk the folder and inventory anything new"
          className="ml-auto rounded-md border border-border bg-surface-raised px-2.5 py-1 text-xs font-semibold text-content hover:bg-surface">
          ↻ Rescan folder
        </button>
      </div>
      <p className="truncate font-mono text-xs text-content-subtle" title={bank.source_path}>
        {bank.source_path}
      </p>

      <VideoCapabilityStrip capability={capability} />

      <p className="text-sm text-content-muted">{countsSummary(counts)}</p>
      {problems.map((p) => (
        <p key={p} className="text-xs text-amber-300">⚠ {p}</p>
      ))}

      {/* What to do next, as ONE sentence. Four equal buttons and no order is
          how a user runs detection before the probe, gets "0 shots" and a green
          success, and concludes the app cannot read their files. */}
      <div className="rounded-lg border border-border bg-surface p-3 text-sm">
        <p className="text-content">{step.text}</p>
        {step.blocked && (
          <p className="mt-1 text-xs text-amber-300">⚠ {step.blocked.why}</p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {['pipeline', 'probe', 'detect', 'thumbs'].map((pass) => {
          const blocked = passBlockedBy(capability, pass)
          const primary = pass === 'pipeline'
          return (
            <button key={pass} type="button" onClick={() => startPass(pass)}
              disabled={busy || !!blocked}
              title={blocked ? blocked.why : undefined}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold disabled:opacity-40 ${
                primary
                  ? 'bg-gradient-primary text-white'
                  : 'border border-border bg-surface-raised text-content hover:bg-surface'}`}>
              {primary ? '▶ ' : ''}{PASS_LABELS[pass]}
            </button>
          )
        })}
        <button type="button" onClick={() => setPromoting(true)}
          disabled={busy || !counts.keep}
          title={!counts.keep ? 'Keep some shots first' : undefined}
          className="rounded-md border border-indigo-500/60 bg-indigo-500/15 px-3 py-1.5 text-xs font-semibold text-indigo-200 hover:bg-indigo-500/25 disabled:opacity-40">
          🎬 {PASS_LABELS.promote}
        </button>
        {busy && (
          <button type="button" onClick={cancel}
            className="rounded-md border border-rose-500/60 bg-rose-500/10 px-3 py-1.5 text-xs font-semibold text-rose-200 hover:bg-rose-500/20">
            ⏹ Stop
          </button>
        )}
      </div>

      {busy && (
        <div role="status" className="rounded-lg border border-amber-500/50 bg-amber-500/10 p-2.5">
          <p className="text-sm text-amber-100">⏳ {activityLine(activity, counts)}</p>
          <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-black/30">
            <div className={`h-full bg-amber-400 ${activityPercent(activity, counts) == null ? 'w-1/3 animate-pulse' : ''}`}
              style={activityPercent(activity, counts) == null ? undefined
                : { width: `${activityPercent(activity, counts)}%` }} />
          </div>
          {/* A resumed pass counts only what is LEFT, so it honestly reports "3 of
              117" while most of the bank is already cut. Saying what is kept is
              what makes stopping a one-hour pass feel allowed. */}
          {resumeSafetyNote(activity, counts) && (
            <p className="mt-1.5 text-xs text-amber-200/80">
              ↩ {resumeSafetyNote(activity, counts)}
            </p>
          )}
        </div>
      )}

      <details className="rounded-lg border border-border bg-surface">
        <summary className="cursor-pointer px-3 py-2 text-sm font-semibold text-content">
          Files ({counts.sources || 0})
        </summary>
        <div className="border-t border-border p-3">
          <VideoSourceList sources={bank.sources || []} activeSourceId={sourceId}
            onFilter={setSourceId} />
        </div>
      </details>

      {/* --- the gallery ------------------------------------------------- */}
      <div className="flex flex-wrap items-center gap-1.5">
        {STATUS_FILTERS.map((f) => (
          <button key={f.key} type="button" onClick={() => setStatus(f.key)}
            aria-pressed={status === f.key}
            className={`rounded-full border px-2.5 py-1 text-[0.6875rem] font-semibold transition-colors ${
              status === f.key
                ? 'border-primary/60 bg-primary/15 text-content'
                : 'border-border bg-surface text-content-muted hover:bg-surface-raised'}`}>
            {f.label} ({statusFilterCount(counts, f.key)})
          </button>
        ))}
        {sourceId && (
          <button type="button" onClick={() => setSourceId(null)}
            className="rounded-full border border-indigo-500/60 bg-indigo-500/15 px-2.5 py-1 text-[0.6875rem] font-semibold text-indigo-200">
            one file only ✕
          </button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-content-muted">
          {selected.length ? `${selected.length} selected` : `${clips.length} of ${total} shown`}
        </span>
        <button type="button" onClick={() => triage(selected, 'keep')} disabled={!selected.length}
          className="rounded-md bg-emerald-600/80 px-2.5 py-1 font-semibold text-white hover:bg-emerald-600 disabled:opacity-30">
          ✓ Keep
        </button>
        <button type="button" onClick={() => triage(selected, 'reject')} disabled={!selected.length}
          className="rounded-md bg-rose-600/80 px-2.5 py-1 font-semibold text-white hover:bg-rose-600 disabled:opacity-30">
          ✕ Reject
        </button>
        <button type="button" onClick={() => setSelected(clips.map((c) => c.id))}
          disabled={!clips.length}
          className="rounded-md border border-border bg-surface-raised px-2.5 py-1 text-content hover:bg-surface disabled:opacity-30">
          Select page
        </button>
        {selected.length > 0 && (
          <button type="button" onClick={() => setSelected([])}
            className="rounded-md border border-border bg-surface-raised px-2.5 py-1 text-content hover:bg-surface">
            Clear
          </button>
        )}
        {/* "Everything" is a separate control on purpose — it is the one action
            here that also hits shots you cannot see. */}
        <button type="button" onClick={() => triageEverything('reject')}
          disabled={!counts.clips}
          className="ml-auto rounded-md border border-border bg-surface-raised px-2.5 py-1 text-content-muted hover:bg-surface disabled:opacity-30">
          Reject all…
        </button>
      </div>

      <VideoClipGrid bankId={bankId} clips={clips} selected={selected}
        onToggle={onToggle} onOpen={openAt}
        emptyMessage={emptyGridMessage({
          status,
          sourceName: bank.sources?.find((s) => s.id === sourceId)?.relpath,
          counts,
        })} />

      {hasMore({ loaded: clips.length, total }) && (
        <div className="flex justify-center">
          <button type="button" onClick={() => loadClips(true)} disabled={loadingClips}
            className="rounded-md border border-border bg-surface-raised px-4 py-1.5 text-sm font-semibold text-content hover:bg-surface disabled:opacity-40">
            {loadingClips ? 'Loading…' : `Load more (${total - clips.length} left)`}
          </button>
        </div>
      )}

      {openClip && (
        <VideoClipLightbox bankId={bankId} clip={openClip}
          hasPrev={openIndex > 0} hasNext={openIndex < clips.length - 1}
          onClose={() => setOpenIndex(null)}
          onPrev={() => setOpenIndex((i) => Math.max(0, i - 1))}
          onNext={() => setOpenIndex((i) => Math.min(clips.length - 1, i + 1))}
          onKeep={() => triageOpen('keep')}
          onReject={() => triageOpen('reject')} />
      )}

      {promoting && (
        <PromoteVideoDialog bankId={bankId} capability={capability}
          keepCount={counts.keep || 0} selectedIds={selected}
          onClose={() => setPromoting(false)}
          onDone={() => { setSelected([]); loadBank(false) }} />
      )}
    </div>
  )
}
