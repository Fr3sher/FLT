import { useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, Check, Circle, Dna, ImagePlus, Images, Loader2, Puzzle, ScanText } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router'
import { apiFetch } from '../../api/fetchClient'
import { useCapabilities } from '../../context/CapabilitiesContext'
import { engineCatalog } from '../../engines/catalog'
import { productReadiness } from '../../plugins/readiness'
import { HelpBadge } from '../../help/HelpMode'
import { completeCoreSetup } from './completeCoreSetup'
import { deriveJourney, journeyProducts, localJourneyPath, normalizeJourney, SETUP_GOALS } from './setupJourney'
import { saveSetupJourney, useSetupJourney } from './useSetupJourney'
import SetupJourneyChoices from './SetupJourneyChoices'

const PRIMARY = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-gradient-primary px-5 py-2.5 text-left text-sm font-semibold text-gray-950 disabled:opacity-50'
const SECONDARY = 'inline-flex min-h-10 items-center justify-center rounded-lg border border-border-strong px-3 py-2 text-sm text-content hover:bg-surface-raised disabled:opacity-50'
const ICONS = { images: Images, captions: ScanText, generate: ImagePlus, plugins: Puzzle }

/** Guide the next action; existing installers still own downloads and consent. */
export default function SetupStart({ onTools, onRecheck, scanned = false, detecting = false, scanProblem = '', runtimeReadiness = null }) {
  const navigate = useNavigate()
  const { caps, known } = useCapabilities()
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const fromQuery = useMemo(() => normalizeJourney(Object.fromEntries(new URLSearchParams(query))), [query])
  const saved = useSetupJourney()
  const journey = fromQuery || saved
  const [selected, setSelected] = useState('dataset')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [storageWarning, setStorageWarning] = useState(false)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState(null)
  const needsChecks = Boolean(journey && journey.goal !== 'dataset')
  const goalId = journey?.goal || ''
  const requestKey = goalId + ':' + revision
  const syncedQuery = useRef(null)

  // A direct link and a browser restart use the same small, non-secret plan.
  useEffect(() => {
    // Clearing the plan just before navigation must not re-save the old URL.
    if (syncedQuery.current === query) return
    syncedQuery.current = query
    if (fromQuery && JSON.stringify(fromQuery) !== JSON.stringify(saved)) {
      setStorageWarning(!saveSetupJourney(fromQuery))
    } else if (!fromQuery && saved) setParams(saved, { replace: true })
  }, [query, fromQuery, saved, setParams])

  useEffect(() => {
    if (!needsChecks) return undefined
    let alive = true
    const controller = new AbortController()
    const options = { cache: 'no-store', background: true, signal: controller.signal }
    Promise.allSettled([
      apiFetch('/api/plugins/', options),
      goalId === 'plugins' ? apiFetch('/api/plugins/store/catalog', options) : Promise.resolve(null),
    ]).then(([plugins, catalog]) => {
      if (!alive) return
      setResult({ key: requestKey,
        data: plugins.status === 'fulfilled' ? plugins.value : null,
        error: plugins.status === 'rejected' ? 'Could not check installed plugins. Check the connection and try again.' : '',
        catalog: catalog.status === 'fulfilled' ? catalog.value
          : { status: 'unavailable', products: [], message: 'The Store could not be reached. You can still set up your installed plugins.' } })
    })
    return () => { alive = false; controller.abort() }
  }, [needsChecks, goalId, requestKey])

  const current = result?.key === requestKey ? result : null
  const installed = current?.data?.plugins || []
  const products = journeyProducts(current?.catalog, installed)
  const selectedPlugin = installed.find(plugin => plugin.id === journey?.plugin)
  const productRows = journey?.plugin ? productReadiness(journey.plugin, caps, { withTargets: true }) : []
  const bootChanged = !!(current?.data?.boot_id && window.lds?.bootId && current.data.boot_id !== window.lds.bootId)
  const interfaceProblem = window.lds?.loadProblems?.some(item => item.plugin === journey?.plugin)
    ? 'This plugin’s interface did not load. Reload LDS; if it still fails, repair the plugin from My plugins.' : ''
  const plan = deriveJourney(journey, { caps, runtime: runtimeReadiness, installed,
    catalog: current?.catalog, productRows, interfaceProblem })
  const checking = needsChecks && (!scanned || detecting || !current || (!known && !scanProblem))
  const checkProblem = needsChecks && (scanProblem || current?.error || (bootChanged && 'LDS has restarted. Reload this page to continue with its current plugins.'))
  const ready = plan?.ready && !checking && !checkProblem
  const stage = !journey ? 0 : ready ? 2 : 1

  function choose(value) {
    setError('')
    setStorageWarning(!saveSetupJourney(value))
    setParams(normalizeJourney(value) || {}, { replace: true })
  }
  async function follow(target, finish = false, goal = journey?.goal) {
    if (busy) return
    const path = localJourneyPath(target)
    if (!path) { setError('This destination is unavailable. Return to the tool list and try again.'); return }
    setBusy(true); setError('')
    try {
      // A first-run redirect must not intercept the trip through the Store.
      // Completion also proves that this workspace can save its own state.
      if (!path.startsWith('/setup')) await completeCoreSetup(goal)
      if (finish) saveSetupJourney(null)
      navigate(path)
    } catch (e) { setError(e.message || 'Could not prepare the workspace. Please try again.') }
    finally { setBusy(false) }
  }
  function recheck() { setRevision(value => value + 1); onRecheck?.() }
  function changeGoal() { saveSetupJourney(null); setParams({}, { replace: true }); setError('') }

  return <div className="mx-auto max-w-2xl space-y-6" data-probe-reading="setup-start"
    data-probe-content="setup" data-probe-setup={checking ? 'checking' : 'ready'}>
    <header>
      <div className="flex items-center justify-between gap-3">
        <Dna aria-hidden="true" className="h-8 w-8 text-primary" />
        <HelpBadge topic="setup-first-steps" />
      </div>
      {journey && journey.goal !== 'dataset' && <ol aria-label="Getting started" className="mt-5 flex flex-wrap gap-x-6 gap-y-3 border-y border-border py-4">
        {['Your goal', 'Preparation', 'First try'].map((label, index) => <li key={label}
          aria-current={stage === index ? 'step' : undefined}
          className={'flex items-center gap-2 text-xs ' + (stage === index ? 'font-semibold text-primary' : 'text-content-muted')}>
          <span aria-hidden="true" className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-current">{index + 1}</span>{label}
        </li>)}
      </ol>}
      <h1 className="mt-6 text-2xl font-bold text-content">{journey ? plan.title : 'What would you like to do with LDS?'}</h1>
      <p className="mt-2 text-sm text-content-muted">{journey
        ? 'Follow the next action below. Only the tools needed for your choice count toward this plan.'
        : 'Your dataset workspace is ready. Open LDS now, or choose a tool to prepare only what you need.'}</p>
    </header>

    {!journey ? <>
      <div className="grid gap-3 sm:grid-cols-2" aria-label="Choose your first goal">
        {SETUP_GOALS.map(goal => {
          const Icon = ICONS[goal.icon]
          return <button type="button" key={goal.id} aria-pressed={selected === goal.id}
            onClick={() => setSelected(goal.id)}
            className={'flex min-h-28 min-w-0 items-start gap-3 rounded-xl border p-4 text-left hover:border-primary focus-visible:outline-primary ' +
              (selected === goal.id ? 'border-primary bg-primary/10' : 'border-border bg-surface')}>
            <Icon className="mt-0.5 h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-content">{goal.title}</span>
              <span className="mt-1 block text-xs leading-relaxed text-content-muted">{goal.description}</span></span>
            {selected === goal.id && <Check className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />}
          </button>
        })}
      </div>
      <p className="text-xs text-content-muted">You can add other tools later. Downloads and any purchases are reviewed before they start.</p>
      <div className="flex flex-wrap items-center justify-end gap-3">
        {selected !== 'dataset' && <button type="button" onClick={() => follow('/datasets', true, 'dataset')} disabled={busy}
          className="mr-auto min-h-10 text-sm text-content-muted underline">Open LDS without these tools</button>}
        <button type="button" disabled={busy} onClick={() => selected === 'dataset'
          ? follow('/datasets', true, 'dataset') : choose({ goal: selected })} className={PRIMARY}>
          {busy ? 'Opening LDS…' : selected === 'dataset' ? 'Open LDS' : 'Continue'}
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </> : <>
      {checking && <p role="status" className="flex items-center gap-2 rounded-lg border border-border p-4 text-sm text-content-muted">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Checking the tools for your plan…
      </p>}
      {checkProblem && <div role="alert" className="space-y-3 rounded-lg border border-amber-500/40 p-4 text-sm text-content">
        <p>{checkProblem}</p>
        <button type="button" onClick={bootChanged ? () => window.location.reload() : recheck} disabled={detecting} className={SECONDARY}>
          {bootChanged ? 'Reload LDS' : 'Retry checks'}
        </button>
      </div>}
      {!checking && !checkProblem && <>
        {plan.choosePlugin || plan.chooseEngine || plan.chooseCapability ? <SetupJourneyChoices plan={plan} journey={journey}
          products={products} catalog={current?.catalog} engines={engineCatalog()} rows={productRows}
          onChoose={choose} onBrowse={() => follow('/plugins?tab=discover')} /> : <>
          <ol className="divide-y divide-border" aria-label="Your preparation steps" data-setup-plan>
            {plan.rows.map(item => {
              const currentStep = plan.next?.id === item.id
              const Icon = item.ready ? Check : currentStep ? ArrowRight : Circle
              return <li key={item.id} data-setup-check={item.id} data-state={item.ready ? 'ready' : currentStep ? 'next' : 'later'}
                className="flex items-start gap-3 py-3">
                <span className={'mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-raised ' +
                  (item.ready ? 'text-emerald-400' : currentStep ? 'text-primary' : 'text-content-subtle')}>
                  <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium text-content">{item.title}<span className="sr-only">{item.ready ? ' — Ready' : currentStep ? ' — Next action' : ' — Later'}</span></span>
                  <span className="mt-1 block text-xs leading-relaxed text-content-muted">{item.description}</span>
                </span>
              </li>
            })}
          </ol>
          {plan.next?.action && <section className="space-y-3 rounded-xl border border-primary/40 bg-surface p-5" aria-label="Your next action" aria-live="polite">
            <p className="text-xs font-semibold uppercase tracking-wide text-primary">Your next action</p>
            <h2 className="text-lg font-semibold text-content">{plan.next.title}</h2>
            <p className="text-sm text-content-muted">{plan.next.description}</p>
            <button type="button" disabled={busy} className={PRIMARY}
              onClick={() => plan.next.action.kind === 'reload' ? window.location.reload() : follow(plan.next.action.to)}>
              {busy ? 'Opening…' : plan.next.action.label}
            </button>
            <p className="text-xs text-content-muted">When you finish, use “Back to my setup plan”. The plan checks what is ready; opening an installer does not complete a step.</p>
          </section>}
          {(ready || plan.manual) && plan.first && <section className="space-y-3 rounded-xl border border-border bg-surface p-5" aria-label="Your first try">
            <p className={'text-xs font-medium ' + (ready ? 'text-emerald-400' : 'text-content-muted')}>
              {ready ? 'Ready for your first try' : 'First try — follow the plugin’s checks'}
            </p>
            <h2 className="text-lg font-semibold text-content">{plan.first.title}</h2>
            <p className="text-sm text-content-muted">{plan.first.description}</p>
            <div className="flex flex-wrap gap-2">{plan.first.links.map(link => <button type="button" key={link.to}
              disabled={busy} className={PRIMARY} onClick={() => follow(link.to, true)}>{busy ? 'Opening…' : link.label}</button>)}</div>
            {plan.first.links.length === 0 && <button type="button" className={SECONDARY} onClick={() => follow('/plugins?tab=installed', true)}>Open My plugins</button>}
          </section>}
        </>}
      </>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button type="button" className="min-h-10 text-sm text-content-muted underline" onClick={changeGoal}>← Change goal</button>
        {journey.goal === 'plugins' && journey.plugin && <button type="button" className={SECONDARY}
          onClick={() => choose({ goal: 'plugins' })}>Choose another plugin</button>}
        {journey.goal === 'images' && journey.engine && <button type="button" className={SECONDARY}
          onClick={() => choose({ goal: 'images' })}>Change engine</button>}
        {selectedPlugin && journey.capability && <button type="button" className={SECONDARY}
          onClick={() => choose({ goal: 'plugins', plugin: journey.plugin })}>Change function</button>}
        {needsChecks && <button type="button" onClick={recheck} disabled={checking || detecting} className={SECONDARY}>Check again</button>}
      </div>
      <p className="text-xs text-content-muted">Your chosen goal stays in this browser after a restart. Return through Setup or “Back to my setup plan”.</p>
    </>}
    {error && <p role="alert" className="break-words text-sm text-rose-300">{error}</p>}
    {storageWarning && <p role="status" className="text-sm text-amber-300">This browser could not save the plan. Keep this tab’s setup URL to return to it after a restart.</p>}
    <div className="border-t border-border pt-4">
      <button type="button" onClick={onTools} className="min-h-10 text-sm text-content-muted underline">All tools & advanced setup</button>
    </div>
  </div>
}
