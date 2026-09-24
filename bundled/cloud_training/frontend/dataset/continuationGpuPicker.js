import { lazy } from 'react';

// Keep descriptors importable without loading UI or contacting a provider.
const Component = lazy(() => import('./ContinueGpuPicker.jsx'));

export function continuationGpuPicker(run) {
  return { Component, props: {
    datasetId: run.dataset_id, trainType: run.train_type, variant: run.variant,
    trainingMode: run.training_mode || 'lora',
  } };
}
