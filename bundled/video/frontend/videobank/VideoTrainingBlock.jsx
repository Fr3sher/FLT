import { useCallback, useEffect, useState } from 'react'
import { apiFetch, postJson } from '@lds/plugin-sdk'
import { useToast } from '@lds/plugin-sdk'
import { HelpBadge } from '@lds/plugin-sdk'
import { PluginSlot, hasContributions } from '@lds/plugin-sdk/ui'
import { ensureLicenceAck } from './licenceAck.js'

/** Targets that have been trained end to end at least once — locally or on a
 * rented pod, it does not matter which: what the note below cares about is
 * whether a real run has ever finished. A target absent from this set is wired
 * from the installed ai-toolkit's own code and preset — correct as far as
 * reading goes, never yet proven by a run — and the card says so, because "it
 * is wired" and "it works" are different claims and only the user can decide
 * whether to spend a night (or a pod bill) on the second. */
const PROVEN_TARGETS = new Set(['wan22_14b', 'minimax_h3', 'minimax_h3_ref2va'])

/** 🎬 The training block of one video dataset: one set of dials, two
 * destinations, and everything the runs report back.
 *
 * This used to be two stacked sections — a local one and a cloud one — each
 * with its own Steps field and its own i2v checkbox. Two fields for one number
 * read as two different features, and a value typed in one lane silently did
 * not apply to the other. The settings describe the RUN, not the machine, so
 * they are asked for once and the destination is just the button you press
 * (maintainer's call, 2026-08-30).
 *
 * WHY THE COST IS ON SCREEN BEFORE THE CLICK (cloud)
 * A pod is billed from the moment it boots, so the block says the GPU and the
 * hourly price as soon as the run has one, and it refuses a launch it can
 * already tell will fail (no clips, a run already on a pod) rather than
 * rendering the server's 409.
 *
 * WHY THE LOCAL BUTTON MUST NEVER START SILENTLY
 * MiniMax H3 pulls about 43 GB of weights on its first local run, so the server
 * refuses with the repository and the size, and this asks, once, before that
 * becomes a night of downloading behind a bar that reads "Starting up…".
 *
 * WHY A CHECKPOINT IS A STEP AND NOT A FILE
 * A Wan 2.2 LoRA is TWO files at one step — the high-noise and low-noise
 * experts — and either one alone is a LoRA no loader can complete. So the unit
 * on screen is the step, its files are downloaded together, and a MiniMax H3
 * step (one file) renders through the same shape without a special case.
 *
 * Polling is strictly on demand: the local line polls only while this
 * dataset's own run is live (`active` is answered from the training fence,
 * which names the TABLE as well as the id — a face training of the colliding
 * id must not drive this bar), the cloud line only while a pod is on the
 * clock, and GPU offers are fetched on click, never on mount — a library page
 * with a dozen datasets must not fan out a vast.ai search per card.
 */
