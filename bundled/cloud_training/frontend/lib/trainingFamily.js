// Cloud Training owns these recipe and lifecycle policies.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0; no private host imports.
export const CUSTOM_BASE_SENTINEL = '__custom_weights__';

const ABSOLUTE_PATH = /^(?:[A-Za-z]:[\\/]|\\\\|\/)/;

export function looksAbsoluteBase(value) {
  return ABSOLUTE_PATH.test(String(value || ''));
}

export function baseOptionSuffix(entry) {
  if (!entry || !entry.value) return '';
  if (entry.trainable === false) return ' · packed export';
  if (entry.quantization === 'bare_cast') return ' · fp8 cast';
  return '';
}

const CLOUD_UNSUPPORTED = {
  sdxl: 'SDXL trains locally only — the cloud lane covers Z-Image, Krea 2 and FLUX.2 Klein',
  flux: 'FLUX.1 trains locally only — the cloud lane covers Z-Image, Krea 2 and FLUX.2 Klein',
  anima: 'Anima cloud training is coming once the pod image is verified — train it locally for now',
  qwenimage21: 'Qwen-Image 2.1 trains locally — the cloud environment is not verified for this model',
};

export function cloudUnsupportedFamilyReason(family) {
  return CLOUD_UNSUPPORTED[family] || null;
}
