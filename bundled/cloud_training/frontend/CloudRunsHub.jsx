import { useCallback, useEffect, useMemo, useState } from 'react';
import { Eraser, FlaskConical } from 'lucide-react';
import { useNavigate } from 'react-router';
import { postJson } from '@lds/plugin-sdk';
import { useToast } from '@lds/plugin-sdk';

import useHubPresence from './shared/useHubPresence.js';
import { TrainingProgress } from '@lds/plugin-sdk/training';
import LaunchProgress from './shared/LaunchProgress.jsx';


import { BaseModelChip, DatasetVersionChip, RunIdChip } from '@lds/plugin-sdk/training';

import { runRowDomId } from '@lds/plugin-sdk/data';
import { isTrainingRecipeReplayBlocked, retryRequest, runBaseModelLabel, runRetryKey } from './lib/cloudRuns.js';
import { postWithConfirmations, retryConfirmableRefusals } from '@lds/plugin-sdk/training';

import { stopButtonLabel } from './lib/launchProgress.js';
import { runSilenceWarning, stopOutcomeMessage } from './lib/runSilence.js';
import CloudStopDialog from './shared/CloudStopDialog.jsx';
import { runsHubContinueLanes } from './lib/continueLanes.js';
import { continuationGpuPicker } from './dataset/continuationGpuPicker.js';
import { vastUrl } from '@lds/plugin-sdk/links';
import { VastLink } from '@lds/plugin-sdk/links';
import { canRecheckFullTransformerDelivery, fullTransformerRecheckOutcome, isFullTransformerRun } from './lib/trainingModel.js';
import { CHECKPOINTS_KEPT, TRASH_REMINDER, purgeAllResultMessage, purgeRunResultMessage, runStagingCleanup } from './lib/stagingCleanup.js';

import { RunsHub, RunsHubContent, FullArtifactStatus, RunStatusBadge as StatusBadge, timeAgo, famLabel, AutoRetryBadges, RecipeWarning, checkpointHref } from '@lds/plugin-sdk/training';
function SilenceWarning({ run }) {
  const warning = runSilenceWarning(run);
  if (!warning) return null;
  const critical = warning.level === 'critical';
  return (
    <div role="alert"
      className={`w-full rounded-md border px-2.5 py-2 text-[0.6875rem] leading-relaxed ${
        critical ? 'border-red-400/50 bg-red-500/10 text-red-200'
          : 'border-amber-400/40 bg-amber-500/10 text-amber-200'}`}>
      <span className="font-semibold">{critical ? '⛔' : '⚠'} Silent run:</span> {warning.text}
    </div>
  );
}

/** Only the cloud transport is contributed. The shared core controller owns
 * the dialog and can continue a saved checkpoint locally with this absent. */
export const cloudRunsContinuation = {
  gpuPicker: continuationGpuPicker,
  availability(run, { data, caps }) {
    return runsHubContinueLanes(run, {
      aitoolkitValid: caps?.aitoolkit?.valid, localActive: data?.local_active,
      actives: data?.actives || [], configured: data?.configured, limit: data?.limit || 1,
    })?.cloud;
  },
  async plan(run) {
    if (run?.run_id == null) return null;
    return postJson('/api/dataset/train/cloud/resume-plan', { run_id: run.run_id });
  },
  submit(run, payload) {
    const body = { extra_steps: payload.extraSteps,
      from_step: payload.fromStep, overrides: payload.overrides,
      resume_mode: payload.resumeMode || 'weights_only',
      ...(payload.gpuName ? { gpu_name: payload.gpuName } : {}),
      ...(payload.transport ? { transport: payload.transport } : {}),
      ...(payload.stateBundleId ? { state_bundle_id: payload.stateBundleId } : {}),
    };
    const url = run.source === 'local'
      ? `/api/dataset/${run.dataset_id}/train/cloud/continue-local`
      : '/api/dataset/train/cloud/continue';
    const selection = run.source === 'local'
      ? { base_model: run.base_model || '', train_type: run.train_type,
        variant: run.variant, masked: run.masked !== false,
        ...(payload.expectedRecordId != null ? { expected_record_id: payload.expectedRecordId } : {}) }
      : { run_id: run.run_id };
    return postWithConfirmations(
      (next) => postJson(url, next), { ...selection, ...body }, 'Continue anyway (force)');
  },
};

export default function CloudRunsHub() {
  return <RunsHub endpoint="/api/dataset/train/cloud/runs" continuation={cloudRunsContinuation}
    render={(host) => <CloudRunsContent host={host} />} />;
}

