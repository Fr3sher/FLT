import { buildGeneratePayload } from '../studio/video/videoStudioApi.js'

export const videoPreviewsUrl = (id) => `/api/video-dataset/${id}/train/previews`

export function previewSelector(node, pill) {
  return { run_id: node.source === 'local' ? null : node.run_id,
    step: pill.step ?? null, final: !!pill.final }
}

export function previewKey(s) {
  return `${s.run_id == null ? 'local' : `cloud-${s.run_id}`}:${s.final ? 'final' : `step-${s.step}`}`
}

export function previewLabel(s) {
  return `${s.run_id == null ? 'Local' : `Run #${s.run_id}`} · ${s.final ? 'Final' : 'Step'}${s.step == null ? '' : ` ${s.step}`}`
}

export function previewChoices(tree) {
  return (tree?.nodes || []).flatMap((node) => (node.checkpoints || []).map((pill) => {
    const selector = previewSelector(node, pill)
    return { key: previewKey(selector), selector, label: previewLabel(selector),
      eligible: pill.present !== false && pill.render_capability?.ok === true,
      reason: pill.render_capability?.reason || 'Rendering availability could not be checked.' }
  }))
}

export function previewRequest({ choices, selected, prompt, mode, source, endFrame, aspect, strength, opts }) {
  if (!['t2v', 'i2v'].includes(mode)) throw new Error('Choose text-to-video or image-to-video.')
  const picks = choices.filter((c) => selected.includes(c.key))
  if (!picks.length) throw new Error('Select at least one checkpoint.')
  if (picks.length !== selected.length || picks.some((c) => !c.eligible)) {
    throw new Error('A selected checkpoint is no longer available. Review the selection.')
  }
  if (!prompt.trim()) throw new Error('Describe the motion to render.')
  if (mode === 'i2v' && !source?.image) throw new Error('Pick the shared start frame.')
  if (strength === '' || !Number.isFinite(Number(strength)) || Number(strength) < 0 || Number(strength) > 2) {
    throw new Error('Choose a LoRA strength between 0 and 2.')
  }
  return { ...buildGeneratePayload({ ...opts, mode, prompt, aspect,
    image: source?.image, ratio: source?.ratio, endImage: endFrame?.image }),
    lora_strength: Number(strength), checkpoints: picks.map((p) => p.selector) }
}

export function previewBatchNotice(result) {
  const queued = result?.queued?.length || 0
  const failures = result?.failures || []
  return `${queued} preview${queued === 1 ? '' : 's'} queued`
    + (result?.seed != null ? ` · shared seed ${result.seed}` : '')
    + (failures.length ? `. ${failures.length} failed: ${failures.map((f) => `${previewLabel(f.selector)}: ${f.error}`).join('; ')}` : '.')
}

export const hasPendingPreviews = (previews) => previews.some((p) => ['pending', 'running', 'queued'].includes(p.status))
