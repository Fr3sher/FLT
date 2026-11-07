import { HelpBadge } from '@lds/plugin-sdk'

/* Two facts about the Gemini engine that belong next to the choice, not in a
   support thread after the fact. Both are stated flat, with no verdict
   attached: the filter has no setting to offer, and nobody — in either
   direction — has measured what SynthID does to trained weights, so this says
   it is present and stops there. Plain <p>: wraps freely at 400 px.
   Rendered by the core under the engine cards (the spec's `note`). */
export default function NanobananaNote() {
  return (
    <p className="text-content-subtle text-[0.625rem] -mt-1">
      Building with <span className="text-content-muted">Nano Banana</span>? Google
      screens every image it returns and refuses some of them — LDS names each
      refusal on the tile; the filter itself is not configurable. Its outputs also
      carry SynthID, Google&apos;s invisible provenance watermark.{' '}
      <HelpBadge topic="nanobanana-filter-and-synthid" />
    </p>
  )
}