function CloudRunsContent({ host }) {
  const toast = useToast();
  const navigate = useNavigate();
  const { data, poll, openDataset, openTestStudio, shareConfig } = host;
  const [stopping, setStopping] = useState({});     // run_id -> bool
  // ⏹ Which run's stop dialog is open (null = none). The dialog exists so the
  // confirmation can also carry "do not rent this machine again".
  const [stopTarget, setStopTarget] = useState(null);
  const [recheckingDelivery, setRecheckingDelivery] = useState({});
  // How much disk each run's staging still holds — what the per-run 🧹 names
  // before moving it. Sizing walks thousands of files per run, so it is fetched
  // ON DEMAND (mount, and again after a cleanup) and deliberately NOT folded
  // into the 5 s poll: the hub must stay as light as it is today.
  const [stagingSizes, setStagingSizes] = useState({});   // run_id -> bytes
  const loadStagingSizes = useCallback(async () => {
    try {
      const r = await fetch('/api/dataset/train/cloud/staging-sizes', { credentials: 'include' });
      if (r.ok) {
        const d = await r.json();
        setStagingSizes(d?.sizes || {});
      }
    } catch { /* sizes are a bonus — the cards render fine without them */ }
  }, []);
  useEffect(() => { loadStagingSizes(); }, [loadStagingSizes]);

  // Per-run 🧹. Same trash mechanism and the same sparing rule as the global
  // button (runStagingCleanup mirrors the backend), so a run one spares the
  // other can never take. Sizes are refetched so the card's weight disappears.
  const [purgingRun, setPurgingRun] = useState({});        // run_id -> bool
  const purgeRun = useCallback(async (run) => {
    const info = runStagingCleanup(run, stagingSizes);
    if (!info.available || !window.confirm(info.confirmMessage)) return;
    setPurgingRun((m) => ({ ...m, [run.run_id]: true }));
    try {
      const d = await postJson('/api/dataset/train/cloud/purge-run', { run_id: run.run_id });
      const msg = purgeRunResultMessage(run, d);
      toast[msg.kind === 'success' ? 'success' : 'info'](msg.text);
      await loadStagingSizes();
      poll();
    } catch (e) {
      toast.error(e?.message || 'Could not clean this run');
    } finally {
      setPurgingRun((m) => { const n = { ...m }; delete n[run.run_id]; return n; });
    }
  }, [stagingSizes, loadStagingSizes, poll, toast]);

  // Is each delivered full model STILL on Hugging Face? `artifact_status` is
  // stamped at delivery and never revisited, so this page happily offered "Open
  // private model on Hugging Face ↗" on a repository its owner had deleted.
  // Asked once, after the page has painted, for the dense runs that recorded a
  // repository — every card renders from the record (dated, past tense) until
  // and unless this answers.
  const hubPresence = useHubPresence(
    [...(data?.actives || []), ...(data?.recent || [])]
      .filter((r) => isFullTransformerRun(r) && r.hf_repo_id)
      .map((r) => r.run_id));

  /* The confirm became a real dialog so it could carry one more decision the
     native one never could: "and do not rent this machine again". See
     components/shared/CloudStopDialog.jsx (asked for by mr.arrow on Discord). */
  const stop = (run) => setStopTarget(run);

  const doStop = async (run, { banHost = false } = {}) => {
    setStopTarget(null);
    setStopping((m) => ({ ...m, [run.run_id]: true }));
    try {
      const d = await postJson('/api/dataset/train/cloud/stop',
        banHost ? { run_id: run.run_id, ban_host: true } : { run_id: run.run_id });
      const m = stopOutcomeMessage(d);
      // A failed termination is the expensive case: keep it on screen (the
      // instance id in the text is what the user needs in the vast console).
      if (m.level === 'error') toast.error(m.text, 20000);
      else toast.info(m.text, m.level === 'warn' ? 12000 : undefined);
      poll();
    } catch (e) {
      // Same silent-button class as ↻ Retry (GitHub #23), and the expensive one:
      // a Stop that was refused leaves a pod BILLING. Never let that be quiet.
      toast.error(e?.message
        ? `Could not stop this run: ${e.message} — check the pod in the vast.ai console.`
        : 'Could not stop this run. Check the pod in the vast.ai console — it may still be billing.',
      20000);
    } finally {
      setStopping((m) => ({ ...m, [run.run_id]: false }));
    }
  };

  // A dense upload can finish successfully while the final Hub verification is
  // temporarily unable to authenticate. The pod is deliberately kept in that
  // state; this action rechecks the durable artifact and lets the backend reap
  // the pod only after a positive verification.
  const recheckFullDelivery = async (run) => {
    if (!canRecheckFullTransformerDelivery(run) || recheckingDelivery[run.run_id]) return;
    setRecheckingDelivery((current) => ({ ...current, [run.run_id]: true }));
    try {
      const result = await postJson('/api/dataset/train/cloud/recheck-delivery', {
        run_id: run.run_id,
      });
      const outcome = fullTransformerRecheckOutcome(result);
      if (outcome.kind === 'error') toast.error(outcome.text);
      else if (outcome.kind === 'success') toast.success(outcome.text);
      else toast.info(outcome.text, outcome.kind === 'warning' ? 12000 : undefined);
      if (outcome.kind === 'error') return;
      await poll();
    } catch (error) {
      toast.error(error?.message
        ? `Could not verify the model on Hugging Face: ${error.message}`
        : 'Could not verify the model on Hugging Face. The pod remains available for recovery and may continue billing.');
    } finally {
      setRecheckingDelivery((current) => ({ ...current, [run.run_id]: false }));
    }
  };

  // Bring a kept pod's full model home — or stop a transfer in flight. The
  // request returns immediately: 26 GB is tens of minutes, so the progress the
  // user watches is the run's own phase line, which this page already polls.
  const fetchFullModel = async (run, running) => {
    try {
      await postJson('/api/dataset/train/cloud/fetch-local', {
        run_id: run.run_id, ...(running ? { cancel: true } : {}),
      });
      toast.info(running
        ? 'Stopping the transfer — everything already downloaded is kept, and fetching again continues from there.'
        : 'Downloading the full model to this computer. The pod is kept until the file here is verified.',
      12000);
      await poll();
    } catch (error) {
      toast.error(error?.message
        ? `Could not fetch the full model: ${error.message}`
        : 'Could not fetch the full model. The pod is kept — try again.');
    }
  };

  // ↻ Retry of a failed run: exact same settings as the failed launch
  // (steps/variant/family/masked, + GPU class for cloud). Cloud runs replay
  // their pod params on a fresh pod; a LOCAL run replays its stamped provenance
  // record through launch_training (normal preflight, GPU-collision refusal).
  //
  // A retry is a LAUNCH, so it meets every pre-flight guard a launch meets — and
  // the guards run on the LIVE dataset, not on the one that failed. Until GitHub
  // #23 (1Tomber) this handler had no catch: postJson rejects on a 400 and shows
  // nothing of its own for that status, so a run whose dataset still had an
  // uncaptioned image produced an uncaught promise rejection and a button that
  // visibly did nothing. Now the confirmable refusals get their confirm — the
  // same one Start asks — and everything else gets said out loud.
  const [retrying, setRetrying] = useState({});      // runRetryKey -> bool
  const retry = async (run) => {
    if (isTrainingRecipeReplayBlocked(run)) {
      toast.error('This run uses an incompatible legacy Z-Image recipe. Start a fresh validated run instead.');
      return;
    }
    const req = retryRequest(run);
    if (!req) return;
    const isLocal = run.source === 'local';
    const key = runRetryKey(run);
    setRetrying((m) => ({ ...m, [key]: true }));
    try {
      const d = await postWithConfirmations(
        (body) => postJson(req.url, body), req.body,
        'Retry anyway (force)', retryConfirmableRefusals());
      if (!d) return;                              // declined at a confirm prompt
      toast.success(isLocal
        ? 'Run relaunched locally — watch it under In progress…'
        : 'Run relaunched — provisioning a fresh pod…');
      poll();
    } catch (e) {
      toast.error(e?.message
        ? `Could not retry this run: ${e.message}`
        : 'Could not retry this run. Please try again.');
    } finally {
      setRetrying((m) => ({ ...m, [key]: false }));
    }
  };

  const configured = data?.configured;
  // useMemo: a new [] on every render invalidated the useMemo below on each frame.
  const actives = useMemo(() => data?.actives || [], [data]);
  const limit = data?.limit || 1;
  const budget = data?.monthly_budget || 0;
  const spent = data?.month_spend || 0;

  const cloud = { stagingSizes, recheckFullDelivery, recheckingDelivery,
    hubPresence, fetchFullModel,
    purgeRun, purgingRun, retry, retrying,
    headerExtra: (<>          {/* Escape hatch to the provider: see the pod's own console (billing,
              logs, manual destroy) when something looks off app-side. */}
          <a href={vastUrl('/instances/')} target="_blank" rel="noreferrer"
            className="ml-auto text-xs font-medium text-sky-300 underline hover:text-sky-200">
            Open the vast.ai console ↗
          </a></>),
    notice: (<>      {data && !configured && (
        <div className="rounded-lg border border-border bg-surface p-4 text-content-muted text-sm">
          Cloud training isn’t configured yet. Add your{' '}
          <VastLink className="text-sky-300 underline hover:text-sky-200" /> API key in{' '}
          {/* Land on the section that actually holds the key and the cloud
              guard-rails, not the Settings landing page. */}
          <button type="button" onClick={() => navigate('/plugins/cloud_training/settings')}
            className="text-sky-300 underline hover:text-sky-200">Settings › Training</button>{' '}
          to rent GPUs on demand.
        </div>
      )}

      {configured && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-border bg-surface px-3 py-2 text-sm">
          <span className="text-content">
            <b className="tabular-nums">{actives.length}</b>
            <span className="text-content-muted">/{limit} active</span>
          </span>
          <span className="text-content-muted tabular-nums">
            ${data.total_price_per_hour || 0}/h total
          </span>
          <span className="text-content-muted tabular-nums">
            this month: ${spent.toFixed(2)}{budget > 0 ? ` of $${budget.toFixed(2)}` : ' (no budget cap)'}
          </span>
        </div>
      )}

</>),
    activeContent: (<> {          actives.map((run) => (
            <div key={run.run_id} id={runRowDomId('cloud', run.run_id)}
              className="flex flex-col gap-2 rounded-xl border border-sky-500/30 bg-sky-500/5 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <RunIdChip source="cloud" recordId={run.record_id} cloudId={run.run_id} />
                <button type="button" onClick={() => openDataset(run.dataset_id)}
                  title="Open this dataset"
                  className="text-content font-semibold text-sm hover:underline">
                  {run.dataset_name || run.run_name || `Dataset #${run.dataset_id}`}
                </button>
                <span className="rounded border border-border bg-surface px-1.5 py-0.5 text-content-muted text-[0.625rem] uppercase">
                  {famLabel(run.train_type)}
                </span>
                {/* No variant shown on the active card, so spell the base in
                    full here — official ("Z-Image Turbo") and custom alike. A
                    VIDEO run's base is its target model; the face fallback put
                    "Z-Image" on a MiniMax H3 run. */}
                {run.train_type === 'video'
                  ? (run.target_label ? <BaseModelChip label={{ official: run.target_label }} /> : null)
                  : <BaseModelChip label={runBaseModelLabel(run)} />}
                <DatasetVersionChip version={run.version} />
                <StatusBadge status={run.status} />
                {isFullTransformerRun(run) && (
                  <span className="rounded border border-sky-400/40 bg-sky-500/10 px-1.5 py-0.5 text-sky-100 text-[0.625rem] font-semibold uppercase">
                    full model · experimental
                  </span>
                )}
                <AutoRetryBadges run={run} />
                <span className="text-content-subtle text-[0.625rem]">{timeAgo(run.created_at)}</span>
                <span className="ml-auto text-content-muted text-[0.6875rem] tabular-nums">
                  {run.gpu ? `${run.gpu} · ` : ''}{run.price_per_hour != null ? `$${run.price_per_hour}/h · ` : ''}
                  ~${run.cost_estimate} so far
                </span>
              </div>

              <RecipeWarning run={run} />
              <SilenceWarning run={run} />
              {/* THIS run's launch, read from its own payload — and THIS run's
                  progress, addressed by its own id. The unaddressed poll fell
                  back to the dataset's NEWEST run, which was survivable when a
                  dataset had one active run and wrong the day it had two: a
                  sibling's launch phase (then its steps, loss and samples)
                  rendered under this card's healthy status. */}
              <LaunchProgress launch={run.launch} />
              <TrainingProgress datasetId={run.dataset_id} trainType={run.train_type}
                variant={run.variant} cloud showLaunch={false} runId={run.run_id} />
              {isFullTransformerRun(run) && (
                <FullArtifactStatus run={run} onRecheck={recheckFullDelivery}
                  rechecking={!!recheckingDelivery[run.run_id]}
                  presence={hubPresence[run.run_id] || null}
                  onFetch={fetchFullModel} fetching={!!run.dense_fetch_active} />
              )}

              <div className="flex flex-wrap items-center gap-2">
                {/* A launch has no checkpoint to lose, so the button that ends
                    it must not read like the one that abandons a trained run.
                    Same endpoint either way: the boot wait honours the stop and
                    destroys the pod (there is no job yet to rescue). */}
                <button type="button" onClick={() => stop(run)} disabled={stopping[run.run_id]}
                  title={stopButtonLabel(run.status) === 'Cancel launch'
                    ? 'Give up this launch and release the machine — nothing has been trained yet'
                    : 'Stop this run; checkpoints already synced are kept'}
                  className="px-3 py-1.5 rounded-lg bg-red-600/80 text-white text-xs font-semibold disabled:opacity-40">
                  {stopping[run.run_id] ? 'Stopping…' : stopButtonLabel(run.status)}
                </button>
                {/* saves counts THIS run's harvested checkpoints. A
                    continuation mirrors its SEED file before step one, which
                    made this button offer the parent's weights during
                    "Starting up…" — a download that is not what it claims. */}
                {!isFullTransformerRun(run) && run.checkpoint_ready
                  && (run.saves || 0) > 0 && (
                  <a href={checkpointHref(run)}
                    className="px-3 py-1.5 rounded-lg border border-emerald-400/40 bg-emerald-500/10 text-emerald-200 text-xs font-semibold no-underline">
                    ⬇ Download the LoRA
                  </a>
                )}
                {run.share_key && (
                  <button type="button" onClick={() => shareConfig(run)}
                    title="Download this run's full settings as a paste-safe text file (recipe / help thread)"
                    className="px-2 py-1.5 rounded-lg border border-border bg-surface text-content-muted hover:text-content text-xs font-semibold">
                    ⎘ Share config
                  </button>
                )}
                <span className="ml-auto flex items-center gap-2">
                  {/* Per-run escape hatch to this pod's provider console (billing,
                      logs, manual destroy). The vast instance id, when known, goes
                      in the tooltip so it's findable in the console's instance list. */}
                  <a href={vastUrl('/instances/')} target="_blank" rel="noreferrer"
                    title={run.vast_instance_id
                      ? `vast.ai instance ${run.vast_instance_id} — provider console (billing, logs, manual destroy)`
                      : 'vast.ai console — billing, logs, manual destroy'}
                    className="px-2 py-1 rounded-lg text-sky-300 hover:text-sky-200 text-xs no-underline">
                    vast.ai console ↗
                  </a>
                  <button type="button" onClick={() => openDataset(run.dataset_id)}
                    className="px-2 py-1 rounded-lg text-content-muted hover:text-content text-xs">
                    Open dataset ↗
                  </button>
                  {!isFullTransformerRun(run) && run.dataset_id != null && (
                    <button type="button" onClick={() => openTestStudio(run.dataset_id)}
                      title="Open Test Studio with this run's dataset selected"
                      className="px-2 py-1 rounded-lg text-indigo-200 hover:bg-indigo-500/10 hover:text-indigo-100 text-xs font-semibold">
                      <FlaskConical aria-hidden="true" className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />Test in Studio
                    </button>
                  )}
                </span>
              </div>
            </div>
          ))} </>),
    historyAction: (<>            {true && (
              <button type="button"
                onClick={async () => {
                  if (!window.confirm(`Clean the staging folders of all FINISHED runs?\n\nThis moves their dataset copies, sample images and logs to the trash. Active runs, and pods still inside their recovery window, are spared.\n${CHECKPOINTS_KEPT}\n${TRASH_REMINDER}`)) return;
                  // No catch here meant a refused purge threw past the refresh
                  // below AND said nothing (GitHub #23's defect class again).
                  try {
                    const d = await postJson('/api/dataset/train/cloud/purge', {});
                    if (d.ok) {
                      // "62.6 GB moved to the trash" on its own reads as "space
                      // reclaimed" — it is not, the trash is on the same disk. And
                      // "Cleaned 0 run(s)" said nothing about WHY. Both fixed here.
                      const msg = purgeAllResultMessage(d);
                      toast[msg.kind === 'error' ? 'error' : msg.kind === 'success' ? 'success' : 'info'](msg.text);
                    }
                  } catch (e) {
                    toast.error(e?.message || 'Could not clean the finished runs.');
                  }
                  await loadStagingSizes();
                  poll();
                }}
                className="ml-auto px-2.5 py-1 rounded-lg bg-red-500/10 border border-red-500/30 text-red-200 text-xs font-semibold">
                <Eraser aria-hidden="true" className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />Clean finished runs
              </button>
            )}</>),
    dialogs: (<>
      <CloudStopDialog run={stopTarget}
        fullModel={!!stopTarget && isFullTransformerRun(stopTarget)}
        onCancel={() => setStopTarget(null)}
        onConfirm={({ banHost }) => doStop(stopTarget, { banHost })} /></>),
  };
  return <RunsHubContent host={host} cloud={cloud} />;
}
