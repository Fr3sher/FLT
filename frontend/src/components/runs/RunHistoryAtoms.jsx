import { Folder, Image as ImageIcon } from 'lucide-react'
import { isTrainingRecipeReplayBlocked } from '../../utils/trainingRuns.js'
import { canFetchDenseLocally, canRecheckFullTransformerDelivery, denseHubBackupView, denseLocalArtifactView, fullTransformerArtifactFiles, fullTransformerArtifactView, fullTransformerFp8Note } from '../../utils/trainingMode.js'

const FAMILY_LABEL = { zimage: 'Z-Image', krea: 'Krea 2', sdxl: 'SDXL', flux: 'FLUX.1', flux2klein: 'FLUX.2 Klein', anima: 'Anima', video: 'Video' };

const STATUS_STYLE = {
  done: 'text-emerald-300 border-emerald-400/40 bg-emerald-500/10',
  error: 'text-rose-300 border-rose-400/40 bg-rose-500/10',
  error_pod_kept: 'text-amber-200 border-amber-400/40 bg-amber-500/10',
  stopped: 'text-content-muted border-border bg-surface',
};

const statusStyle = (s) =>
  STATUS_STYLE[s] || 'text-sky-300 border-sky-400/40 bg-sky-500/10';

const STATUS_LABEL = {
  done: 'done',
  error: 'failed',
  error_pod_kept: 'failed · pod kept',
  stopped: 'stopped',
};

const CARD_ACCENT = {
  done: 'border-l-emerald-400/70',
  error: 'border-l-rose-400/70',
  error_pod_kept: 'border-l-amber-400/70',
  stopped: 'border-l-border-strong',
};

export const cardAccent = (s) => CARD_ACCENT[s] || 'border-l-border';

export function StatusBadge({ status }) {
  if (!status) return null;
  return (
    <span className={'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 '
      + `text-[0.625rem] font-semibold uppercase tracking-wide ${statusStyle(status)}`}>
      <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
      {STATUS_LABEL[status] || status}
    </span>
  );
}

