import { EngineCard, TAG_CLASS } from '@lds/plugin-sdk/ui'
import { RouterIcon } from './engineIcons.jsx'

/* OpenRouter on the generate panel. The model is free text in Settings, so the
   card names it and quotes no per-image price: the rate in the spec is an
   ESTIMATE for the default model, and a number the user may have changed
   under it must not be stated as a fact. */
export default function OpenrouterCard({ spec, checked, available, generating, onToggle, share, engineConfig }) {
  const accent = spec.accent
  const model = ((engineConfig || {}).openrouter_model || '').trim()
  return (
    <EngineCard id={spec.id} checked={checked} available={available} generating={generating}
      onToggle={onToggle}
      icon={<RouterIcon className={`w-9 h-9 shrink-0 ${checked ? accent.icon : 'text-content-subtle'}`} />}
      title={<>OpenRouter <span className="font-normal text-content-subtle">· API</span></>}
      tags={[
        <span key="gpu" className={TAG_CLASS}>No GPU</span>,
        <span key="price" className={TAG_CLASS}>Your credits</span>,
        <span key="sfw" className={TAG_CLASS}>SFW</span>,
      ]}
      hint={available ? (
        <span className={`text-[0.625rem] ${checked ? accent.text : 'text-content-subtle'}`}>
          <span className="break-all">{model || 'default model'}</span>
          {' · '}{share} image(s), billed by OpenRouter at that model&rsquo;s rate
        </span>
      ) : (
        <span className="text-amber-300 text-[0.625rem]">⚠ Add OPENROUTER_API_KEY in Settings</span>
      )} />
  )
}
