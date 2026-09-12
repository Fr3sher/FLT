import { HelpBadge } from '@lds/plugin-sdk'
import { InstallRunner, SettingsLink } from '@lds/plugin-sdk/ui'
import { labels } from './setup.js'

export default function LiveInstallCard({ caps, onDone }) {
  const live = caps?.live || {}, missing = Array.isArray(live.missing) ? live.missing : []
  const required = missing.filter(row => row.required), optional = missing.filter(row => !row.required)
  const canDownload = caps?.comfyui?.dir_valid === true
  return <section className="rounded-xl border border-border bg-surface p-5" data-probe-panel="live-setup">
    <h3 className="flex items-center gap-2 text-base font-semibold text-content">Live channels <HelpBadge topic="setup-live" /></h3>
    <p className="mt-2 text-sm text-content-muted">Live includes its own player, scenes and LoRA controls. Install the stream encoder, then prepare H3 for local rendering. Existing H3 files are reused.</p>
    <div className="mt-4 rounded-lg border border-border bg-surface-raised p-3">
      <p className="mb-2 text-sm text-content">{live.encoder ? '✓ Stream encoder ready' : 'Stream encoder needed'}</p>
      <InstallRunner action="live_encoder" buttonLabel={live.encoder ? 'Repair stream encoder' : 'Install stream encoder'} onDone={onDone} />
    </div>
    <p className="mt-4 text-sm text-content-muted">Local generation uses <a className="underline text-sky-300" href="https://huggingface.co/Comfy-Org/MiniMax-H3" target="_blank" rel="noreferrer">MiniMax H3</a>: four required files, about 39.5 GB. Downloads start only when you choose them.</p>
    {!canDownload && <p className="mt-2 text-sm text-amber-200">Choose a valid ComfyUI folder in <SettingsLink section="local-tools" focus="comfyui-base-dir">Settings</SettingsLink> first.</p>}
    {canDownload && caps?.live && required.length === 0 && <p className="mt-3 text-sm text-content">✓ Required H3 files are on disk. {live.ready ? 'Local rendering is ready.' : 'Start ComfyUI to check local rendering.'}</p>}
    <div className="mt-3 space-y-3">{required.map(row => <div key={row.action} className="rounded-lg border border-border p-3">
      <p className="mb-2 text-sm text-content">{labels[row.action]}</p>
      {canDownload && <InstallRunner action={row.action} buttonLabel="Download" onDone={onDone} />}
    </div>)}</div>
    <details className="mt-4 rounded-lg border border-border p-3"><summary className="min-h-10 cursor-pointer text-sm text-content">Optional speed tools</summary>
      <p className="mb-3 text-sm text-content-muted">Turbo is optional. Node packs run in ComfyUI; install them there and restart it.</p>
      {optional.map(row => <div key={row.action} className="mb-3"><p className="mb-1 text-sm text-content">{labels[row.action]}</p>{canDownload && <InstallRunner action={row.action} buttonLabel="Download" onDone={onDone} />}</div>)}
      {Object.entries(live.options || {}).filter(([key]) => ['turbo', 'sparse'].includes(key)).map(([key, pack]) => <p key={key} className="text-sm text-content-muted"><a className="text-sky-300 underline" href={pack.url} target="_blank" rel="noreferrer">{pack.pack}</a> — {key}: {pack.available === true ? 'ready' : pack.available === false ? 'not installed' : 'start ComfyUI to check'}</p>)}
    </details>
  </section>
}
