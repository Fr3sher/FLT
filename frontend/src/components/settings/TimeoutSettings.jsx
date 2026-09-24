import { Card, INPUT_CLASS } from './primitives'
import ResetToDefault from './ResetToDefault'
import { defaultValueAt } from './settingDefaults.js'

function TimeoutField({ config, configDefaults, setField, section, field, id, label, help, ...bounds }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-content">{label}</label>
      <input id={id} type="number" {...bounds} className={INPUT_CLASS}
        value={config[section]?.[field] ?? defaultValueAt(configDefaults, section, field) ?? ''}
        onChange={(event) => setField(section, field, Number(event.target.value))} />
      <p className="mt-1 text-xs text-content-muted">{help}</p>
      <ResetToDefault label={label} section={section} field={field}
        config={config} configDefaults={configDefaults} setField={setField} />
    </div>
  )
}

export default function TimeoutSettings(props) {
  return (
    <Card title="Processing and network time limits"
      help="Keep the defaults, or give slow or busy hardware more time. Changes apply to new operations. Stop controls remain available.">
      <TimeoutField {...props} section="comfyui" field="repair_timeout_minutes" id="klein-repair-timeout"
        label="Klein repair and watermark cleaning (minutes)" min={0} max={1440} step={1}
        help="Default: 5 minutes per image. Includes waiting in the queue. Use 0 for no elapsed-time limit. Applies to box and brush repairs in Bank, Dataset and Test Studio." />
      <TimeoutField {...props} section="comfyui" field="improve_timeout_minutes" id="bank-improve-timeout"
        label="Bank upscale and improve wait (minutes)" min={0} max={1440} step={1}
        help="Default: 30 minutes per image. Use 0 for no elapsed-time limit. A custom wait also reaches the ComfyUI worker, so its shorter general limit cannot end the render early." />
      <TimeoutField {...props} section="timeouts" field="processing_multiplier" id="processing-timeout-multiplier"
        label="Processing timeout multiplier" min={0.1} max={100} step={0.1}
        help="Default: 1×. Multiplies generation, repair, model startup, captioning and local analysis budgets, including budgets based on batch size. For example, 2× gives a five-minute repair ten minutes. Explicitly unlimited waits stay unlimited." />
      <TimeoutField {...props} section="timeouts" field="network_multiplier" id="network-timeout-multiplier"
        label="Network timeout multiplier" min={0.1} max={100} step={0.1}
        help="Default: 1×. Multiplies connection, download, API and service-health waits. AI response waits use the processing multiplier; their connection uses this network multiplier. Larger values also make unavailable services take longer to report a failure." />
      <p className="text-xs text-content-muted">
        The general generation time limit and ComfyUI response timeout remain in the ComfyUI group.
        Multipliers apply on top of those values. Polling intervals and cleanup after Stop keep their usual timing.
      </p>
    </Card>
  )
}
