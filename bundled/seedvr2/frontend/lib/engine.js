export const SEEDVR2_ENGINE = {
    id: 'seedvr2',
    label: 'SeedVR2',
    emoji: '🔍',
    action: 'Upscale via SeedVR2',
    summary: 'Resolves detail at a higher resolution and keeps the original look.',
    confirm: 'Create a separate SeedVR2 upscale candidate',

  ready: caps => caps?.comfyui?.seedvr2_ready === true,
  blockedReason: 'SeedVR2 is not ready yet — open SeedVR2 Setup to prepare it.',
}
