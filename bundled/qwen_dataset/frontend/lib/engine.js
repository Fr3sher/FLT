export const QWEN_ENGINE = {
  id: 'qwen_dataset', label: 'Qwen-Image 2.1', kind: 'local', order: 1,
  rate: 0, remote: false, billable: false, secret: null, keyTestTarget: null,
  recommended: true, modelSettingKey: null, referenceEdit: false,
  settingsLabel: 'Qwen-Image 2.1 (ComfyUI, local)', shortLabel: 'Qwen 2.1 (local)',
  setupRow: null,
  accent: {
    card: 'border-amber-400/60 bg-amber-500/15 ring-1 ring-amber-400/40',
    title: 'text-amber-200', text: 'text-amber-300', icon: 'text-amber-300',
    pill: 'bg-amber-500/25 text-amber-200', dot: 'bg-amber-400',
  },
  card: () => import('../panels/QwenCard.jsx'),
}

export function qwenUnavailableReason(caps = {}, enabledInSettings = true) {
  if (!enabledInSettings) return 'Enable Qwen-Image 2.1 in Dataset Forge settings.'
  if (!caps.comfyui?.reachable) return 'Start ComfyUI and check its connection.'
  const status = caps.qwen_dataset
  if (!status) return 'Check Dataset Forge preparation.'
  if (status.missing_nodes?.length) return 'Update ComfyUI, restart when idle, then re-check.'
  if (status.missing?.length || status.invalid?.length) return 'Prepare the Qwen model files.'
  return status.detail || 'Re-check Dataset Forge preparation.'
}

export const MODEL_ACTIONS = [
  { action: 'qwen_dataset_model', field: 'unet', label: 'Qwen-Image 2.1 model' },
  { action: 'qwen_dataset_text_encoder', field: 'text_encoder', label: 'Qwen3-VL text encoder' },
  { action: 'qwen_dataset_vae', field: 'vae', label: 'Qwen-Image 2.1 VAE' },
]

export function setupRows(caps) {
  return [{ label: 'Qwen-Image 2.1 dataset generation',
    what: 'Create dataset variations on your own GPU from reference photos',
    ok: caps?.qwen_dataset?.ok === true, topic: 'qwen-dataset-prepare' }]
}

export function modelPreparationRows(caps = {}) {
  const status = caps.qwen_dataset
  const missing = new Set([...(status?.missing || []), ...(status?.invalid || [])])
  return MODEL_ACTIONS.map(({ action, field, label }) => ({
    action, label,
    present: !!status?.models?.[field] && !missing.has(action),
    available: !!caps.comfyui?.dir_valid,
    hint: caps.comfyui?.dir_valid ? '' : 'Choose the ComfyUI folder in Local tools first.',
  }))
}
