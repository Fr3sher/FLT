import { Card, TextField, SettingsLink } from '@lds/plugin-sdk/ui'

export default function CameraSettings({ config, setField }) {
  const camera = config?.camera || {}
  return <Card id="camera-models" title="Camera model preferences"
    help="Leave these fields blank for automatic model selection. An override pins an existing model file in ComfyUI; it does not download or install a model.">
    <TextField id="camera-unet" label="Qwen Image Edit model" value={camera.unet}
      onChange={(value) => setField('camera', 'unet', value)} placeholder="Automatic — installed Qwen Image Edit model"
      help="ComfyUI diffusion model filename. The Camera angles picker edits this same preference." />
    <details className="rounded-lg border border-border p-3">
      <summary className="min-h-10 cursor-pointer text-sm font-medium text-content">Advanced model overrides</summary>
      <div className="mt-3 space-y-4">
        <TextField id="camera-text-encoder" label="Text encoder" value={camera.text_encoder}
          onChange={(value) => setField('camera', 'text_encoder', value)} placeholder="Automatic" />
        <TextField id="camera-vae" label="VAE" value={camera.vae}
          onChange={(value) => setField('camera', 'vae', value)} placeholder="Automatic" />
        <TextField id="camera-angles-lora" label="Multiple-Angles LoRA" value={camera.angles_lora}
          onChange={(value) => setField('camera', 'angles_lora', value)} placeholder="Automatic" />
        <TextField id="camera-speed-lora" label="Lightning speed LoRA" value={camera.speed_lora}
          onChange={(value) => setField('camera', 'speed_lora', value)} placeholder="Automatic" />
      </div>
    </details>
    <SettingsLink section="local-tools" focus="comfyui-base-dir">Shared ComfyUI connection and folder</SettingsLink>
  </Card>
}
