import { setting, action } from '@lds/plugin-sdk/help'
export const HELP = [
  setting('image_upscale.default_engine', 'engines', 'improve-engine', 'Default image improvement engine',
    ['improve.engine', 'improve', 'restoration', 'default', 'active plugins', 'klein', 'seedvr2']),
  action('action-bank-improve', 'Upscale & improve images inside a bank',
    ['upscale', 'upscaling', 'improve', 'enhance', 'sharpen', 'super resolution',
     'super-resolution', 'klein', 'seedvr2', 'seedvr', 'low resolution', 'small',
     'blurry', 'soft', 'quality', 'gpu', 'comfyui', 'bank', 'batch', 'pass',
     'before promoting', 'without dataset', 'stop'],
    '/bank', 'using-the-app', 'crop-and-upscale-inside-a-bank'),

  action('action-edit-improve-instruction', 'Edit the improve instruction without leaving the images',
    ['improve', 'upscale', 'instruction', 'prompt', 'edit', 'edit here', 'inline', 'in place',
     'window', 'modal', 'popup', 'settings window', 'generate button',
     'change the prompt', 'turn off', 'disable', 'toggle', 'no prompt', 'upscale only',
     'klein', 'anime', 'drawn', 'realistic', 'texture', 'skin', 'detail', 'lightbox',
     'reset to default', 'built-in default', 'global', 'app-wide', 'every dataset',
     'applies everywhere', 'same as settings',
     // The same note now also picks the LoRA preset the pass chains
     // (klein.improve_lora_preset) — one panel, all three improve knobs.
     'lora preset', 'improve preset', 'chain lora', 'preset', 'extra loras'],
    '/datasets?section=images', 'settings-reference', 'image-engines'),

  action('action-reimprove-tile', 'Re-run Upscale & improve after changing its settings',
    ['improve', 'upscale', 'reimprove', 're-improve', 'rerun', 're-run', 'redo', 'again',
     'regenerate', 'no regenerate button', 'missing button', 'klein improve', 'candidate',
     'steps', 'megapixels', 'strength', 'try again', 'source image', 'parent'],
    '/datasets?section=images', 'settings-reference', 'image-engines'),

  action('action-canvas-improve', 'Upscale a picture from the board or its gallery',
    ['canvas', 'board', 'improve', 'upscale', 'upscale & improve', 'enhance', 'klein',
     'seedvr2', 'sharpen', 'detail', 'resolution', 'megapixels', 'lightbox',
     'pinned image', 'generated image', 'where did it go', 'result', 'gallery',
     'checkpoint gallery', 'improve from canvas', 'no improve button',
     'improve an improvement', 'reference face', 'retry', 'failed upscale',
     'improve from the gallery', 'upscale from the gallery', 'run gallery',
     'gallery lightbox', 'improve a test image', 'improve a render',
     'gallery did not update', 'upscale not showing'],
    '/canvas', 'using-the-app', 'upscale-a-picture-straight-from-the-board'),

  setting('identity_prompts.klein_improve', 'engines', 'identity-prompt-klein-improve', 'Klein improve prompt & toggle',
    ['klein', 'improve', 'upscale', 'enhance', 'prompt', 'texture', 'detail', 'toggle', 'disable',
     'anime', 'drawn', 'illustration', 'cartoon', 'too realistic', 'realistic', 'photoreal',
     'textures', 'skin detail', 'skin', 'improve prompt', 'turn off improve', 'quality inpaint',
     'inpaint', 'ruins my images', 'harms the image', 'style changed', 'no prompt']),
  setting('klein.improve_strength', 'engines', 'klein-improve-strength', 'Upscale & improve — strength',
    ['improve', 'upscale', 'strength', 'megapixels', 'resolution', 'steps',
     'enhancement lora', 'consistency', 'klein', 'how much', 'change']),
setting('improve.colour_match', 'engines', 'improve-colour-match', "Put the source's colours back",
    ['colour match', 'color match', 'colour shift', 'color shift', 'skin warms', 'skin cools',
     'grade', 'mkl', 'two colour worlds', 'klein colours', 'finishing', 'finish']),
  setting('improve.sharpen', 'engines', 'improve-sharpen', 'Sharpen (finishing pass)',
    ['sharpen', 'unsharp', 'sharpness', 'soft', 'blurry', 'halo', 'finest detail',
     'finishing', 'finish', 'after improve']),
  setting('improve.grain', 'engines', 'improve-grain', 'Film grain (finishing pass)',
    ['grain', 'film grain', 'noise', 'plastic', 'smooth', 'waxy', 'photographic',
     'looks like a render', 'finishing', 'finish']),
  setting('improve.grain_saturation', 'engines', 'improve-grain-sat', 'How coloured the grain is',
    ['grain saturation', 'coloured grain', 'colored grain', 'luminance grain', 'sensor noise',
     'chroma noise', 'grain colour']),


].map(topic => {
  if (topic.id === 'action-bank-improve') return topic
  if (topic.id === 'action-canvas-improve') return { ...topic, app: { ...topic.app, route: '/gallery' } }
  const anchor = topic.id.startsWith('improve.') ? 'improve-finishing' : 'klein-improvement-settings'
  return { ...topic, guide: { chapter: 'settings-reference', anchor } }
})

for (const topic of HELP) {
  if (topic.id === 'image_upscale.default_engine') topic.app.sharedSetting = 'improve.engine'
  const route = topic.app?.route
  if (route?.startsWith('/settings/') || route?.startsWith('/setup')) {
    topic.app = { ...topic.app, route: '/plugins/image_upscale/settings',
      ...(route.startsWith('/settings/') ? { legacyRoute: route } : {}) }
  }
}
