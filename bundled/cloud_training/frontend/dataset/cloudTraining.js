import { cloudUnsupportedFamilyReason } from '../lib/trainingFamily.js';
import { trainingRunSelection } from '../lib/trainingSelection.js';
import { postJson } from '@lds/plugin-sdk';

export function cloudDisabledReasonFor(form, cloudStatus = {}) {
  const { caps, fullMode, fullTransformerEligible, fullTransformerReason, trainType,
    vaePath, tePath, customWeightsEmpty, baseNotTrainable, baseBlocksTrain,
    belowFloor, keptCount, sliderOn, typeLabel, trainMinFloor } = form;
  const activeCount = (cloudStatus.actives || (cloudStatus.active ? [cloudStatus.active] : [])).length;
  const limit = cloudStatus.limit || 1;
  const cloudTooFewImages = belowFloor;
  const cloudLimitReached = activeCount >= limit;
  // Familles que la voie cloud ne sert pas — miroir des refus AVANT réservation
  // côté serveur. Anima y manquait : au-dessus du plancher d'images le bouton
  // s'activait et n'était refusé qu'après le clic.
  const cloudFamilyBlock = cloudUnsupportedFamilyReason(trainType);
  return !caps.cloud_training
      ? 'Cloud training needs a vast.ai API key — add it in Settings'
    : fullMode && !fullTransformerEligible
      ? (fullTransformerReason || 'Full-model training is a Krea 2 recipe')
    : cloudFamilyBlock
      ? cloudFamilyBlock
    : (vaePath || tePath)
      ? 'Custom VAE/text-encoder overrides are local-only — clear them in Advanced options to train in the cloud'
    : customWeightsEmpty
      ? 'Enter the path to your custom weights .safetensors first'
    : baseNotTrainable
      ? 'This checkpoint cannot be loaded for training — pick the bf16/fp16 version of it'
    : baseBlocksTrain
      ? 'Convert the custom base first — the cloud lane pushes the converted copy to your Hugging Face account'
    : cloudTooFewImages
      ? `Only ${keptCount} image(s) kept — the cloud minimum for ${sliderOn ? 'a slider' : typeLabel} is ${trainMinFloor}`
    : cloudLimitReached
      ? `Cloud run limit reached (${activeCount}/${limit}) — stop one or raise the limit in Settings`
    : null;

}

export const cloudContinueLane = {
  id: 'cloud', label: 'Cloud',
  runsUrl: '/api/dataset/train/cloud/runs?limit=50',
  request({ node, body }) {
    if (node.source === 'cloud' && node.run_id != null) {
      const { base_model: _base, train_type: _type, variant: _variant, masked: _masked, ...extra } = body;
      return { url: '/api/dataset/train/cloud/continue', body: { run_id: node.run_id, ...extra } };
    }
    return node.dataset_id == null ? null : {
      url: `/api/dataset/${node.dataset_id}/train/cloud/continue-local`, body,
    };
  },
  availability(ctx) {
    const reason = ctx.fullMode
      ? 'Continuing a full model is not available. Switch back to LoRA to continue a LoRA.'
      : cloudDisabledReasonFor(ctx.form, ctx.cloudRunView?.status);
    return reason ? { available: false, reason } : { available: true };
  },
  async resume(payload, { ds, base, variant, trainType, opts, toast }) {
    const body = {
      extra_steps: payload.extraSteps,
      ...trainingRunSelection(base, trainType, variant),
      ...(typeof opts.masked === 'boolean' ? { masked: opts.masked } : {}),
      allow_caption_mismatch: !!opts.allowCaptionMismatch,
      allow_uncaptioned: !!opts.allowUncaptioned,
      allow_unverified_weights: !!opts.allowUnverifiedWeights,
      allow_caption_quality: !!opts.allowCaptionQuality,
      allow_not_ready: !!opts.allowNotReady,
      allow_parallel_run: !!opts.allowParallelRun,
      ...(opts.fromStep != null ? { from_step: opts.fromStep } : {}),
      ...(opts.expectedRecordId != null ? { expected_record_id: opts.expectedRecordId } : {}),
      ...(opts.overrides ? { overrides: opts.overrides } : {}),
      resume_mode: opts.resumeMode || 'weights_only',
      ...(opts.stateBundleId ? { state_bundle_id: opts.stateBundleId } : {}),
      ...((payload.gpuName || opts.gpuName) ? { gpu_name: payload.gpuName || opts.gpuName } : {}),
    };
    let d;
    try {
      d = await postJson(`/api/dataset/${ds.currentId}/train/cloud/continue-local`, body);
    } catch (error) {
      return { ...error?.body, ok: false, error: error?.message || 'Cloud continuation failed' };
    }
    if (d.ok) toast?.success(`Cloud run started from step ${d.resumed_from} → ${d.target_steps}`);
    return d;
  },
};
