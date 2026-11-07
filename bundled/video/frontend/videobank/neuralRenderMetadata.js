// Historical render metadata remains readable when the finishing plugin is absent.
export function neuralRenderTags(rec) {
  if (!rec || typeof rec !== 'object') return []
  const tags = []
  const num = (v, d) => (Number.isFinite(Number(v)) ? Number(v) : d)
  const tone = num(rec.tone, 1)
  const structure = num(rec.structure, 1)
  const strength = num(rec.strength, 1)
  const passes = num(rec.passes, 1)
  const scale = num(rec.scale, 1)
  if (tone !== 1) tags.push(`tone ${tone}`)
  if (structure !== 1) tags.push(`structure ${structure}`)
  if (strength !== 1) tags.push(`strength ×${strength}`)
  if (passes > 1) tags.push(`${passes} passes`)
  if (scale === 2) tags.push('2× render')
  if (rec.automask) tags.push('auto mask')
  const used = typeof rec.temporal_used === 'boolean' ? rec.temporal_used : rec.temporal === 'on'
  tags.push(used ? 'temporal' : 'still')
  if (Number.isFinite(Number(rec.ms_per_frame))) tags.push(`${Math.round(Number(rec.ms_per_frame))} ms/frame`)
  return tags
}
