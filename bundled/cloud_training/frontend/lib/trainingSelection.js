// Cloud Training owns these recipe and lifecycle policies.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0; no private host imports.
import { normalizeTrainingMode } from './trainingModel.js';

export function trainingRunSelection(baseModel, trainType, variant) {
  return {
    ...(baseModel !== undefined && baseModel !== null ? { base_model: baseModel } : {}),
    ...(trainType ? { train_type: trainType } : {}),
    ...(variant ? { variant } : {}),
  };
}

export function cloudTrainingLaunchPayload({
  baseModel = '', variant, trainType, trainingMode, masked, steps, gpuName,
} = {}) {
  return {
    base_model: baseModel,
    variant,
    train_type: trainType,
    training_mode: normalizeTrainingMode(trainingMode),
    // Presence-conditional, like `masked` in canvasContinueRequest: person masking
    // is a persisted DATASET setting now, so an OMITTED key means "the server reads
    // the dataset", not "true". Sending an optimistic default from a panel whose
    // settings had not loaded yet would overwrite a stored OFF on a PAID run.
    ...(typeof masked === 'boolean' ? { masked } : {}),
    ...(steps ? { steps } : {}),
    ...(gpuName ? { gpu_name: gpuName } : {}),
  };
}

export function trainFamilyLabel(type) {
  if (type === 'sdxl') return 'SDXL';
  if (type === 'krea') return 'Krea 2';
  if (type === 'flux') return 'FLUX.1';
  if (type === 'flux2klein') return 'FLUX.2 Klein';
  if (type === 'anima') return 'Anima';
  return 'Z-Image';
}
