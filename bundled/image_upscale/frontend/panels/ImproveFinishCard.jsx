import { Card, ResetToDefault } from '@lds/plugin-sdk/ui'
import { defaultValueAt } from '@lds/plugin-sdk/data'
/* The finishing pass — three pixel operations the APP runs on the ✨ improve
   result, after ComfyUI is done with it.

   This card belongs to Klein Improve. SeedVR2 owns its separate finishing recipe. The reference workflow
   these come from does them with three third-party node packs; doing them here
   makes these finishing operations deterministic without extra node packs —
   no GPU, no model, no graph. */
const IMPROVE_SHARPEN_MAX = 1.5
const IMPROVE_GRAIN_MAX = 0.05
// The values the reference workflow uses, shown as the "known-good" landing spot
// rather than shipped as defaults — this ships off.
const IMPROVE_REFERENCE = { colour_match: 0.8, sharpen: 0.55, grain: 0.01 }

export default function ImproveFinishCard({ config, setField, configDefaults }) {
  const improve = config.improve || {}
  const reset = { config, configDefaults, setField }
  const dflt = (key) => defaultValueAt(configDefaults, 'improve', key)
  const num = (key) => Number(improve[key] ?? dflt(key)) || 0
  const colour = num('colour_match')
  const sharpen = num('sharpen')
  const grain = num('grain')
  const grainSat = num('grain_saturation')
  const anyOn = colour > 0 || sharpen > 0 || grain > 0
  return (
    <Card
      id="improve-finish"
      title="Klein finishing pass"
      help="Three small operations applied to the finished image by the app, not by ComfyUI: put the source's colours back, sharpen the finest detail, and add a little film grain. They are what separate a render that looks processed from one that looks photographed. Nothing to install — no model, no GPU, no node pack. All three ship off; the image you get today is byte-for-byte the one ComfyUI wrote."
    >
      {!anyOn && (
        <p className="rounded border border-border-subtle bg-surface-subtle px-2 py-1.5 text-[0.6875rem] text-content-subtle">
          Every stage is off — the finished image is left exactly as ComfyUI wrote it.
          The reference workflow this was ported from runs colour match{' '}
          {IMPROVE_REFERENCE.colour_match}, sharpen {IMPROVE_REFERENCE.sharpen}, grain{' '}
          {IMPROVE_REFERENCE.grain}.
        </p>
      )}

      <div className="mt-3 sm:max-w-md">
        <label htmlFor="improve-colour-match" className="block text-xs font-medium text-content">
          Put the source&rsquo;s colours back ({colour === 0 ? 'off' : colour})
        </label>
        <input
          id="improve-colour-match"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={colour}
          onChange={(e) => setField('improve', 'colour_match', Number(e.target.value))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">

            <>
              A Klein improve keeps the content and loses the grade: skin warms or cools and
              a dataset ends up holding two colour worlds depending on which images went
              through. This measures the colours of the image as it was <b>before</b> the
              pass and puts them back. {IMPROVE_REFERENCE.colour_match} is the reference
              value; 1 forbids the pass any colour change at all.
            </>

        </p>
        <ResetToDefault label="Put the source's colours back" section="improve"
          field="colour_match" {...reset} />
      </div>

      <div className="mt-3 sm:max-w-md">
        <label htmlFor="improve-sharpen" className="block text-xs font-medium text-content">
          Sharpen ({sharpen === 0 ? 'off' : sharpen})
        </label>
        <input
          id="improve-sharpen"
          type="range"
          min={0}
          max={IMPROVE_SHARPEN_MAX}
          step={0.05}
          value={sharpen}
          onChange={(e) => setField('improve', 'sharpen', Number(e.target.value))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          Local contrast at a 1&nbsp;px radius — the finest octave, the one diffusion leaves
          empty — not a global sharpness slider. {IMPROVE_REFERENCE.sharpen} is the reference
          value; past about 1 the halo starts reading as an outline.
        </p>
        <ResetToDefault label="Sharpen" section="improve" field="sharpen" {...reset} />
      </div>

      <div className="mt-3 sm:max-w-md">
        <label htmlFor="improve-grain" className="block text-xs font-medium text-content">
          Film grain ({grain === 0 ? 'off' : grain})
        </label>
        <input
          id="improve-grain"
          type="range"
          min={0}
          max={IMPROVE_GRAIN_MAX}
          step={0.002}
          value={grain}
          onChange={(e) => setField('improve', 'grain', Number(e.target.value))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          Diffusion output is smooth in a way photographs are not — the model resolves
          structure confidently and leaves the finest octave nearly empty. A very small
          amount of noise refills it and the eye reads the result as a photograph.
          The scale is deliberately tiny: {IMPROVE_REFERENCE.grain} is about ±2.5 levels of
          an 8-bit image, seen as texture and never as noise.
        </p>
        <ResetToDefault label="Film grain" section="improve" field="grain" {...reset} />
      </div>

      {/* Not greyed on `grain === 0`: this dial also serves the Studio's PER-RUN
          grain (the cell carries its own amount, the colour mix follows this
          setting), so it has to stay editable while the improve pass's grain is
          off. */}
      <div className="mt-3 sm:max-w-md">
        <label htmlFor="improve-grain-sat" className="block text-xs font-medium text-content">
          How coloured that grain is ({grainSat})
        </label>
        <input
          id="improve-grain-sat"
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={grainSat}
          onChange={(e) => setField('improve', 'grain_saturation', Number(e.target.value))}
          className="mt-1 w-full accent-violet-500"
        />
        <p className="mt-1 text-[0.6875rem] text-content-subtle">
          0 puts identical noise on the three channels, which is what film does and what
          reads as grain. 1 makes each channel independent, which reads as sensor noise.
        </p>
        <ResetToDefault label="How coloured that grain is" section="improve"
          field="grain_saturation" {...reset} />
      </div>
    </Card>
  )
}
