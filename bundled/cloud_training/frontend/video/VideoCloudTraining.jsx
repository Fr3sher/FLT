import { useCallback, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { apiFetch, postJson } from '@lds/plugin-sdk';
import { useToast } from '@lds/plugin-sdk';
import { HelpBadge } from '@lds/plugin-sdk';
import { postWithConfirmations } from '@lds/plugin-sdk/training';
import VideoCloudLaunchDialog from './VideoCloudLaunchDialog'
import { CLOUD_STATUS_URL, preflightGate } from './videoCloudLaunch'
import { isActive, launchBlockedReason, runSummary, canRetry, canContinue } from './videoCloudStatus'

// One set of cloud actions, mounted in the video form's existing button row.
export function VideoCloudActions({ busyCloud, opening, blocked, openCloudDialog,
  run, latestGroup, postCloud, cloudUrl, steps }) {
  return (
    <>
            <button type="button" disabled={busyCloud || opening || Boolean(blocked)}
              onClick={openCloudDialog}
              title={blocked || (opening
                ? 'Checking the set and the account before the offers open…'
                : 'Compare GPU offers with their price, duration and total before renting one')}
              className="min-h-10 lg:min-h-0 rounded border border-border bg-surface-raised px-2 py-1 text-[0.6875rem] font-semibold text-content hover:bg-surface disabled:opacity-40">
              {/* Bare text on purpose: the exact label is an inventoried surface
                  (bankSurfaceInventory reads literal button text). It opens a
                  window now, and it stays "☁ Train in the cloud". */}
              ☁ Train in the cloud
            </button>
            <HelpBadge topic="video-cloud-training" />
            {canRetry(run) && (
              <button type="button" disabled={busyCloud}
                onClick={() => postCloud(`${cloudUrl}/retry`, { run_id: run.run_id },
                  'Relaunched on a fresh pod with the same settings.')}
                className="min-h-10 lg:min-h-0 rounded border border-border bg-surface-raised px-2 py-1 text-[0.6875rem] text-content hover:bg-surface disabled:opacity-40">
                ↻ Retry
              </button>
            )}
            {canContinue(run, latestGroup) && (
              <button type="button" disabled={busyCloud}
                onClick={() => postCloud(`${cloudUrl}/continue`,
                  { run_id: latestGroup.run_id, extra_steps: steps },
                  `Continuing from the last harvested step, +${steps} steps.`)}
                className="min-h-10 lg:min-h-0 rounded border border-border bg-surface-raised px-2 py-1 text-[0.6875rem] text-content hover:bg-surface disabled:opacity-40">
                ▶ Train further
              </button>
            )}

    </>
  )
}

// The cloud state stays mounted while the local line changes state. Only its
// buttons use the shared row; there is still one poller and one launch dialog.
export default function VideoCloudTraining({ ds, steps, doI2v,
  confirmLicence, cloudUrl, preflightUrl, launchHost, localActive, onSaveCount, refreshKey = 0 }) {
  const toast = useToast()
  // Cloud lane.
  const [run, setRun] = useState(null)
  const [groups, setGroups] = useState([])
  const [busyCloud, setBusyCloud] = useState(false)
  // The launch WINDOW — the image lane's dialog, for video: one radio per GPU
  // class with its price, the rough duration and total for this set, the
  // runtime-cap warning, and the month's spend. It replaced an inline <select>
  // that rented a pod on a click with the cost hidden in a closed dropdown.
  const [cloudDialog, setCloudDialog] = useState(false)
  const [cloudStatus, setCloudStatus] = useState(null)
  const [opening, setOpening] = useState(false)

  const refreshCloud = useCallback(async () => {
    try {
      setRun(await apiFetch(`${cloudUrl}/progress`, { background: true }))
    } catch { /* a poll that fails is not worth a toast */ }
    try {
      const d = await apiFetch(`${cloudUrl}/checkpoints`, { background: true })
      setGroups(d.groups || [])
    } catch { setGroups([]) }
  }, [cloudUrl])
  useEffect(() => { refreshCloud() }, [refreshCloud])
  useEffect(() => {
    if (!isActive(run?.status)) return undefined
    const t = setInterval(refreshCloud, 5000)
    return () => clearInterval(t)
  }, [run?.status, refreshCloud])

  const saveCount = groups.reduce((n, g) => n + (g.steps?.length || 0), 0)
  useEffect(() => { onSaveCount?.(saveCount) }, [saveCount, onSaveCount])
  useEffect(() => { if (refreshKey) refreshCloud() }, [refreshKey, refreshCloud])
  const postCloud = async (url, body, okMessage) => {
    // Every caller of this helper rents a pod (launch, retry, continue), so the
    // licence gate lives here once rather than on three buttons. Retries after
    // a first acknowledged launch pass silently — the yes belongs to the
    // profile, and it was already given.
    if (!confirmLicence()) return
    setBusyCloud(true)
    try {
      // The guardrails' `PARALLEL_RUN:` refusal is a QUESTION by contract
      // ("second pod, billed separately — launch anyway?"). Posting bare turned
      // it into a dead error on this lane; the loop relays the answer as
      // allow_parallel_run, exactly as the image lane does.
      const d = await postWithConfirmations((b) => postJson(url, b), body, 'Launch anyway (force)')
      if (d === null) return false                 // declined: nothing rented
      toast.success(okMessage)
      refreshCloud()
      return true
    } catch (e) {
      toast.error(e?.message || 'The cloud run could not be started.')
      return false
    } finally {
      setBusyCloud(false)
    }
  }

  /** ☁ Open the launch window — AFTER the preflight, BEFORE the money.
   *
   * Order matters and each step is a different question: the licence (does
   * the user accept this model's terms — once per profile), the cloud-lane
   * preflight (a blocker stops here and is shown; warnings become ONE confirm,
   * the image lane's rule), then the window with the offers. A preflight that
   * cannot be reached never blocks: the server re-decides on launch. */
  const openCloudDialog = async () => {
    if (!confirmLicence()) return
    setOpening(true)
    try {
      const report = await apiFetch(preflightUrl, { background: true })
        .catch(() => null)
      const gate = preflightGate(report, { lane: 'cloud' })
      if (!gate.ok) {
        toast.error(`Not ready for the cloud — ${gate.blockers.join(' · ')}`)
        return
      }
      if (gate.confirmText && !window.confirm(gate.confirmText)) return
      // Account-wide, for the footer's "this month: $x of $y". Best effort.
      apiFetch(CLOUD_STATUS_URL, { background: true })
        .then((d) => setCloudStatus(d)).catch(() => setCloudStatus(null))
      setCloudDialog(true)
    } finally {
      setOpening(false)
    }
  }

  /** The dialog's own launch: the chosen GPU class rides as gpu_name, and the
   * dialog closes only on a real success (a declined question or a refusal
   * keeps it open, next to the offers that were being compared). */
  const launchCloud = (gpuName) => postCloud(cloudUrl,
    { steps,
      ...(doI2v ? { do_i2v: true } : {}), ...(gpuName ? { gpu_name: gpuName } : {}) },
    'Renting a pod — the panel follows it from here.')

  if (!ds.training_verified) return null
  const blocked = launchBlockedReason(ds, run)
  const latestGroup = groups[0] || null
  return (
    <>
      {launchHost && createPortal(
        <VideoCloudActions busyCloud={busyCloud} opening={opening} blocked={blocked}
          openCloudDialog={openCloudDialog} run={run}
          latestGroup={latestGroup} postCloud={postCloud} cloudUrl={cloudUrl} steps={steps} />,
        launchHost)}
      {!localActive && blocked && (
        <p className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1 text-[0.6875rem] text-amber-100">
          {blocked}
        </p>
      )}

      {run?.run_id && (
        <p className="text-[0.6875rem] text-content-muted">
          ☁ {runSummary(run)}
          {run.phase_detail ? ` — ${run.phase_detail}` : ''}
        </p>
      )}
      {run?.error && (
        <p className="rounded border border-rose-500/60 bg-rose-500/10 px-2 py-1 text-[0.6875rem] text-rose-100">
          {run.error}
        </p>
      )}

      {cloudDialog && (
        <VideoCloudLaunchDialog ds={ds} steps={steps} cloudStatus={cloudStatus}
          onClose={() => setCloudDialog(false)} onLaunch={launchCloud} />
      )}

    </>
  )
}
