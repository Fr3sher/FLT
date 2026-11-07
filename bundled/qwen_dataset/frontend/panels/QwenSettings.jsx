import { HelpBadge } from '@lds/plugin-sdk'
import { Card, INPUT_CLASS, TextField } from '@lds/plugin-sdk/ui'

export default function QwenSettings({ config, configDefaults, setField, caps }) {
  const values = config.plugins?.qwen_dataset || {}
  const defaults = configDefaults?.plugins?.qwen_dataset || {}
  const set = (key, value) => setField('plugins', 'qwen_dataset', { ...values, [key]: value })
  return <div className="space-y-4">
    <Card title="Dataset generation" help="Choose Qwen-Image 2.1 in your dataset’s Generate variations panel. It uses the same shot selection, reference photos, output size and curation grid.">
      <p className="text-xs text-content-subtle">
        The starting recipe is 25 steps, CFG 3, res_multistep / simple. Add useful side or profile views
        to the dataset references to guide angles the main photo does not show. Up to 10 references
        are supported, including the primary photo.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="qwen-dataset-steps" className="text-sm font-medium text-content">
            Sampling steps <HelpBadge topic="qwen-dataset-steps" />
          </label>
          <input id="qwen-dataset-steps" type="number" min={1} max={100} step={1}
            value={values.steps ?? defaults.steps ?? 25} className={INPUT_CLASS}
            onChange={event => set('steps', event.target.value === '' ? defaults.steps ?? 25 : Number(event.target.value))} />
        </div>
        <div>
          <label htmlFor="qwen-dataset-cfg" className="text-sm font-medium text-content">
            Prompt guidance (CFG) <HelpBadge topic="qwen-dataset-cfg" />
          </label>
          <input id="qwen-dataset-cfg" type="number" min={0} max={30} step={0.1}
            value={values.cfg ?? defaults.cfg ?? 3} className={INPUT_CLASS}
            onChange={event => set('cfg', event.target.value === '' ? defaults.cfg ?? 3 : Number(event.target.value))} />
        </div>
        <div>
          <label htmlFor="qwen-dataset-sampler" className="text-sm font-medium text-content">
            Sampler <HelpBadge topic="qwen-dataset-sampler" />
          </label>
          <select id="qwen-dataset-sampler" className={INPUT_CLASS}
            value={values.sampler_name || defaults.sampler_name || 'res_multistep'}
            onChange={event => set('sampler_name', event.target.value)}>
            <option value="res_multistep">res_multistep (recommended)</option>
            <option value="euler">euler</option>
            <option value="dpmpp_2m">dpmpp_2m</option>
          </select>
        </div>
        <div>
          <label htmlFor="qwen-dataset-scheduler" className="text-sm font-medium text-content">
            Scheduler <HelpBadge topic="qwen-dataset-scheduler" />
          </label>
          <select id="qwen-dataset-scheduler" className={INPUT_CLASS}
            value={values.scheduler || defaults.scheduler || 'simple'}
            onChange={event => set('scheduler', event.target.value)}>
            <option value="simple">simple (recommended)</option>
            <option value="normal">normal</option>
            <option value="karras">karras</option>
          </select>
        </div>
      </div>
      <div>
        <label htmlFor="qwen-dataset-reference-resolution" className="text-sm font-medium text-content">
          Reference resolution <HelpBadge topic="qwen-dataset-reference-resolution" />
        </label>
        <input id="qwen-dataset-reference-resolution" type="number" min={256} max={2048} step={32}
          value={values.reference_resolution ?? defaults.reference_resolution ?? 1024} className={INPUT_CLASS}
          onChange={event => set('reference_resolution', event.target.value === ''
            ? defaults.reference_resolution ?? 1024 : Number(event.target.value))} />
        <p className="mt-1 text-xs text-content-muted">
          Resolution used when encoding reference photos. Higher values use more memory.
          Set the generated image size with Output size (MP) in Generate variations.
        </p>
      </div>
      <div>
        <label htmlFor="qwen-dataset-negative-prompt" className="text-sm font-medium text-content">
          Negative prompt <HelpBadge topic="qwen-dataset-negative-prompt" />
        </label>
        <textarea id="qwen-dataset-negative-prompt" rows={3} maxLength={20000} value={values.negative_prompt ?? ''}
          className={INPUT_CLASS} onChange={event => set('negative_prompt', event.target.value)}
          placeholder="Optional traits to avoid" />
      </div>
      <button type="button" onClick={() => setField('plugins', 'qwen_dataset', { ...values,
        steps: defaults.steps ?? 25, cfg: defaults.cfg ?? 3,
        sampler_name: defaults.sampler_name ?? 'res_multistep', scheduler: defaults.scheduler ?? 'simple' })}
        className="min-h-10 self-start rounded-md border border-border px-3 py-2 text-sm text-content">
        Restore recommended sampling
      </button>
      <p className="text-xs text-content-subtle">
        Current sampler: {values.sampler_name || defaults.sampler_name || 'res_multistep'} / {values.scheduler || defaults.scheduler || 'simple'}.
        Save your changes before starting a batch.
      </p>
    </Card>
    <Card title="Model files" help="Leave empty for automatic selection. Use official INT8 or BF16 filenames, with an optional subfolder. Renamed files and custom builds are not supported.">
      <TextField id="qwen-dataset-unet" label="Qwen-Image 2.1 model filename"
        value={values.unet} onChange={value => set('unet', value)} placeholder="Automatic"
        help={caps?.qwen_dataset?.models?.unet ? `Detected: ${caps.qwen_dataset.models.unet}` : 'The Qwen-Image 2.1 diffusion model.'} />
      <TextField id="qwen-dataset-text-encoder" label="Qwen3-VL text encoder filename"
        value={values.text_encoder} onChange={value => set('text_encoder', value)} placeholder="Automatic"
        help={caps?.qwen_dataset?.models?.text_encoder ? `Detected: ${caps.qwen_dataset.models.text_encoder}` : 'The Qwen3-VL encoder used by Qwen-Image 2.1.'} />
      <TextField id="qwen-dataset-vae" label="Qwen-Image 2.1 VAE filename"
        value={values.vae} onChange={value => set('vae', value)} placeholder="Automatic"
        help={caps?.qwen_dataset?.models?.vae ? `Detected: ${caps.qwen_dataset.models.vae}` : 'The Qwen-Image 2.1 VAE.'} />
    </Card>
    <p className="text-xs text-content-subtle">
      Inspired by{' '}
      <a href="https://www.reddit.com/r/comfyui/comments/1wnlgko/qwen_21_dataset_generator/" target="_blank" rel="noreferrer"
        className="text-primary underline">Jolanoff’s Qwen dataset workflow</a>, based on acekiube’s face dataset workflow.
    </p>
  </div>
}
