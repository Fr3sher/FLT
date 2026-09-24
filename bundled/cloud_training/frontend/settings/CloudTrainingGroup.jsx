import { useEffect, useState } from 'react'
import { Card, INPUT_CLASS, SecretField } from '@lds/plugin-sdk/ui';
import { ResetToDefault } from '@lds/plugin-sdk/ui';
import { defaultValueAt } from '@lds/plugin-sdk/data';
import { vastReferralId, vastSignupUrl } from '@lds/plugin-sdk/links';
import { VastReferralDisclosure } from '@lds/plugin-sdk/links';
import { VastLink } from '@lds/plugin-sdk/links';

/* First-time walkthrough, collapsed for users who already have a key.
   Every provider link uses the common referral builder; the disclosure's
   referral disclosure stays directly below the signup instructions. */
export function VastKeyGuide({ referralId = vastReferralId() } = {}) {
  const link = 'font-medium text-sky-300 underline hover:text-sky-200'
  const signup = vastSignupUrl(referralId)
  return (
    <details className="mb-2 rounded-lg border border-border bg-surface px-3 py-2 open:pb-3">
      <summary className="cursor-pointer select-none text-xs font-medium text-content">
        <span aria-hidden>📖</span> How to get a vast.ai API key (≈2 minutes)
      </summary>
      <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-xs text-content-muted">
        <li>
          Create a free account at{' '}
          <a href={signup} target="_blank" rel="noreferrer" className={link}>cloud.vast.ai</a>
          {' '}(email or Google sign-in).
        </li>
        <li>
          Add credit: open{' '}
          <VastLink path="/billing/" referralId={referralId} className={link}>Billing</VastLink>
          {' '}in the left sidebar and click <strong>Add Credit</strong> — $5 is plenty to
          start (a typical training run costs ~$1–2, billed by{' '}
          <VastLink referralId={referralId} className={link} />, not by this app).
        </li>
        <li>
          Open{' '}
          <VastLink path="/manage-keys/" referralId={referralId} className={link}>Keys</VastLink>
          {' '}(left sidebar, under Account) and copy your API key — create one first if
          the list is empty.
        </li>
        <li>
          Paste the key in the field below and press <strong>Test</strong> — it saves the
          key automatically and should answer “connected as &lt;your account&gt;”.
        </li>
      </ol>
      <VastReferralDisclosure referralId={referralId} linkClass={link} className="mt-2 text-xs text-content-muted" />
    </details>
  )
}

const VAST_SECRET = {
  key: 'VAST_API_KEY', label: 'vast.ai API key', testTarget: 'vast',
  help: 'Enables cloud GPU training: the app rents a GPU for the run and shuts it down when done (typical run: $1-2). Get a key at cloud.vast.ai → Keys.',
  guide: <VastKeyGuide />,
}

