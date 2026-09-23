import { EngineCard, TAG_CLASS } from '@lds/plugin-sdk/ui'
import { ChatGptIcon } from './engineIcons.jsx'
import { chatgptViaSubscription } from '../lib/engineSpecs.js'

/* ChatGPT on the generate panel. Two lanes, one card: the subscription (the
   plan's own image quota) or the pay-per-use API key. The card says which one
   THIS run would use — the same rule the cost estimate applies through the
   spec's `freeWhen` — and names the API lane's model, which is free text in
   Settings: the card used to state "gpt-image-2" flatly, which became a lie
   the moment someone changed it. */
export default function ChatgptCard({ spec, checked, available, generating, onToggle, share, caps, engineConfig }) {
  const accent = spec.accent
  const viaSub = chatgptViaSubscription({ caps, engineConfig })
  const sub = (caps || {}).chatgpt_subscription || {}
  const planLabel = sub.plan && sub.plan !== 'free'
    ? sub.plan.charAt(0).toUpperCase() + sub.plan.slice(1)
    : 'Plus/Pro'
  const imageModel = ((engineConfig || {}).chatgpt_image_model || '').trim()
  return (
    <EngineCard id={spec.id} checked={checked} available={available} generating={generating}
      onToggle={onToggle}
      icon={<ChatGptIcon className={`w-9 h-9 shrink-0 ${checked ? accent.icon : 'text-content-subtle'}`} />}
      title={<>ChatGPT <span className="font-normal text-content-subtle">{viaSub ? '· subscription' : '· API'}</span></>}
      tags={[
        <span key="gpu" className={TAG_CLASS}>No GPU</span>,
        <span key="price" className={TAG_CLASS}>{viaSub ? 'Plan quota' : `~$${spec.rate.toFixed(2)}/image`}</span>,
        <span key="sfw" className={TAG_CLASS}>SFW</span>,
      ]}
      hint={available ? (
        <span className={`text-[0.625rem] ${checked ? accent.text : 'text-content-subtle'}`}>
          {/* The subscription lane renders on the plan's own image model and
              ignores the Settings field, so only the API lane names it. */}
          {viaSub
            ? `Uses your ChatGPT ${planLabel} image quota`
            : <><span className="break-all">{imageModel || 'gpt-image-2.5-sunburst'}</span>
                {` · ${share} image(s) ≈ $${(share * spec.rate).toFixed(2)}`}</>}
        </span>
      ) : (
        <span className="text-amber-300 text-[0.625rem]">⚠ Add an API key or connect a subscription in Settings</span>
      )} />
  )
}
