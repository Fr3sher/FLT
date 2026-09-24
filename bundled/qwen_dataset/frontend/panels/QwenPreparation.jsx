import { useState } from 'react'
import { HelpBadge, useToast } from '@lds/plugin-sdk'
import { Card, SettingsLink } from '@lds/plugin-sdk/ui'
import { modelPreparationRows, qwenUnavailableReason } from '../lib/engine.js'

export default function QwenPreparation({ caps = {}, onDone }) {
  const toast = useToast()
  const [checking, setChecking] = useState(false)
  const status = caps.qwen_dataset
  const ready = status?.ok === true
  const recheck = async () => {
    setChecking(true)
    try {
      const result = await onDone?.()
      if (result === null) toast.error('Could not refresh preparation. Check the connection and try again.')
    }
    catch (error) { toast.error(error.message || 'Could not check Dataset Forge preparation.') }
    finally { setChecking(false) }
  }
  return <Card id="qwen-dataset-preparation" title="Prepare Qwen-Image 2.1"
    help="Connect your ComfyUI installation, prepare the three model files, then re-check. Compatible files already present are reused.">
    <p className={`text-sm ${ready ? 'text-emerald-300' : 'text-content-muted'}`} role="status">
      {ready ? 'Ready — ComfyUI reports the required nodes and model files.' : qwenUnavailableReason(caps)}
      <HelpBadge topic="qwen-dataset-prepare" className="ml-1" />
    </p>
    <p className="text-xs text-content-subtle">
      The default INT8 model, encoder and VAE total about 17.3 GB. Generations run on your GPU.
      The model weights use the{' '}
      <a href="https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE" target="_blank" rel="noreferrer"
        className="text-primary underline">Qwen Research licence (non-commercial)</a>.
    </p>
    {!caps.comfyui?.dir_valid && <p className="text-sm text-content-muted">
      <SettingsLink section="local-tools" focus="comfyui-base-dir" tone="warning">Connect your local ComfyUI folder</SettingsLink>
    </p>}
    <div className="space-y-3">
      {modelPreparationRows(caps).map(row => <div key={row.action} className="space-y-1">
        <p className="text-sm text-content-muted">{row.present ? '✓ ' : ''}{row.label}</p>
        {!row.present && <p className="text-xs text-content-subtle">{row.available
          ? 'Use Preparation to install or repair this file.' : row.hint}</p>}
      </div>)}
    </div>
    {status?.missing_nodes?.length > 0 && <p className="text-xs text-amber-300">
      Update ComfyUI using its normal updater, then restart it when idle. Missing nodes:{' '}
      <span className="break-words">{status.missing_nodes.join(', ')}</span>.
    </p>}
    <button type="button" onClick={recheck} disabled={checking}
      className="min-h-10 self-start rounded-md border border-border px-3 py-2 text-sm text-content disabled:opacity-50">
      {checking ? 'Checking…' : 'Re-check preparation'}
    </button>
  </Card>
}