export function timeAgo(iso) {
  if (!iso) return '';
  // backend timestamps are naive UTC (isoformat of utcnow) — pin to UTC.
  const t = new Date(/[Z+]/.test(iso) ? iso : `${iso}Z`).getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function famLabel(f) { return FAMILY_LABEL[f] || f || 'LoRA'; }

const FAMILY_SHORT = { zimage: 'Z-Image', krea: 'Krea', sdxl: 'SDXL', flux: 'FLUX', flux2klein: 'Klein', anima: 'Anima' };

export function RunThumb({ run, broken, onBroken }) {
  if (run.preview_url && !broken) {
    return (
      <a href={run.preview_url} target="_blank" rel="noreferrer"
        title="Last sample this run generated (open full size)"
        className="relative block h-16 w-16 sm:h-20 sm:w-20 shrink-0 overflow-hidden rounded-lg border border-border hover:border-indigo-400">
        {/* `?s=` on the img, nothing on the <a>: the card draws a 64-80 px
            square and the hub lists every run ever launched, so downloading a
            full training sample per card was the whole page's weight. The link
            around it still opens the untouched file. */}
        <img src={`${run.preview_url}?s=192`} loading="lazy" decoding="async" onError={onBroken}
          alt={`Last training sample of ${run.dataset_name || run.run_name || 'this run'}`}
          className="h-full w-full object-cover" />
      </a>
    );
  }
  return (
    <div aria-hidden
      className="flex h-16 w-16 sm:h-20 sm:w-20 shrink-0 flex-col items-center justify-center gap-1 rounded-lg border border-border bg-app/60 text-content-subtle">
      <ImageIcon aria-hidden="true" className="h-4 w-4 opacity-50" />
      <span className="px-1 text-center text-[0.5625rem] uppercase tracking-wide leading-tight">
        {FAMILY_SHORT[run.train_type] || 'LoRA'}
      </span>
    </div>
  );
}

export function PodKeptNote({ fullModel = false }) {
  return (
    <div role="alert"
      className="w-full rounded-md border border-amber-400/40 bg-amber-500/10 px-2.5 py-2 text-amber-200 text-[0.6875rem] leading-relaxed">
      <span className="font-semibold">⚠ Pod kept for manual checkpoint recovery</span> — it keeps
      billing until reaped. {fullModel
        ? 'Verify or recover the full-model weights on Hugging Face before the recovery window expires.'
        : 'Download its LoRA, then it is cleaned up automatically after the recovery window.'}
    </div>
  );
}

const FULL_ARTIFACT_TONE = {
  success: 'border-emerald-400/40 bg-emerald-500/10 text-emerald-100',
  error: 'border-rose-400/45 bg-rose-500/10 text-rose-100',
  warning: 'border-amber-400/45 bg-amber-500/10 text-amber-100',
  info: 'border-sky-400/40 bg-sky-500/10 text-sky-100',
};

function DenseLocalStatus({ run, onFetch, fetching = false }) {
  const view = denseLocalArtifactView(run);
  if (!view) return null;
  const canFetch = canFetchDenseLocally(run) && !!onFetch;
  return (
    <div role={view.tone === 'warning' ? 'alert' : 'status'}
      className={`w-full rounded-md border px-2.5 py-2 text-[0.6875rem] leading-relaxed ${FULL_ARTIFACT_TONE[view.tone]}`}>
      <span className="font-semibold">{view.label}</span>
      <span className="block opacity-90">{view.detail}</span>
      {view.dir && (
        <span className="block break-all opacity-80" title="Folder on this computer">
          <Folder aria-hidden="true" className="mr-1 inline h-3.5 w-3.5 align-[-2px]" /><span className="font-mono">{view.dir}</span>
        </span>
      )}
      {/* Which of the two files to take. They are not interchangeable: the fp8
          one is what ComfyUI loads, the master is the only one that can be
          trained again. */}
      {view.available && fullTransformerArtifactFiles(run).map((file) => (
        <span key={file.kind} className="block opacity-90">
          {file.primary ? '★ ' : '· '}
          <span className="font-mono break-all">{file.name}</span> — {file.note}
        </span>
      ))}
      {view.available && run.inference_hint?.note && (
        <span className="block opacity-90">⚠ {run.inference_hint.note}</span>
      )}
      {(canFetch || fetching) && (
        <button type="button" onClick={() => onFetch(run, fetching)}
          className="mt-1.5 block rounded-md border border-sky-300/50 bg-sky-400/10 px-2.5 py-1 font-semibold text-sky-50 hover:bg-sky-400/20">
          {fetching ? 'Stop fetching (what landed is kept)' : 'Fetch to this computer'}
        </button>
      )}
    </div>
  );
}

export function FullArtifactStatus({ run, onRecheck, rechecking = false,
  onFetch, fetching = false, presence = null }) {
  const local = denseLocalArtifactView(run);
  const backup = denseHubBackupView(run, presence);
  // A run delivered here keeps its Hugging Face block only as a BACKUP note:
  // "Full model not found" would be a lie about a model sitting on the disk.
  const view = backup || (local ? null : fullTransformerArtifactView(run, presence));
  const canRecheck = canRecheckFullTransformerDelivery(run) && !!onRecheck;
  if (!view) {
    return <DenseLocalStatus run={run} onFetch={onFetch} fetching={fetching} />;
  }
  return (
    <>
      <DenseLocalStatus run={run} onFetch={onFetch} fetching={fetching} />
      <div role={view.tone === 'error' || view.tone === 'warning' ? 'alert' : 'status'}
        className={`w-full rounded-md border px-2.5 py-2 text-[0.6875rem] leading-relaxed ${FULL_ARTIFACT_TONE[view.tone]}`}>
        <span className="font-semibold">{view.label}</span>
        <span className="block opacity-90">{view.detail}</span>
        {/* Which of the delivered files to take. Without this the repository shows
            two objects with nearly the same name, one of which is 26 GB. */}
        {!local && fullTransformerArtifactFiles(run).map((file) => (
          <span key={file.kind} className="block opacity-90">
            {file.primary ? '★ ' : '· '}
            <span className="font-mono break-all">{file.name}</span> — {file.note}
          </span>
        ))}
        {fullTransformerFp8Note(run) && (
          <span className="block opacity-80">ℹ {fullTransformerFp8Note(run)}</span>
        )}
        {!local && view.available && run.inference_hint?.note && (
          <span className="block opacity-90">⚠ {run.inference_hint.note}</span>
        )}
        {view.href && (
          <a href={view.href} target="_blank" rel="noreferrer"
            className="mt-1 inline-block font-semibold text-sky-200 underline hover:text-sky-100">
            Open private model on Hugging Face ↗
          </a>
        )}
        {!view.href && view.repositoryHref && (
          <a href={view.repositoryHref} target="_blank" rel="noreferrer"
            title="This link only opens the repository; the model weights have not been verified yet"
            className="mt-1 inline-block font-semibold text-amber-100 underline hover:text-white">
            Inspect Hugging Face repository (delivery not verified) ↗
          </a>
        )}
        {canRecheck && (
          <button type="button" onClick={() => onRecheck(run)} disabled={rechecking}
            className="mt-1.5 block rounded-md border border-amber-300/50 bg-amber-400/10 px-2.5 py-1 text-amber-50 font-semibold hover:bg-amber-400/20 disabled:opacity-40">
            {rechecking
              ? (view.cleanupPending ? 'Cleaning up pod…' : 'Verifying Hugging Face delivery…')
              : (view.cleanupPending ? 'Retry pod cleanup' : 'Verify Hugging Face delivery')}
          </button>
        )}
      </div>
    </>
  );
}

export function AutoRetryBadges({ run }) {
  return (
    <>
      {run.auto_retry_of != null && (
        <span
          className="rounded border border-sky-400/40 bg-sky-500/10 px-1.5 py-0.5 text-sky-200 text-[0.625rem]"
          title={`Automatic retry of cloud run #${run.auto_retry_of}`}>
          ↻ automatic retry {run.auto_retry_count || 1}/1
        </span>
      )}
      {run.auto_retry_run_id != null && (
        <span
          className="rounded border border-violet-400/40 bg-violet-500/10 px-1.5 py-0.5 text-violet-200 text-[0.625rem]"
          title={`Automatically relaunched as cloud run #${run.auto_retry_run_id}`}>
          ↻ auto-retried as #{run.auto_retry_run_id}
        </span>
      )}
    </>
  );
}

export function RecipeWarning({ run }) {
  if (!run.recipe_warning) return null;
  const replayBlocked = isTrainingRecipeReplayBlocked(run);
  return (
    <div role="alert"
      className="w-full rounded-md border border-amber-400/40 bg-amber-500/10 px-2.5 py-2 text-amber-200 text-[0.6875rem] leading-relaxed">
      <span className="font-semibold">⚠ Z-Image recipe warning:</span> {run.recipe_warning}
      {replayBlocked && (
        <span className="font-semibold"> Retry and Continue are disabled; start a fresh validated run.</span>
      )}
    </div>
  );
}

export function settingsLine(run) {
  const s = run.settings;
  if (!s) return null;
  return [
    s.rank ? `rank ${s.rank}${s.alpha ? `/${s.alpha}` : ''}` : null,
    Array.isArray(s.resolution) ? `${s.resolution.join('+')} px` : null,
    s.save_every ? `save ${s.save_every}` : null,
    s.optimizer && s.optimizer !== 'adamw8bit' ? s.optimizer : null,
    s.lr_scheduler || null,
    s.dropout ? `dropout ${s.dropout}` : null,
    s.timestep_type || null,
    run.masked === false ? 'unmasked' : 'masked',
  ].filter(Boolean).join(' · ');
}

export function checkpointHref(run) {
  if (run.checkpoint_url) return run.checkpoint_url;
  const qs = new URLSearchParams();
  if (run.train_type) qs.set('train_type', run.train_type);
  if (run.variant) qs.set('variant', run.variant);
  // run_id: THIS row's file — with several finished runs of a family in the
  // history, family resolution alone would serve the newest run's checkpoint.
  if (run.run_id) qs.set('run_id', String(run.run_id));
  return `/api/dataset/${run.dataset_id}/train/cloud/checkpoint?${qs.toString()}`;
}
