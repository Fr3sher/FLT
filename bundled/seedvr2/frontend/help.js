import { action, setting, setupStep } from '@lds/plugin-sdk/help'
export const HELP = [
  setting('seedvr2.default_engine', 'engines', 'improve-engine', 'Default image improvement engine',
    ['improve.engine', 'improve', 'restoration', 'default', 'active plugins', 'klein', 'seedvr2']),
  action('action-seedvr2-restore', 'Restore images with SeedVR2',
    ['seedvr2', 'upscale', 'restore', 'bank', 'dataset', 'gallery', 'fidelity'],
    '/bank', 'settings-reference', 'seedvr2-upscaling-local'),
  setting('seedvr2.finish_sharpen', 'engines', 'seedvr2-finish-sharpen', 'SeedVR2 finishing sharpness', ['seedvr2', 'sharpen', 'finishing']),
  setting('seedvr2.finish_grain', 'engines', 'seedvr2-finish-grain', 'SeedVR2 film grain', ['seedvr2', 'grain', 'finishing']),
  setting('seedvr2.finish_grain_saturation', 'engines', 'seedvr2-finish-grain-saturation', 'SeedVR2 grain colour', ['seedvr2', 'grain colour', 'finishing']),
  setting('seedvr2.tiling', 'engines', 'seedvr2-tiling', 'High-resolution tiling',
    ['tiling', 'tile', 'tiles', 'seedvr2 tiling', 'TTP', 'Comfyui_TTP_Toolset',
     'high resolution', '4k', 'detail', 'artifacts', 'seam', 'seams', 'vram',
     'out of memory', 'oom', 'always', 'never', 'auto', 'overlap', 'tile boundaries', 'nine tiles']),
  setting('seedvr2.tile_px', 'engines', 'seedvr2-tile-px', 'SeedVR2 tile size',
    ['tile size', 'tile px', 'tile', 'seedvr2 vram', 'out of memory', 'oom', 'cuda',
     '8gb', '8 gb', 'small card', 'smaller card', 'upscale fails', 'upscale crashes',
     'seam', 'seams', '512', '768', '1024', 'encode_tile_size', 'decode tile']),
  setting('seedvr2.tile_threshold', 'engines', 'seedvr2-tile-threshold',
    'SeedVR2 tiling threshold',
    ['tiling threshold', 'start tiling above', 'crossover', 'when does it tile',
     'tile sooner', 'seedvr2 auto tiling', '1536', 'short edge']),
  setting('seedvr2.vae', 'engines', 'seedvr2-vae', 'SeedVR2 VAE build',
    ['seedvr2 vae', 'vae', 'ema_vae_fp16', 'vae not found', 'pin the vae',
     'renamed vae', 'models/SEEDVR2', 'model location', 'dit', 'weights folder']),
  setupStep('setup-seedvr2-install', 'install', 'Prepare SeedVR2 nodes and models',
    ['seedvr2', 'seed vr2', 'seedvr', 'upscale', 'upscaler', 'upscaling', 'super resolution',
     'super-resolution', 'restore', 'restoration', 'sharpen', 'fidelity', 'keeps colours',
     'colour shift', 'color shift', 'changes the image', 'node pack',
     'ComfyUI-SeedVR2_VideoUpscaler', 'prepare', 'restart', 're-check', 'dit', 'vae', 'models/SEEDVR2',
     '3b', '7b', 'fp8', 'blocks to swap', 'target resolution', 'install seedvr2']),
].map(topic => ({ ...topic, guide: { chapter: 'settings-reference', anchor: 'seedvr2-upscaling-local' } }))

for (const topic of HELP) {
  if (topic.id === 'seedvr2.default_engine') topic.app.sharedSetting = 'improve.engine'
  const route = topic.app?.route
  if (route?.startsWith('/settings/') || route?.startsWith('/setup')) {
    topic.app = { ...topic.app, route: '/plugins/seedvr2/settings',
      ...(route.startsWith('/settings/') ? { legacyRoute: route } : {}) }
  }
}