export default function VideoTrainingBlock({ ds, onSaveCount, refreshKey = 0 }) {
  const toast = useToast()
  // ONE dial set for both destinations. Prefilled with the server's
  // dataset-sized suggestion (steps scale with the clip count — measured, not
  // vibes; see suggested_steps in video_training.py). Still just a prefill:
  // what the user types is what trains, wherever it trains.
  const [steps, setSteps] = useState(ds?.suggested_steps || 2000)
  const [doI2v, setDoI2v] = useState(false)

  // Local lane.
  const [progress, setProgress] = useState(null)
  const [busyLocal, setBusyLocal] = useState(false)

  // Cloud Training contributes the optional lane; Video keeps the shared dials.
  const [launchHost, setLaunchHost] = useState(null)
  const [cloudSaveCount, setCloudSaveCount] = useState(0)
  const cloudAvailable = hasContributions('training.launch', 'video')
  const confirmLicence = () => ensureLicenceAck(ds, {
    storage: window.localStorage, confirmFn: window.confirm,
  })

  const pollLocal = useCallback(async () => {
    try {
      setProgress(await apiFetch(`/api/video-dataset/${ds.id}/train/progress`,
        { background: true }))
    } catch { /* the card stays useful without its progress line */ }
  }, [ds.id])
  useEffect(() => { pollLocal() }, [pollLocal])

  const localActive = !!progress?.active
  useEffect(() => {
    if (!localActive) return undefined
    const t = setInterval(pollLocal, 3000)
    return () => clearInterval(t)
  }, [localActive, pollLocal])

  // Report both destinations through the workspace's existing refresh signal.
  const saveCount = (cloudAvailable ? cloudSaveCount : 0)
    + (progress?.checkpoints?.length || 0)
  useEffect(() => { onSaveCount?.(saveCount) }, [saveCount, onSaveCount])
  useEffect(() => { if (refreshKey) pollLocal() }, [refreshKey, pollLocal])

  const startLocal = async (acceptDownload = false) => {
    // The licence question comes BEFORE anything is spent — not after the
    // download confirm, whose 43 GB would already be an investment in a run
    // the licence answer might forbid.
    if (!ensureLicenceAck(ds, {
      storage: window.localStorage, confirmFn: window.confirm,
    })) return undefined
    setBusyLocal(true)
    try {
      const r = await postJson(`/api/video-dataset/${ds.id}/train`,
        { steps, do_i2v: doI2v, accept_download: acceptDownload })
      toast.success(`Training started — ${r.clips} clips, ${r.steps} steps.`)
      // Things the run will not fail on but that change what to expect from it.
      ;(r.warnings || []).forEach((w) => toast.warning(w))
      pollLocal()
    } catch (e) {
      const body = e?.body
      if (body?.needs_download) {
        // `free_gigabytes` is null when the drive could not be measured. Saying
        // nothing is the only honest rendering — "0 GB free" and "plenty of
        // room" are opposite answers and we have neither.
        const room = typeof body.free_gigabytes === 'number'
          ? ` You have ${body.free_gigabytes.toFixed(1)} GB free there.`
          : ''
        if (window.confirm(`${body.error}\n\nDownload about ${body.gigabytes} GB from ${body.repo}?${room}`)) {
          setBusyLocal(false)
          return startLocal(true)
        }
      } else {
        // A refusal that carries its own fix (a pip line to paste) needs
        // longer than the 6 s default — it has to be read and copied.
        const msg = e?.message || 'Could not start training.'
        toast.error(msg, msg.length > 200 ? 20000 : undefined)
      }
    } finally {
      setBusyLocal(false)
    }
    return undefined
  }

  const stopLocal = async () => {
    try {
      const r = await postJson(`/api/video-dataset/${ds.id}/train/stop`, {})
      // `ok: false` means the fence names another run. Saying "stopped" there
      // would tell the user a GPU was released while ai-toolkit still owns it.
      if (r.ok) toast.success('Training stopped.')
      else toast.warning('That run is not this dataset’s — nothing was stopped.')
      pollLocal()
    } catch (e) {
      toast.error(e?.message || 'Could not stop training.')
    }
  }

  if (!ds.training_verified) return null

  const dl = progress?.download

  return (
    <section className="flex flex-col gap-1.5 border-t border-border pt-1.5">
      {localActive ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <button type="button" onClick={stopLocal}
            className="rounded border border-rose-500/60 bg-rose-500/10 px-2 py-1 text-[0.6875rem] font-semibold text-rose-100 hover:bg-rose-500/20">
            ⏹ Stop training
          </button>
          <HelpBadge topic="video-train-local" />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            <label className="flex items-center gap-1 text-[0.6875rem] text-content-muted">
              Steps
              <input type="number" min={100} step={100} value={steps}
                onChange={(e) => setSteps(Number(e.target.value) || 1000)}
                className="w-20 rounded border border-border bg-surface-raised px-1.5 py-0.5 text-[0.6875rem] text-content" />
            </label>
            {Boolean(ds?.suggested_steps) && (
              <span className="text-[0.625rem] text-content-subtle">
                suggested for {ds.clips} clips
              </span>
            )}
            {ds.target_profile === 'minimax_h3' && (
              <label className="flex items-center gap-1 text-[0.6875rem] text-content-muted">
                <input type="checkbox" checked={doI2v}
                  onChange={(e) => setDoI2v(e.target.checked)} />
                i2v (first-frame)
              </label>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {/* BETA, and honestly so (maintainer's call, 2026-08-30): the rail
                is proven end to end but days old, and a label that says "expect
                rough edges" costs less than a user who assumed a settled
                feature. Same chip both destinations — the beta is the RAIL. */}
            <span className="rounded border border-amber-500/50 bg-amber-500/10 px-1.5 py-0.5 text-[0.625rem] font-semibold uppercase tracking-wider text-amber-200">
              Beta
            </span>
            <button type="button" onClick={() => startLocal(false)}
              disabled={busyLocal || !ds.clips}
              className="rounded border border-border bg-surface-raised px-2 py-1 text-[0.6875rem] font-semibold text-content hover:bg-surface disabled:opacity-50">
              {busyLocal ? 'Starting…' : '▶ Train on this PC'}
            </button>
            <HelpBadge topic="video-train-local" />
            <span ref={setLaunchHost} className="contents" />
          </div>
        </>
      )}

      {localActive && (
        <p className="text-[0.6875rem] text-content-muted">
          {dl
            ? `Downloading weights — ${dl.percent ?? 0}%`
            : progress.step != null
              ? `Step ${progress.step}${progress.total ? ` / ${progress.total}` : ''}${progress.loss != null ? ` · loss ${progress.loss}` : ''}${progress.eta ? ` · ${progress.eta} left` : ''}`
              : 'Starting up…'}
        </p>
      )}

      {!localActive && !PROVEN_TARGETS.has(ds.target_profile) && (
        <p className="text-[0.6875rem] text-content-subtle">
          {ds.target_label} is wired from ai-toolkit’s own settings but has not
          been trained end to end yet.
        </p>
      )}
      {/* On the card, not only in the toast after launching: a warning that
          arrives once the run is up is a warning about a decision already made. */}
      {!localActive && progress?.resolution_note && (
        <p className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1 text-[0.6875rem] text-amber-100">
          ⚠ {progress.resolution_note}
        </p>
      )}
      {!!progress?.checkpoints?.length && (
        <p className="text-[0.6875rem] text-content-muted">
          {progress.checkpoints.length} saved checkpoint
          {progress.checkpoints.length === 1 ? '' : 's'} in {progress.run_name}
        </p>
      )}

      <PluginSlot slot="training.launch" surface="video"
        ds={ds} steps={steps} doI2v={doI2v} confirmLicence={confirmLicence}
        cloudUrl={`/api/video-dataset/${ds.id}/train/cloud`}
        preflightUrl={`/api/video-dataset/${ds.id}/train/preflight?lane=cloud`}
        launchHost={launchHost} localActive={localActive}
        onSaveCount={setCloudSaveCount} refreshKey={refreshKey} />
    </section>
  )
}
