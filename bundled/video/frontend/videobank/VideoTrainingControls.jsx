import { useId } from 'react'
import { HelpBadge } from '@lds/plugin-sdk';

export default function VideoTrainingControls({ value, onChange, error }) {
  const id = useId()
  const set = (key, next) => onChange({ ...value, [key]: next })
  const inputClass = 'min-h-10 lg:min-h-0 rounded border border-border bg-surface-raised px-2 py-1 text-xs text-content'
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-lg border border-border bg-surface p-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-content-muted">
          LoRA rank
          <select aria-label="LoRA rank" value={value.rank} onChange={(e) => set('rank', Number(e.target.value))} className={inputClass}>
            {[8, 16, 32, 64, 128, 256].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label className="flex flex-wrap items-center gap-2 text-xs text-content-muted">
          Memory mode
          <select aria-label="Memory mode" value={value.memory} onChange={(e) => set('memory', e.target.value)} className={inputClass}>
            <option value="auto">Auto (local on / cloud off)</option>
            <option value="on">Low VRAM on</option>
            <option value="off">Low VRAM off</option>
          </select>
        </label>
        <HelpBadge topic="video-training-controls" />
      </div>
      <p className="text-xs text-content-muted">Higher ranks use more memory. Low VRAM reduces memory use but can slow training.</p>
      <label htmlFor={`${id}-prompts`} className="text-xs font-medium text-content">Sample prompts</label>
      <textarea id={`${id}-prompts`} rows={3} value={value.prompts}
        onChange={(e) => set('prompts', e.target.value)}
        aria-describedby={`${id}-hint${error ? ` ${id}-error` : ''}`} aria-invalid={Boolean(error)}
        placeholder="One prompt per line, including your trigger word"
        className={`${inputClass} w-full resize-y`} />
      <p id={`${id}-hint`} className="text-xs text-content-muted">
        Optional · up to 4 prompts. Samples appear in the run graph after they are generated and collected.
        Each prompt adds video generation time and cloud cost. Leave blank to disable sampling.
      </p>
      {error && <p id={`${id}-error`} role="alert" className="text-xs text-rose-300">{error}</p>}
    </div>
  )
}
