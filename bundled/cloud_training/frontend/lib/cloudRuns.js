// Cloud Training owns these recipe and lifecycle policies.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0; no private host imports.
import { trainFamilyLabel } from './trainingSelection.js';

function baseModelBasename(value) {
  const trimmed = String(value || '').replace(/[\\/]+$/, '');
  const leaf = trimmed.split(/[\\/]/).pop();
  return leaf || trimmed;
}

export function runBaseModelLabel(run) {
  if (!run) return null;
  const raw = run.base_model;
  if (raw == null) return null;                       // legacy row: not recorded
  const custom = String(raw).trim();
  if (custom) {
    const name = baseModelBasename(custom);
    return { text: name, title: `Custom base: ${name}`, custom: true };
  }
  const family = trainFamilyLabel(run.train_type);
  const variant = trainingRunVariantLabel(run.train_type, run.variant);
  const text = variant ? `${family} ${variant}` : family;
  return { text, title: `Official base: ${text}`, custom: false };
}

export function trainingRunVariantLabel(trainType, variant) {
  if (!variant) return null;
  if (variant === 'base') return trainType === 'krea' ? 'Raw' : 'Base';
  if (variant === 'deturbo') return 'De-Turbo';
  if (variant === 'turbo') return 'Turbo';
  return variant.toUpperCase();
}

export function retryRequest(run) {
  if (run?.source === 'local') {
    return run.record_id != null
      ? { url: '/api/dataset/train/retry', body: { record_id: run.record_id } }
      : null;
  }
  return run?.run_id != null
    ? { url: '/api/dataset/train/cloud/retry', body: { run_id: run.run_id } }
    : null;
}

export function runRetryKey(run) {
  return run?.source === 'local' ? `l${run?.record_id}` : `c${run?.run_id}`;
}

const REPLAY_BLOCKING_RECIPE_STATUSES = new Set(['legacy_incompatible', 'incompatible']);

export function isTrainingRecipeReplayBlocked(run) {
  const status = run?.recipe_status ?? run?.recipe?.status ?? run?.status;
  return REPLAY_BLOCKING_RECIPE_STATUSES.has(status);
}
