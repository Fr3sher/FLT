import { Card, INPUT_CLASS, ResetToDefault, PromptOverrideField } from '@lds/plugin-sdk/ui'
import { defaultValueAt } from '@lds/plugin-sdk/data'
const IMPROVE_KNOBS = [
  { key: 'improve_megapixels', label: 'Output size (MP)',
    min: 0.5, max: 8, step: 0.5,
    hint: 'The result’s resolution.' },
  { key: 'improve_base_lora_strength', label: 'Enhancement LoRA',
    min: 0, max: 2, step: 0.05,
    hint: '0 = off (the shipped behaviour). Try 0.5–0.8. Needs klein/realistic.safetensors.' },
  // Drives klein.consistency_strength, which enqueue_klein_edit clamps to 1.5 — the
  // UI must not offer a value the engine pulls back. It anchors COMPOSITION, not
  // identity: it was mislabelled "Character LoRA" when these knobs first shipped.
  { key: 'improve_consistency_strength', label: 'Consistency LoRA',
    min: 0, max: 1.5, step: 0.05,
    hint: 'Holds the composition and background. High values resist the edit.' },
  { key: 'improve_steps', label: 'Steps',
    min: 1, max: 50, step: 1, hint: 'More steps = slower, usually cleaner.' },
]
export default function KleinImproveSettings({ config, setField, configDefaults, promptDefaults }) {
const ip = config.identity_prompts || {}
const defaults = promptDefaults || {}
const improveEnabled = ip.klein_improve_enabled !== false
const kleinDefault = key => defaultValueAt(configDefaults, 'klein', key)
const set = (key, value) => setField('identity_prompts', key, value)
return <Card id="klein-improve-settings" title="Klein improvement">
      <div className="border-t border-border pt-4">
        {/* The second sentence is the honest half. The default asks for
            PHOTOGRAPHIC detail, and the app does not vary it by subject type, so
            on a drawn dataset it works against the anime lock every other prompt
            here enforces. The default is deliberately left as-is — people have
            calibrated their results on it — but saying nothing turned that into
            "the tool ruins my anime" (Qeeyana, Reddit). */}
        <p className="mb-2 text-xs text-content-subtle">
          The prompt below is <strong>not</strong> per subject type — it asks for texture and
          detail, which means the same thing for a person, a dog or a car.{' '}
          <span className="text-amber-300">
            It does <strong>not</strong> mean the same thing for a drawing: the built-in text asks for
            photographic detail, so on an Anime dataset it pushes skin and fabric towards realism.
            Rewrite it below, or untick the box above to upscale with no prompt at all.
          </span>
        </p>
        <label htmlFor="identity-prompt-klein-improve-enabled" className="flex items-center gap-2 text-sm font-medium text-content">
          <input
            id="identity-prompt-klein-improve-enabled"
            type="checkbox"
            checked={improveEnabled}
            onChange={(e) => set('klein_improve_enabled', e.target.checked)}
            className="h-4 w-4 rounded border-border-strong"
          />
          Apply an improvement prompt on “Klein upscale &amp; improve”
        </label>
        <PromptOverrideField
          id="identity-prompt-klein-improve"
          label="Klein upscale & improve prompt"
          desc="The fixed instruction the manual “Klein upscale & improve” action sends to add texture and detail. Turn the checkbox above off to upscale with no prompt at all (pure enhancement)."
          rows={3}
          value={ip.klein_improve}
          defaultText={defaults.klein_improve}
          onChange={(v) => set('klein_improve', v)}
          disabled={!improveEnabled}
          className="mt-2"
        />
        {!improveEnabled && (
          <p className="mt-1 text-xs text-content-subtle">Disabled — no prompt is applied.</p>
        )}
      </div>

      {/* The instruction above was already editable, but the knobs deciding how
          much the pass actually changes were hardcoded — including both LoRA
          strengths at 0, which meant the workflow's own realistic LoRA never
          applied. Defaults here are those historical values. */}
      {/* id spelled out literally: it is the deep-link target of the lightbox's
          "Adjust improve strength →" link, and the contract tests find targets by
          scanning this file for id="…". The BLOCK is the target, not one knob:
          "strength" here is the four values together, and ringing the group is
          the honest answer to what that label promises. */}
      <div id="klein-improve-strength" className="scroll-mt-24 border-t border-border pt-4">
        <h4 className="text-sm font-medium text-content">Upscale &amp; improve — strength</h4>
        <p className="mt-1 mb-2 text-xs text-content-muted">
          Output resolution, and how much the pass is allowed to change the image. All four
          start at the values the action used before they were exposed, so leaving them alone
          keeps today’s result.
        </p>
        <p className="mb-2 text-xs text-content-muted">
          The <strong>enhancement LoRA</strong> needs its weights file
          (<code>klein/realistic.safetensors</code>): a positive enhancement strength requires
          this file. Download it with the shared Klein assets in <strong>Setup ▸ Downloads &amp; repair</strong>
          before raising the enhancement strength.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          {IMPROVE_KNOBS.map((k) => (
            <div key={k.key}>
              <label htmlFor={`klein-${k.key}`} className="block text-xs font-medium text-content">
                {k.label}
              </label>
              <input
                id={`klein-${k.key}`}
                type="number"
                min={k.min}
                max={k.max}
                step={k.step}
                value={config.klein?.[k.key] ?? kleinDefault(k.key)}
                onChange={(e) => setField('klein', k.key,
                  e.target.value === '' ? kleinDefault(k.key) : Number(e.target.value))}
                className={INPUT_CLASS}
              />
              <p className="mt-1 text-[0.6875rem] text-content-subtle">
                {k.hint} Default {String(kleinDefault(k.key))}.
              </p>
              <ResetToDefault label={k.label} section="klein" field={k.key}
                config={config} configDefaults={configDefaults} setField={setField} />
            </div>
          ))}
        </div>
      </div>
</Card>
}
