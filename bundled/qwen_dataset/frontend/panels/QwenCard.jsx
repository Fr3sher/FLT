import { EngineCard, SettingsLink, TAG_CLASS } from '@lds/plugin-sdk/ui'
import { qwenUnavailableReason } from '../lib/engine.js'

export default function QwenCard({ spec, checked, available, generating, onToggle, caps, enabledInSettings }) {
  return <div className="flex min-w-0 flex-col gap-1 [&>button]:h-full">
    <EngineCard id={spec.id} checked={checked} available={available} generating={generating}
      onToggle={onToggle}
      icon={<svg viewBox="0 0 32 32" aria-hidden="true" focusable="false"
        className={`h-9 w-9 shrink-0 ${checked ? spec.accent.icon : 'text-content-subtle'}`}>
        <rect x="4" y="7" width="19" height="21" rx="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
        <path d="M10 4h15a3 3 0 0 1 3 3v15M8 23l5-6 4 4 3-3" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="16" cy="13" r="2" fill="currentColor" />
      </svg>}
      title={<>Qwen-Image 2.1 <span className="font-normal text-content-subtle">· local</span></>}
      tags={[
        <span key="gpu" className={TAG_CLASS}>Your GPU</span>,
        <span key="price" className={TAG_CLASS}>No API cost</span>,
        <span key="license" className={TAG_CLASS}>Non-commercial</span>,
      ]}
      hint={<span className={`text-[0.625rem] ${available ? 'text-content-subtle' : 'text-amber-300'}`}>
        {available ? 'Generate the selected shots from your reference photos. Dataset Forge keeps the usual curation and retry flow.'
          : qwenUnavailableReason(caps, enabledInSettings)}
      </span>} />
    {/* Keep preparation reachable while the engine checkbox is disabled. */}
    <div className="flex min-h-10 items-center px-2 lg:min-h-0">
      {enabledInSettings === false
        ? <SettingsLink pluginId="qwen_dataset" focus="plugin-enabled-engines" tone="warning">Enable this engine</SettingsLink>
        : <SettingsLink pluginId="qwen_dataset" focus={available ? undefined : 'qwen-dataset-preparation'}
          tone={available ? 'subtle' : 'warning'}>Dataset Forge settings &amp; preparation</SettingsLink>}
    </div>
  </div>
}
