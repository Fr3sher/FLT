import { useState } from 'react'

const CHOICE = 'w-full min-w-0 rounded-xl border border-border bg-surface p-4 text-left hover:border-primary disabled:cursor-not-allowed disabled:opacity-60'
const STATES = { ready: 'Ready', setup: 'Needs preparation', pending: 'Waiting for a service', unknown: 'Check unavailable' }

export default function SetupJourneyChoices({ plan, journey, products, catalog, engines, rows, onChoose, onBrowse }) {
  const [search, setSearch] = useState('')
  if (plan.chooseEngine) return <section className="space-y-4" aria-label="Choose an image engine">
    <h2 className="text-lg font-semibold text-content">Where should your images be generated?</h2>
    <p className="text-sm text-content-muted">Local engines use your GPU and model downloads. Online engines come from installed plugins and may use a paid account or API key.</p>
    <div className="grid gap-3 sm:grid-cols-2">{engines.map(engine => <button type="button" key={engine.id} className={CHOICE}
      onClick={() => onChoose({ ...journey, engine: engine.id })}>
      <span className="block text-sm font-semibold text-content">{engine.label}</span>
      <span className="mt-1 block text-xs text-content-muted">{engine.kind === 'local' ? 'Local · your GPU' : 'Online · account or API key'}</span>
    </button>)}</div>
    <button type="button" onClick={() => onChoose({ goal: 'plugins' })} className="min-h-10 text-sm text-primary underline">Find more engines in the plugin Store</button>
  </section>
  if (plan.chooseCapability) return <section className="space-y-4" aria-label="Choose a plugin function">
    <h2 className="text-lg font-semibold text-content">What would you like to use first?</h2>
    <p className="text-sm text-content-muted">This plugin has several functions. Choose one to see its next action; other optional tools will not hold it up.</p>
    <div className="space-y-3">{rows.map((item, index) => <button type="button" key={item.label + index} className={CHOICE}
      onClick={() => onChoose({ ...journey, capability: item.label })}>
      <span className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-content">{item.label}</span>
        <span className={'text-xs ' + (item.state === 'ready' ? 'text-emerald-400' : 'text-content-muted')}>{STATES[item.state]}</span>
      </span>
      {(item.what || item.note) && <span className="mt-1 block text-xs text-content-muted">{item.what || item.note}</span>}
    </button>)}</div>
  </section>
  const matches = products.filter(product => (product.name + ' ' + product.description).toLowerCase().includes(search.toLowerCase()))
  return <section className="space-y-4" aria-label="Choose a plugin">
    <h2 className="text-lg font-semibold text-content">Choose the tool you want to add</h2>
    <p className="text-sm text-content-muted">Pick a plugin to see its plan: installation, activation, then the models or services for your chosen function.</p>
    <label className="block text-sm text-content">Find a plugin
      <input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Search by name or use…"
        className="mt-1 min-h-11 w-full rounded-lg border border-border-strong bg-surface-raised px-3 py-2 text-content" />
    </label>
    {catalog?.status !== 'ready' && <p role="status" className="text-sm text-content-muted">{catalog?.message || 'The Store is not available. Installed plugins are listed below.'}</p>}
    <div className="grid gap-3 sm:grid-cols-2">{matches.map(product => <button type="button" key={product.id} className={CHOICE}
      disabled={!product.installed && product.issues?.length > 0}
      onClick={() => onChoose({ goal: 'plugins', plugin: product.id })}>
      <span className="block text-sm font-semibold text-content">{product.name}</span>
      <span className="mt-1 block text-xs text-primary">{product.installed ? 'Installed' : product.price?.kind === 'paid' ? 'Paid plugin · review before purchase' : 'Review installation in the Store'}</span>
      <span className="mt-2 block text-xs leading-relaxed text-content-muted">{product.description}</span>
      {!product.installed && product.issues?.length > 0 && <span className="mt-2 block text-xs text-amber-300">{product.issues[0].message}</span>}
    </button>)}</div>
    {!matches.length && <p className="text-sm text-content-muted">{search ? 'No plugin matches this search.' : 'No plugin is available here yet. Open the Store to check its connection or install a plugin archive.'}</p>}
    <button type="button" onClick={onBrowse} className="min-h-10 text-sm text-primary underline">Open the plugin Store</button>
  </section>
}
