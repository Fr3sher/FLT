import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Link } from 'react-router';
import { postJsonResult as postJson } from '@lds/plugin-sdk';
import { postJson as postApi } from '@lds/plugin-sdk';
import { useToast } from '@lds/plugin-sdk';
import { SettingsLink } from '@lds/plugin-sdk/ui';
import { TrainingProgress } from '@lds/plugin-sdk/training';
import { stopOutcomeMessage } from '../lib/runSilence.js';
import { cloudTrainingLaunchPayload } from '../lib/trainingSelection.js';
import { postWithConfirmations } from '@lds/plugin-sdk/training';
import { normalizeTrainingMode, TRAINING_MODE_FULL_TRANSFORMER, TRAINING_MODE_LORA, isFullTransformerRun, denseTurboWarning, hfCloudTokenReadiness } from '../lib/trainingModel.js';
import CloudLaunchDialog from './CloudLaunchDialog';
import CloudStopDialog from '../shared/CloudStopDialog.jsx';
import { FullTransformerArtifactNotice } from './FullTransformerRecipe';
import { cloudDisabledReasonFor } from './cloudTraining.js';

export default function DatasetCloudTraining({ ds, form, preflightOk, toastTrainError,
  progressHost, noticeHost, budgetHost, onStateChange }) {
  const toast = useToast();
  const { caps, fullMode, trainType, variant, base, trainingMode, maskedOpt, stepsN,
    allowNotReady, keptCount, denseBaseSummary } = form;
  const denseTurboNotice = denseTurboWarning({ baseModel: base, variant });
  const [hfCloudTokenIssue, setHfCloudTokenIssue] = useState(null);
  const validateReport = (report) => {
    if (!fullMode) return true;
    const readiness = hfCloudTokenReadiness(report);
    if (readiness.blocked) {
      setHfCloudTokenIssue(readiness.detail || 'HF_CLOUD_TOKEN is missing, invalid, or does not have the required permissions.');
      return false;
    }
    if (readiness.signaled) setHfCloudTokenIssue(null);
    return true;
  };
  // Cloud run status (global — several cloud runs may be active at once,
  // across different datasets, up to cloudStatus.limit). Polled independently
  // of the local `status` poll above, and only while a vast.ai key is
  // actually configured.
  const [cloudStatus, setCloudStatus] = useState({
    configured: false, limit: 1, actives: [], active: null, total_price_per_hour: 0, last: null,
  });
  useEffect(() => {
    if (!caps.cloud_training) return undefined;
    let alive = true;
    let t;
    const tick = async () => {
      try {
        const r = await fetch('/api/dataset/train/cloud/status', { credentials: 'include' });
        if (r.ok && alive) setCloudStatus(await r.json());
      } catch { /* transient */ }
      if (alive) t = setTimeout(tick, 5000);
    };
    t = setTimeout(tick, 0);
    return () => { alive = false; clearTimeout(t); };
  }, [caps.cloud_training]);
  // Compat: older servers (or a stale poll) may still answer with only the
  // single `active` field — fall back to a 1-element list built from it.
  const actives = cloudStatus.actives || (cloudStatus.active ? [cloudStatus.active] : []);
  // Per-(dataset, family) as before — but PLURAL now: two same-family runs may
  // train this dataset at once (settings A/B). A run without train_type (older
  // server payload) matches any family, preserving the previous behavior.
  const cloudActivesHere = actives.filter((a) => a.dataset_id === ds.currentId
    && (!a.train_type || a.train_type === trainType));
  // Which of them the card + progress + checkpoint link follow. View state
  // only (never server state): defaults to the newest, snaps back when the
  // selected run leaves the active list.
  const [selectedCloudRunId, setSelectedCloudRunId] = useState(null);
  const [cloudStopTarget, setCloudStopTarget] = useState(null);
  const cloudActiveHere = cloudActivesHere.find((a) => a.run_id === selectedCloudRunId)
    || cloudActivesHere[cloudActivesHere.length - 1] || null;
  // Same dialog the Runs hub uses: stopping from THIS panel used to skip the
  // "Do not rent this machine again" tick, which is the option you want when
  // a pod is stuck on boot and you are watching it here rather than on Runs.
  const doStopCloud = async (run, { banHost = false } = {}) => {
    if (!run) return;
    setCloudStopTarget(null);
    const d = await postJson('/api/dataset/train/cloud/stop',
      banHost ? { run_id: run.run_id, ban_host: true } : { run_id: run.run_id });
    // Never leave a stop unanswered: a pod that could not be terminated keeps
    // billing, and the message names the instance.
    const m = stopOutcomeMessage(d);
    if (m.level === 'error') toast.error(m.text, 20000);
    else toast.info(m.text, m.level === 'warn' ? 12000 : undefined);
  };
  const cloudLastHere = cloudStatus.last
    && cloudStatus.last.dataset_id === ds.currentId
    && (!cloudStatus.last.train_type || cloudStatus.last.train_type === trainType)
    ? cloudStatus.last
    : null;

  const cloudDisabledReason = cloudDisabledReasonFor(form, cloudStatus);
  useEffect(() => {
    onStateChange({ datasetId: ds.currentId, trainType, active: cloudActiveHere, last: cloudLastHere, status: cloudStatus });
  }, [ds.currentId, trainType, cloudActiveHere, cloudLastHere, cloudStatus, onStateChange]);
  // Launch-time GPU speed picker: the ☁️ button opens a dialog that lists live
  // vast.ai offers by speed (price/h + approx time + cost); the chosen class is
  // forwarded as gpu_name. launchCloud carries the POST + the MISMATCH_CAPTION
  // retry that used to live inline in the button handler.
  const [cloudDialog, setCloudDialog] = useState(false);
  const launchCloud = async (gpuName) => {
    // A cloud launch spends real money, so it gets the SAME sanity gate as a local
    // one — minus the rows about this machine's GPU, which no rented pod will use.
    if (!(await preflightOk({ lane: 'cloud', validateReport }))) return false;
    let body = {
      ...cloudTrainingLaunchPayload({
        baseModel: base, variant, trainType, trainingMode,
        masked: maskedOpt, steps: stepsN, gpuName,
      }),
      ...(allowNotReady ? { allow_not_ready: true } : {}),
    };
    // postWithConfirmations, NOT a hand-rolled loop on `d.ok === false`.
    //
    // That loop could never run. Every confirmable refusal leaves the service as a
    // RuntimeError, which the route maps to HTTP 409 with `{error: "..."}` -- a
    // body carrying no `ok` key at all -- and postJson THROWS on any non-2xx
    // rather than returning it. So the await raised, everything below it was dead
    // code, and the user got the raw refusal text as an error toast with no way to
    // answer the question it was asking. Reported on the parallel-run one: "I
    // still cannot run two trainings on the same dataset", on an install whose
    // backend supported it perfectly.
    //
    // This helper is what the Runs hub and the canvas already use for these same
    // refusals: it catches, asks, and retries carrying the flag -- and refuses to
    // ask twice for a flag it already sent, so a refusal that survives its own
    // confirmation ends instead of looping.
    let d;
    try {
      d = await postWithConfirmations(
        (b) => postApi(`/api/dataset/${ds.currentId}/train/cloud`, b),
        body, 'Train anyway (force)');
    } catch (e) {
      toastTrainError({ ...(e?.body || {}), error: e?.message }, 'Cloud training failed');
      return false;
    }
    // The dialog closes on success and the panel's own launch view only appears
    // on the next 5 s poll — a silent close read as "nothing happened". Name the
    // run that now exists and where its launch steps are visible.
    if (d) {
      toast.info(d.run_id != null
        ? `Cloud run #${d.run_id} created — follow its launch on the Runs page.`
        : 'Cloud run created — follow its launch on the Runs page.');
    }
    return !!d;
  };

  return (<>
        {(caps.cloud_training || fullMode) && (
          <button type="button"
            disabled={!!cloudDisabledReason}
            title={cloudDisabledReason
              || 'Rents a vast.ai GPU for this run (~$1-2), auto-terminated'}
            onClick={() => {
              setHfCloudTokenIssue(null);
              setCloudDialog(true);
            }}
            className="px-3 py-1.5 rounded-lg border border-sky-500/50 bg-sky-500/10 text-sky-200 text-sm font-semibold disabled:opacity-40">
            <span aria-hidden>☁️</span> {fullMode ? 'Start full-model training' : 'Train in cloud'}
          </button>
        )}
      {cloudDialog && (
        <CloudLaunchDialog
          datasetId={ds.currentId} trainType={trainType} variant={variant}
          trainingMode={trainingMode}
          base={base} steps={stepsN}
          keptCount={keptCount} cloudStatus={cloudStatus}
          preflightTokenIssue={hfCloudTokenIssue}
          onClose={() => setCloudDialog(false)} onLaunch={launchCloud} />
      )}

      {/* Same dialog as the Runs hub, portaled for the same reason as Continue
          above: a modal opened from Training must still be seen if the
          workspace has switched section. */}
      {createPortal((
        <CloudStopDialog run={cloudStopTarget}
          fullModel={!!cloudStopTarget && isFullTransformerRun(cloudStopTarget)}
          onCancel={() => setCloudStopTarget(null)}
          onConfirm={({ banHost }) => doStopCloud(cloudStopTarget, { banHost })} />
      ), document.body)}

    {progressHost && createPortal(<>      {/* A cloud run left its pod alive for manual recovery (any dataset) — it
          keeps billing until reaped, so this must stay visible regardless of
          which dataset's panel happens to be open. No action button: the
          recovery is manual (outside the app) and expiry-reaping is automatic. */}
      {cloudStatus.last?.status === 'error_pod_kept' && (
        <p className="m-0 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-amber-300 text-[0.6875rem]">
          ⚠ A previous cloud run kept its pod for manual recovery — it is still billing until reaped. {cloudStatus.last.error}
        </p>
      )}

      {/* Cloud run progress + stop (this dataset only) — separate from the local
          poll above; runs entirely on the vast.ai pod. */}
      {cloudActivesHere.length > 1 && (() => {
        // Two runs whose frozen dataset generations differ are NOT a settings
        // A/B any more — mark the odd ones out against the newest run.
        const newestFp = cloudActivesHere[cloudActivesHere.length - 1]?.dataset_fingerprint;
        return (
          <div className="flex items-center gap-1 flex-wrap" role="tablist"
            aria-label="Active cloud runs on this dataset">
            {cloudActivesHere.map((a) => {
              const selected = a.run_id === cloudActiveHere?.run_id;
              const diverges = Boolean(a.dataset_fingerprint && newestFp
                && a.dataset_fingerprint !== newestFp);
              return (
                <button key={a.run_id} type="button" role="tab" aria-selected={selected}
                  onClick={() => setSelectedCloudRunId(a.run_id)}
                  title={diverges
                    ? 'This run trains a different dataset generation than its sibling — the runs are not comparing settings on the same data.'
                    : `Cloud run #${a.run_id} — ${a.status}`}
                  className={`rounded-full border px-2 py-0.5 text-[0.6875rem] tabular-nums ${
                    selected
                      ? 'border-sky-400/60 bg-sky-500/15 text-sky-200'
                      : 'border-border bg-surface text-content-muted hover:text-content'}`}>
                  ☁ #{a.run_id} · {a.status}{diverges ? ' ⚠' : ''}
                </button>
              );
            })}
          </div>
        );
      })()}
      {cloudActiveHere && (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-[0.6875rem] text-sky-200 flex-wrap">
            <span aria-hidden>☁️</span>
            <span className="font-semibold">Cloud run — {cloudActiveHere.status}</span>
            {cloudActivesHere.length > 1 && (() => {
              const fps = new Set(cloudActivesHere.map((a) => a.dataset_fingerprint).filter(Boolean));
              return fps.size > 1 ? (
                <span className="text-amber-300">⚠ different dataset generation</span>
              ) : null;
            })()}
            {cloudActiveHere.gpu && <span>{cloudActiveHere.gpu}</span>}
            {cloudActiveHere.price_per_hour != null && (
              <span className="tabular-nums">${cloudActiveHere.price_per_hour}/h · ~${cloudActiveHere.cost_estimate} so far</span>
            )}
            {/* Full progress bar, loss curve and samples live on the Runs hub. */}
            <Link to="/cloud" title="Open the Runs page — full progress, loss curve and samples"
              className="ml-auto min-h-10 lg:min-h-0 inline-flex items-center px-1 py-0.5 text-sky-300 hover:text-sky-200 font-medium underline decoration-sky-300/40">
              View in Runs ↗
            </Link>
            <button type="button" className="px-2 py-0.5 rounded bg-red-600/80 text-white text-[0.6875rem] font-semibold"
              onClick={() => setCloudStopTarget(cloudActiveHere)}>
              Stop cloud run
            </button>
          </div>
          <TrainingProgress datasetId={ds.currentId}
            base={cloudActiveHere.base_model ?? ''}
            trainType={cloudActiveHere.train_type || trainType}
            variant={cloudActiveHere.variant || variant} cloud
            runId={cloudActiveHere.run_id} />
          {normalizeTrainingMode(cloudActiveHere.training_mode) === TRAINING_MODE_FULL_TRANSFORMER && (
            <FullTransformerArtifactNotice run={cloudActiveHere} />
          )}
        </div>
      )}
      {/* Download link only when the LAST run matches the selected family
          (a legacy payload without train_type matches any family). Keeping it
          keyed on cloudStatus.last stays simple — per-family history is
          served by ?train_type= on the checkpoint route itself. */}
      {caps.cloud_training && !fullMode && !cloudActiveHere && cloudLastHere
        && normalizeTrainingMode(cloudLastHere.training_mode) === TRAINING_MODE_LORA
        && cloudLastHere.checkpoint_ready && cloudLastHere.status === 'done' && (
        <a href={`/api/dataset/${ds.currentId}/train/cloud/checkpoint?train_type=${encodeURIComponent(trainType)}`}
          className="text-sky-300 text-[0.6875rem] underline w-fit">
          ⬇ Download the cloud-trained LoRA (.safetensors)
        </a>
      )}
      {!cloudActiveHere && cloudLastHere
        && normalizeTrainingMode(cloudLastHere.training_mode) === TRAINING_MODE_FULL_TRANSFORMER && (
        <FullTransformerArtifactNotice run={cloudLastHere} />
      )}

</>, progressHost)}
    {noticeHost && createPortal(<>      {fullMode && (
        <div role="status" className="rounded-lg border border-sky-400/45 bg-sky-500/10 px-3 py-2 text-[0.75rem] leading-relaxed">
          <div className="font-semibold text-sky-100">Experimental · advanced cloud mode · not recommended by default</div>
          <p className="m-0 mt-1 text-sky-200/90">
            Krea officially recommends training a LoRA on Raw, then applying it to Turbo.
            Full-model training requires a much larger, more diverse dataset, an 80 GB GPU,
            and at least 200 GB of disk.
          </p>
          <p className="m-0 mt-1 text-amber-100/95">
            The ~26 GB model is uploaded using a dedicated <code>HF_CLOUD_TOKEN</code>. A tightly scoped
            fine-grained token is recommended: read access only to the Krea 2 base this run uses
            ({denseBaseSummary}) and write access to a single dedicated Hugging Face namespace
            containing only LDS deliveries. A global write token is also
            accepted with a warning. Configure it in{' '}
            <SettingsLink pluginId="cloud_training" focus="HF_CLOUD_TOKEN" tone="warning">Cloud training settings</SettingsLink>.
            {' '}Stopping the run or hitting the runtime cap may lose the latest full-model checkpoint if it has not been uploaded.
          </p>
        </div>
      )}

      {/* Turbo in dense mode: allowed, and UNMEASURED. Said here — above the
          launch buttons, before a GPU is rented — and phrased as what is
          unknown. It promises no result and predicts no failure, and it never
          blocks: the product decision is warn and let through. */}
      {fullMode && denseTurboNotice && (
        <div role="status" id="dense-turbo-warning"
          className="rounded-lg border border-amber-400/45 bg-amber-500/[0.09] px-3 py-2 text-[0.75rem] leading-relaxed">
          <div className="font-semibold text-amber-100">⚠ {denseTurboNotice.title}</div>
          <p className="m-0 mt-1 text-amber-100/90">{denseTurboNotice.body}</p>
        </div>
      )}

</>, noticeHost)}
    {budgetHost && createPortal(<>      {/* A disabled ☁ Train-in-cloud button always states WHY, right under the
          button row — the tooltip alone was invisible until hovered, so a greyed
          SDXL cloud button read as an unexplained limit (owner-reported). */}
      {(caps.cloud_training || fullMode) && cloudDisabledReason && (
        <p className="m-0 text-sky-300/90 text-[0.6875rem]">
          ☁ Cloud training unavailable — {cloudDisabledReason}
        </p>
      )}

      {actives.length > 0 && (
        <p className="m-0 text-content-subtle text-[0.625rem]">
          ☁ {actives.length}/{cloudStatus.limit || 1} cloud runs — ${cloudStatus.total_price_per_hour || 0}/h total
        </p>
      )}

</>, budgetHost)}
  </>);
}
