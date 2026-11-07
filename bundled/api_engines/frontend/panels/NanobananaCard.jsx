import { EngineCard, TAG_CLASS } from '@lds/plugin-sdk/ui'

/* Nano Banana Pro on the generate panel — the card the engine spec names.
   The core renders one EngineCard per engine it knows and hands each plugin
   card the same facts: whether it is checked, whether the install can run it,
   its share of the selected shots. What the card SAYS is the plugin's. */
export default function NanobananaCard({ spec, checked, available, generating, onToggle, share }) {
  const accent = spec.accent
  return (
    <EngineCard id={spec.id} checked={checked} available={available} generating={generating}
      onToggle={onToggle}
      icon={<span className="w-9 h-9 shrink-0 grid place-items-center text-2xl" aria-hidden="true">🍌</span>}
      title={<>Nano Banana Pro <span className="font-normal text-content-subtle">· API</span></>}
      tags={[
        <span key="gpu" className={TAG_CLASS}>No GPU</span>,
        <span key="price" className={TAG_CLASS}>~${spec.rate.toFixed(2)}/image</span>,
        <span key="sfw" className={TAG_CLASS}>SFW</span>,
      ]}
      hint={available ? (
        <span className={`text-[0.625rem] ${checked ? accent.text : 'text-content-subtle'}`}>
          Best face fidelity · {share} image(s) ≈ ${(share * spec.rate).toFixed(2)}
        </span>
      ) : (
        <span className="text-amber-300 text-[0.625rem]">⚠ Add GEMINI_API_KEY in Settings</span>
      )} />
  )
}
