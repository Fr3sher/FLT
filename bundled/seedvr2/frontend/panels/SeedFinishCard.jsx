import { Card, ResetToDefault } from '@lds/plugin-sdk/ui'
import { defaultValueAt } from '@lds/plugin-sdk/data'

const FIELDS = [
  { key: 'seedvr2-finish-sharpen', name: 'sharpen', label: 'Sharpen', max: 1.5, step: 0.05, hint: 'Local contrast at a 1 px radius. Start low to avoid visible outlines.' },
  { key: 'seedvr2-finish-grain', name: 'grain', label: 'Film grain', max: 0.05, step: 0.002, hint: 'A small amount of texture after restoration. Zero leaves the image smooth.' },
  { key: 'seedvr2-finish-grain-saturation', name: 'grain_saturation', label: 'Grain colour', max: 1, step: 0.05, hint: 'Zero gives monochrome film grain; one gives independent colour noise.' },
]

export default function SeedFinishCard({ config, setField, configDefaults }) {
  return (
    <Card id="seedvr2-finish" title="SeedVR2 finishing pass"
      help="Optional sharpening and grain applied by LDS after SeedVR2. These settings belong to SeedVR2 alone. Colour correction is handled once inside the SeedVR2 node above. Nothing extra to install.">
      {FIELDS.map(({ key: id, name, label, max, step, hint }) => {
        const field = `finish_${name}`
        const value = Number(config.seedvr2?.[field] ?? defaultValueAt(configDefaults, 'seedvr2', field)) || 0
        return (
          <div key={field} className="mt-3 sm:max-w-md">
            <label htmlFor={id} className="block text-xs font-medium text-content">{label} ({value})</label>
            <input id={id} type="range" min={0} max={max} step={step} value={value}
              onChange={event => setField('seedvr2', field, Number(event.target.value))}
              className="mt-1 w-full accent-violet-500" />
            <p className="mt-1 text-[0.6875rem] text-content-subtle">{hint}</p>
            <ResetToDefault label={label} section="seedvr2" field={field}
              config={config} configDefaults={configDefaults} setField={setField} />
          </div>
        )
      })}
    </Card>
  )
}
