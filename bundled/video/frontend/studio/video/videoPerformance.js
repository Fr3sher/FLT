export const PERFORMANCE_DEFAULTS = {
  fused: false, h3_attention: 'auto', h3_spectrum: false,
  h3_video_vae: 'fp16', h3_video_writer: 'native',
};

export function performanceSettings(value = {}) {
  value ||= {};
  return {
    fused: value.fused === true,
    h3_attention: ['auto', 'native', 'sage'].includes(value.h3_attention) ? value.h3_attention : 'auto',
    h3_spectrum: value.h3_spectrum === true,
    h3_video_vae: value.h3_video_vae === 'int8' ? 'int8' : 'fp16',
    h3_video_writer: value.h3_video_writer === 'fast' ? 'fast' : 'native',
  };
}

export function referenceBaseMissing(base, value, performance) {
  if (base?.available === false) return true;
  if (base?.ready !== false) return false;
  // INT8 replaces FP16; it must not require downloading both decoders.
  return !(value.h3_video_vae === 'int8' && performance?.int8?.available === true
    && base.nodes_ready === true && Array.isArray(base.missing_weights)
    && base.missing_weights.every(item => item.action === 'h3_video_vae'));
}
