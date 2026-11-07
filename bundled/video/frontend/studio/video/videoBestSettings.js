import { performanceSettings } from './videoPerformance.js';
export const videoBestUrl = (datasetId) => `/api/video-dataset/${datasetId}/best-settings`;
export const saveVideoBestUrl = (clipId) => `/api/video-studio/clip/${clipId}/best`;
export function bestForLoraUrl(lora) {
  const query = new URLSearchParams({ lora: lora?.lora || '' });
  if (lora?.runId) query.set('run_id', lora.runId);
  if (lora?.datasetId) query.set('dataset_id', lora.datasetId);
  return `/api/video-studio/best-settings?${query}`;
}

/** Only rendering dials: the current motion, start/end frames and shot plan stay. */
export function bestToControls(best, options, currentOptions) {
  const s = best.settings;
  return {
    mode: s.mode, aspect: s.aspect === 'auto' ? 'landscape' : s.aspect,
    lora: { lora: s.lora, runId: best.run_id, datasetId: best.dataset_id },
    strength: s.lora_strength,
    opts: { ...currentOptions, ...performanceSettings(s), frames: s.frames, megapixels: s.megapixels,
      steps: s.steps, seed: s.seed, accel: s.accel, sparse: s.sparse,
      latentUpscale: s.latent_upscale,
      eros: s.base_model === options?.base_eros,
      light: s.base_model === options?.base_light },
  };
}

export function bestUnavailable(best, options, mode) {
  if (mode === 'ref2va' || best?.settings?.mode === 'ref2va') return 'Best settings do not support References yet. Use Reuse on a reference clip to restore its settings.';
  if (!options) return 'Wait for the Studio options to load.';
  const s = best.settings;
  if (![options.base_official, options.base_eros, options.base_light, options.performance?.fused?.filename].includes(s.base_model)) return 'The saved base model is not available in this Studio.';
  if (s.base_model === options.base_eros && options.eros_available === false) return 'Install the saved 10Eros base to apply these settings.';
  if (s.base_model === options.base_light && options.light?.available === false) return 'The saved W4A8 base is unavailable on this ComfyUI.';
  if (s.accel && options.accelerations?.find((a) => a.id === s.accel)?.available === false) return 'Install the saved acceleration to apply these settings.';
  if (s.sparse && options.options_available?.sparse?.available === false) return 'Install sparse attention to apply these settings.';
  if (s.latent_upscale && options.options_available?.latent_upscale?.available === false) return 'Install latent upscale to apply these settings.';
  return '';
}
