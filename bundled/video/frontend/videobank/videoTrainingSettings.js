export function videoTrainingControls({ rank = 16, memory = 'auto', prompts = '' }, lane) {
  if (!Number.isInteger(rank) || rank < 1 || rank > 256) {
    throw new Error('LoRA rank must be an integer between 1 and 256.')
  }
  if (!['auto', 'on', 'off'].includes(memory)) throw new Error('Choose a memory mode.')
  const sample_prompts = prompts.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
  if (sample_prompts.some((s) => s.length > 2000)) {
    throw new Error('Each sample prompt must be at most 2000 characters.')
  }
  return { rank, sample_prompts, low_vram: memory === 'auto' ? lane === 'local' : memory === 'on' }
}