function CloudOfferFilter({ id, label, help, checked, onChange }) {
  return (
    <div className="flex items-start justify-between gap-4 rounded-lg border border-border bg-surface-raised px-3 py-2.5">
      <div>
        <p id={`${id}-label`} className="text-sm font-medium text-content">{label}</p>
        <p id={`${id}-help`} className="mt-0.5 text-xs text-content-muted">{help}</p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-help`}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? 'bg-emerald-500' : 'border border-border-strong bg-surface'}`}
      >
        <span
          aria-hidden
          className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : 'translate-x-0'}`}
        />
      </button>
    </div>
  )
}

/* Cloud training limits: concurrency cap, offer price ceiling, monthly budget
   and the stall watchdog timeout. Fetches the cloud status ONCE on mount for
   the "Spent this month" info line — no poll, this page is not a dashboard. */
function CloudTrainingCard({ config, setField, configDefaults }) {
  // Every shipped value below is read from the server payload (config_defaults),
  // never retyped: these guardrails move between releases.
  const dflt = (key) => defaultValueAt(configDefaults, 'cloud', key)
  const [spend, setSpend] = useState(null)
  const verifiedOnly = config.cloud?.verified_only ?? true
  const secureCloudOnly = config.cloud?.secure_cloud_only ?? false
  useEffect(() => {
    let alive = true
    // Raw fetch (not apiFetch): this info line is best-effort — a transient
    // 500 must not fire the global error toast over a cosmetic detail.
    fetch('/api/dataset/train/cloud/status', { credentials: 'include' })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive && d && typeof d.month_spend === 'number') setSpend(d.month_spend) })
      .catch(() => { /* info line is best-effort */ })
    return () => { alive = false }
  }, [])
  return (
    <Card title="Cloud training" help="vast.ai GPU rental guardrails — how many training pods may run at once, the offer price ceiling, your monthly spend limit, and the watchdogs that end a run that has stopped making progress. A pod that is still downloading its base model IS making progress: those budgets are judged on its byte counter, not on the training step it has not reached yet.">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label htmlFor="cloud-max-concurrent-runs" className="block text-sm font-medium text-content">
            Max simultaneous cloud runs
          </label>
          <input
            id="cloud-max-concurrent-runs"
            type="number"
            min="1"
            max="10"
            step="1"
            value={config.cloud?.max_concurrent_runs ?? dflt('max_concurrent_runs')}
            onChange={(e) => setField('cloud', 'max_concurrent_runs', parseInt(e.target.value) || dflt('max_concurrent_runs'))}
            className={INPUT_CLASS}
          />
          <ResetToDefault label="Max simultaneous cloud runs" section="cloud" field="max_concurrent_runs"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-max-price-per-hour" className="block text-sm font-medium text-content">
            Max price per hour ($)
          </label>
          <input
            id="cloud-max-price-per-hour"
            type="number"
            min="0.1"
            max="5"
            step="0.05"
            value={config.cloud?.max_price_per_hour ?? dflt('max_price_per_hour')}
            onChange={(e) => setField('cloud', 'max_price_per_hour', Math.max(0.1, parseFloat(e.target.value) || 0.1))}
            className={INPUT_CLASS}
          />
          <ResetToDefault label="Max price per hour" section="cloud" field="max_price_per_hour"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-monthly-budget" className="block text-sm font-medium text-content">
            Monthly budget ($, 0 = unlimited)
          </label>
          <input
            id="cloud-monthly-budget"
            type="number"
            min="0"
            step="1"
            value={config.cloud?.monthly_budget_usd ?? dflt('monthly_budget_usd')}
            onChange={(e) => setField('cloud', 'monthly_budget_usd', parseFloat(e.target.value) || 0)}
            className={INPUT_CLASS}
          />
          <ResetToDefault label="Monthly budget" section="cloud" field="monthly_budget_usd"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-stall-timeout" className="block text-sm font-medium text-content">
            Stall timeout (minutes)
          </label>
          <input
            id="cloud-stall-timeout"
            type="number"
            min="5"
            max="240"
            step="1"
            value={config.cloud?.stall_timeout_minutes ?? dflt('stall_timeout_minutes')}
            onChange={(e) => setField('cloud', 'stall_timeout_minutes', parseInt(e.target.value) || dflt('stall_timeout_minutes'))}
            className={INPUT_CLASS}
          />
          <ResetToDefault label="Stall timeout" section="cloud" field="stall_timeout_minutes"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-first-step-timeout" className="block text-sm font-medium text-content">
            First-step timeout (minutes)
          </label>
          <input
            id="cloud-first-step-timeout"
            type="number"
            min="5"
            max="240"
            step="1"
            value={config.cloud?.first_step_timeout_minutes ?? dflt('first_step_timeout_minutes')}
            onChange={(e) => setField('cloud', 'first_step_timeout_minutes', parseInt(e.target.value) || dflt('first_step_timeout_minutes'))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-[0.6875rem] text-content-subtle">
            Before training starts, the pod downloads its base model. This is the idle budget for that phase — the clock restarts every time the pod reports more downloaded bytes, so a slow-but-working download is never cut. Only a pod that reports nothing at all for this long is terminated.
          </p>
          <ResetToDefault label="First-step timeout" section="cloud" field="first_step_timeout_minutes"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-first-step-download-budget" className="block text-sm font-medium text-content">
            Base-model download ceiling (minutes, 0 = none)
          </label>
          <input
            id="cloud-first-step-download-budget"
            type="number"
            min="0"
            max="480"
            step="1"
            value={config.cloud?.first_step_download_budget_minutes ?? dflt('first_step_download_budget_minutes')}
            onChange={(e) => setField('cloud', 'first_step_download_budget_minutes', Math.max(0, parseInt(e.target.value, 10) || 0))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-[0.6875rem] text-content-subtle">
            The hard ceiling on that same phase. A host too slow to ever finish would otherwise keep its download alive — and your rental with it — until the runtime cap. Past this, the pod is terminated even though it is still downloading. Set 0 to rely on the runtime cap alone.
          </p>
          <ResetToDefault label="Base-model download ceiling" section="cloud" field="first_step_download_budget_minutes"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-max-runtime" className="block text-sm font-medium text-content">
            Max runtime (minutes)
          </label>
          <input
            id="cloud-max-runtime"
            type="number"
            min="30"
            max="1440"
            step="10"
            value={config.cloud?.max_runtime_minutes ?? dflt('max_runtime_minutes')}
            onChange={(e) => setField('cloud', 'max_runtime_minutes', parseInt(e.target.value) || dflt('max_runtime_minutes'))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-[0.6875rem] text-content-subtle">
            The last backstop on the bill: past this, the pod is terminated whatever it is doing, and the newest checkpoint is rescued first. Enforced from outside the run too, so it holds even if the run's own supervision dies.
          </p>
          <ResetToDefault label="Max runtime" section="cloud" field="max_runtime_minutes"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-freeze-watchdog" className="block text-sm font-medium text-content">
            Freeze watchdog (minutes, 0 = warn only)
          </label>
          <input
            id="cloud-freeze-watchdog"
            type="number"
            min="0"
            max="480"
            step="1"
            value={config.cloud?.freeze_watchdog_minutes ?? dflt('freeze_watchdog_minutes')}
            onChange={(e) => setField('cloud', 'freeze_watchdog_minutes', Math.max(0, parseInt(e.target.value, 10) || 0))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-[0.6875rem] text-content-subtle">
            Last-resort net when a training run stops reporting altogether (a restart, a connection wedged against the pod): the pod is terminated from outside the run, so it can't keep billing unnoticed. Checkpoints already downloaded are kept. Set 0 to only get the warning on the run card. Booting and downloading are never cut by this; the dataset upload has its own setting below.
          </p>
          <ResetToDefault label="Freeze watchdog" section="cloud" field="freeze_watchdog_minutes"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-upload-stall" className="block text-sm font-medium text-content">
            Dataset upload stall (minutes, 0 = never cut)
          </label>
          <input
            id="cloud-upload-stall"
            type="number"
            min="0"
            max="480"
            step="1"
            value={config.cloud?.upload_stall_minutes ?? dflt('upload_stall_minutes')}
            onChange={(e) => setField('cloud', 'upload_stall_minutes', Math.max(0, parseInt(e.target.value, 10) || 0))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-[0.6875rem] text-content-subtle">
            This is <strong>not</strong> a time limit on the upload — a large dataset is allowed to take as long as it needs, and the run card shows the files and gigabytes going across. It is how long the machine may sit with <strong>no data at all</strong> arriving before the run is given up and the pod released, so a wedged transfer stops billing in minutes instead of hours. Set 0 to never cut. Turning the freeze watchdog off turns this off too.
          </p>
          <ResetToDefault label="Dataset upload stall" section="cloud" field="upload_stall_minutes"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-unreachable-grace" className="block text-sm font-medium text-content">
            Unreachable grace (minutes)
          </label>
          <input
            id="cloud-unreachable-grace"
            type="number"
            min="1"
            max="60"
            step="1"
            value={config.cloud?.unreachable_grace_minutes ?? dflt('unreachable_grace_minutes')}
            onChange={(e) => setField('cloud', 'unreachable_grace_minutes', parseInt(e.target.value) || dflt('unreachable_grace_minutes'))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-[0.6875rem] text-content-subtle">
            How long a mid-run pod may stay unreachable (a <VastLink className="underline" /> network blip) before the run is given up and retried on a fresh host. Raise it if healthy runs die with "pod unreachable".
          </p>
          <ResetToDefault label="Unreachable grace" section="cloud" field="unreachable_grace_minutes"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
        <div>
          <label htmlFor="cloud-min-reliability" className="block text-sm font-medium text-content">
            Min host reliability
          </label>
          <input
            id="cloud-min-reliability"
            type="number"
            min="0.9"
            max="0.999"
            step="0.005"
            value={config.cloud?.min_reliability ?? dflt('min_reliability')}
            onChange={(e) => setField('cloud', 'min_reliability', Math.min(0.999, Math.max(0.9, parseFloat(e.target.value) || dflt('min_reliability'))))}
            className={INPUT_CLASS}
          />
          <p className="mt-1 text-[0.6875rem] text-content-subtle">
            Lower it (e.g. 0.95) to surface cheaper hosts in the GPU picker — at a higher risk of a pod that never boots (≈ a few wasted cents, auto-cleaned).
          </p>
          <ResetToDefault label="Min host reliability" section="cloud" field="min_reliability"
            config={config} configDefaults={configDefaults} setField={setField} />
        </div>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium text-content">GPU offer filters</p>
        <div className="grid gap-2 lg:grid-cols-2">
          <CloudOfferFilter
            id="cloud-verified-only"
            label="Verified hosts only"
            help="Only show hosts verified by vast.ai. Recommended; turning this off can reveal more or cheaper offers, with more host risk."
            checked={verifiedOnly}
            onChange={(value) => setField('cloud', 'verified_only', value)}
          />
          <CloudOfferFilter
            id="cloud-secure-cloud-only"
            label="Secure Cloud only"
            help="Only show offers marked Secure Cloud by vast.ai. This excludes Community Cloud machines, so availability may be lower and prices higher."
            checked={secureCloudOnly}
            onChange={(value) => setField('cloud', 'secure_cloud_only', value)}
          />
        </div>
      </div>
      {spend != null && (
        <p className="text-xs text-content-muted">Spent this month: ${spend.toFixed(2)}</p>
      )}
    </Card>
  )
}





const HF_CLOUD_SECRET = {
  key: 'HF_CLOUD_TOKEN', label: 'Dedicated Hugging Face cloud token', testTarget: 'hf_cloud',
  help: (
    <>
      Required only for full-model Krea 2 cloud training. Recommended: create a separate fine-grained token with zero global permissions and grant{' '}
      <strong className="font-semibold text-content">repo.content.read exactly on krea/Krea-2-Raw</strong>
      {', then '}
      <strong className="font-semibold text-content">repo.content.read + repo.write on one dedicated HF user/org namespace that contains only LDS deliveries</strong>
      {'. A per-run repository does not exist yet when the token is created, so scope write access to that single dedicated namespace. A global write token is also accepted, but LDS will warn because it can modify every repository this account can write to.'}
    </>
  ),
  guide: (
    <div className="mb-2 flex flex-wrap gap-x-3 gap-y-1">
      <a
        href="https://huggingface.co/settings/tokens/new?tokenType=fineGrained"
        target="_blank"
        rel="noreferrer"
        className="inline-block max-w-full text-xs font-medium text-sky-300 underline underline-offset-2 hover:text-sky-200"
      >
        Create a fine-grained token on Hugging Face ↗
      </a>
      <a
        href="https://huggingface.co/settings/tokens/new?tokenType=write"
        target="_blank"
        rel="noreferrer"
        className="inline-block max-w-full text-xs font-medium text-sky-300 underline underline-offset-2 hover:text-sky-200"
      >
        Create a global write token on Hugging Face ↗
      </a>
    </div>
  ),
}

export default function CloudTrainingGroup(props) {
  const { config, setField, configDefaults } = props
  return (
    <>
      <Card title="Cloud GPU (vast.ai)" help="No local GPU? The app can rent one per run — the key below unlocks the ☁️ Train in cloud button.">
        <SecretField field={VAST_SECRET} {...props} />
        <div className="rounded-lg border border-sky-400/25 bg-sky-400/5 p-3">
          <SecretField field={HF_CLOUD_SECRET} {...props} />
        </div>
      </Card>
      <CloudTrainingCard config={config} setField={setField} configDefaults={configDefaults} />
    </>
  )
}
