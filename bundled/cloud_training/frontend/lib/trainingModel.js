// Cloud Training owns these recipe and lifecycle policies.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0; no private host imports.
export const TRAINING_MODE_LORA = 'lora';

export const TRAINING_MODE_FULL_TRANSFORMER = 'full_transformer';

export function normalizeTrainingMode(value) {
  return value === TRAINING_MODE_FULL_TRANSFORMER
    ? TRAINING_MODE_FULL_TRANSFORMER
    : TRAINING_MODE_LORA;
}

export function trainingModeLabel(value) {
  return normalizeTrainingMode(value) === TRAINING_MODE_FULL_TRANSFORMER
    ? 'Full model'
    : 'LoRA';
}

export function isFullTransformerRun(run) {
  return normalizeTrainingMode(run?.training_mode) === TRAINING_MODE_FULL_TRANSFORMER;
}

export function hfCloudTokenReadiness(payload = {}) {
  const check = Array.isArray(payload?.checks)
    ? payload.checks.find((item) => item?.id === 'hf_cloud_token')
    : null;
  const offerStatus = payload?.hf_cloud_token || null;
  const status = payload?.hf_cloud_token_status
    || payload?.hf_token_status
    || offerStatus
    || null;
  const combinedText = [...new Set([
    check?.detail,
    check?.hint,
    status?.error,
    status?.detail,
    payload?.error,
    payload?.hint,
  ].filter(Boolean).map(String))].join(' — ');
  const textSignalsTokenFailure = /HF_CLOUD_TOKEN|hugging\s*face[^\n]*token|token[^\n]*(scope|permission)/i
    .test(combinedText);
  const checkFailed = String(check?.status || '').toLowerCase() === 'fail';
  const statusFailed = status && (
    status.ok === false
    || status.configured === false
    || status.valid === false
    || status.ready === false
  );
  const offerStatusFailed = offerStatus && offerStatus.ok !== true;
  const signaled = !!check || !!status || textSignalsTokenFailure;
  const blocked = checkFailed || !!statusFailed || !!offerStatusFailed
    || (!check && !status && textSignalsTokenFailure);
  let detail = combinedText;
  if (!detail && blocked) {
    detail = status?.configured === false
      ? 'The dedicated HF_CLOUD_TOKEN is missing.'
      : 'The dedicated HF_CLOUD_TOKEN is invalid or does not have the required permissions.';
  }
  return {
    signaled,
    ready: !blocked,
    blocked,
    detail: detail || null,
  };
}

const isoDay = (value) => (/^\d{4}-\d{2}-\d{2}/.test(String(value || ''))
  ? String(value).slice(0, 10) : '');

export function fullTransformerArtifactView(run = {}, presence = null) {
  const presenceState = String(presence?.state || '').trim().toLowerCase();
  const status = String(run.artifact_status || '').trim().toLowerCase();
  const detail = String(run.artifact_status_detail ?? run.artifact_detail ?? '').trim();
  const available = status === 'available';
  const cleanupStatus = String(run.artifact_cleanup_status || '').trim().toLowerCase();
  // Older backend rows predate artifact_cleanup_status.  A kept pod with a
  // verified model is therefore pending by default unless cleanup is explicitly
  // complete; silence here could otherwise hide continued billing.
  const cleanupPending = available && run.status === 'error_pod_kept'
    && cleanupStatus !== 'complete';
  const cleanupDetail = String(run.artifact_cleanup_detail || '').trim();
  const rawRepositoryHref = String(run.hf_url || '').trim();
  const repositoryHref = /^https:\/\/huggingface\.co\//i.test(rawRepositoryHref)
    ? rawRepositoryHref
    : null;
  const href = available ? repositoryHref : null;

  if (available) {
    // Measured gone wins over the record: the delivery DID happen, and the
    // repository is not there any more. Both links are dropped — there is
    // nothing behind them but a 404, and "Inspect the repository (delivery
    // unverified)" would misname what the user is about to see.
    if (presenceState === 'gone') {
      return {
        status, available: false, presence: presenceState, cleanupPending,
        href: null, repositoryHref: null, tone: 'error',
        label: 'Full model no longer on Hugging Face',
        detail: 'This run delivered a verified full model, and the repository no '
          + 'longer answers: it was deleted or renamed, or the token can no longer '
          + 'see it. Nothing here can fetch it any more — check the Checkpoints '
          + 'panel for a copy on this computer before assuming it is lost.',
      };
    }
    const when = isoDay(run.verified_at || run.delivery_last_checked_at);
    const fresh = presenceState === 'present';
    return {
      status, available, presence: presenceState || null, cleanupPending,
      href, repositoryHref,
      tone: cleanupPending ? 'warning' : 'success',
      // Past tense unless something has actually asked the Hub just now. A
      // delivery is a fact about a moment; presence is a fact about this one.
      label: fresh ? 'Full model on Hugging Face' : 'Full model delivered',
      detail: cleanupPending
        ? (cleanupDetail
          || 'The model is verified, but pod cleanup has not been confirmed and the pod may still be billing.')
        : (fresh
          ? 'Checked just now: the private Hugging Face repository still holds this model.'
          : `Delivered and verified${when ? ` on ${when}` : ' at the end of the run'}`
            + ' — not re-checked since.'
            + (href ? ' Open the repository to confirm it is still there.'
              : ' This status does not include the repository link.')),
    };
  }
  if (status === 'missing') {
    // "No weights were verified IN the repository" presumes a repository to
    // look in. Once the Hub says there is none, the inspect link below is the
    // same dead end this whole change exists to stop offering.
    if (presenceState === 'gone') {
      return {
        status, available: false, presence: presenceState,
        href: null, repositoryHref: null, tone: 'error',
        label: 'Full model no longer on Hugging Face',
        detail: 'This run never delivered verified weights, and the repository '
          + 'itself no longer answers — it was deleted or renamed, or the token '
          + 'can no longer see it. There is nothing left here to inspect.',
      };
    }
    return {
      status, available: false, presence: presenceState || null,
      href: null, repositoryHref, tone: 'error',
      label: 'Full model not found',
      detail: detail || 'No full-model weights were verified in the repository. Check the run logs and Hugging Face repository before deleting any recovery copy.',
    };
  }
  if (status === 'verification_pending') {
    return {
      status, available: false, href: null, repositoryHref, tone: 'warning',
      label: 'Hugging Face verification pending',
      detail: detail || 'Check the dedicated HF_CLOUD_TOKEN in Settings ▸ Local tools and your connection, then refresh Runs. Do not treat the model as recoverable yet.',
    };
  }
  if (status === 'creating_repository' || status === 'pending' || status === 'uploading') {
    // 'pending' is stamped at LAUNCH and covers the whole run, so on its own it
    // cannot say whether weights are moving. Announcing 'Uploading full
    // model…' from it claimed a transfer that had not been started and could
    // not be: for the two hours run #138 spent pushing its DATASET to the pod,
    // this panel described the model going up to Hugging Face, next to a link
    // offering to inspect a repository holding nothing but licence files. The
    // run's own phase is what distinguishes them, and it is already here.
    const runStatus = String(run.status || '');
    const beforeTraining = ['preparing', 'provisioning', 'uploading'].includes(runStatus);
    const training = runStatus === 'training';
    // Delivery is the very end of a run, so anything that is no longer running
    // and still reads 'pending' never got there. Saying 'Uploading full model…'
    // on a terminated run is the worst version of this: it also tells the user
    // to keep a pod alive that the supervisor already destroyed.
    // An ABSENT status is not a finished run (an older payload, a caller that
    // does not carry one): claiming a delivery never happened is a statement,
    // and it is only made about a run whose phase actually says so.
    const ended = !!runStatus && !['preparing', 'provisioning', 'uploading',
      'training', 'downloading', 'terminating'].includes(runStatus);
    let label = 'Uploading full model…';
    let fallbackDetail = 'Keep the run and pod active until the repository is verified.';
    if (status === 'creating_repository') {
      label = 'Creating Hugging Face repository…';
    } else if (beforeTraining) {
      label = 'Full model not created yet';
      fallbackDetail = 'The run is still starting up — the weights are created on Hugging '
        + 'Face once training produces them. Nothing is uploading to Hugging Face yet.';
    } else if (training) {
      label = 'Full model not delivered yet';
      fallbackDetail = 'Training is running. The weights are delivered to Hugging Face at '
        + 'the end of the run — keep the run and pod active until then.';
    } else if (ended) {
      label = 'Full model was never delivered';
      fallbackDetail = 'The run ended before any weights reached Hugging Face, so the '
        + 'repository holds only the licence and model card. Check the run error above.';
    }
    return {
      status, available: false, href: null, repositoryHref,
      // A run that ended empty-handed is not neutral information.
      tone: ended && status !== 'creating_repository' ? 'warning' : 'info',
      label,
      detail: detail || fallbackDetail,
    };
  }
  return {
    status, available: false, href: null, repositoryHref, tone: 'warning',
    label: 'Full model status unavailable',
    detail: detail || 'Refresh Runs. If the status remains unavailable, check the run logs and your Hugging Face configuration.',
  };
}

export function fullTransformerArtifactFiles(run = {}) {
  const localAvailable = String(run.local_artifact_status || '').trim().toLowerCase() === 'available';
  const hubAvailable = String(run.artifact_status || '').trim().toLowerCase() === 'available';
  if (!localAvailable && !hubAvailable) return [];
  const files = [];
  const fp8Status = String(run.fp8_export_status || '').trim().toLowerCase();
  // A local delivery names the file that is on the disk; a Hugging Face one
  // names the object in the repository. Same two roles, two addresses — and the
  // note has to say which, or "download this one" points at nothing.
  const fp8Name = localAvailable
    ? (run.local_fp8_filename || null)
    : (fp8Status === 'done' ? run.fp8_weight_filename : null);
  if (fp8Name) {
    files.push({
      kind: 'fp8',
      name: String(fp8Name),
      sizeBytes: (localAvailable
        ? (typeof run.local_fp8_bytes === 'number' ? run.local_fp8_bytes : null)
        : (typeof run.fp8_size_bytes === 'number' ? run.fp8_size_bytes : null)),
      primary: true,
      note: localAvailable
        ? 'Use this one in ComfyUI — quantized fp8, already on this computer.'
        : 'Download this one for ComfyUI — quantized fp8, loads with the standard Load Diffusion Model node.',
    });
  }
  const masterName = localAvailable
    ? run.local_weight_filename
    : (run.fp8_keep_bf16 !== false ? run.hf_weight_filename : null);
  if (masterName) {
    files.push({
      kind: 'bf16',
      name: String(masterName).split('/').pop(),
      sizeBytes: (localAvailable
        ? (typeof run.local_weight_bytes === 'number' ? run.local_weight_bytes : null)
        : (run.hf_artifact_proof?.size_bytes ?? null)),
      primary: files.length === 0,
      note: files.length === 0
        ? 'Full-precision master. Usable in ComfyUI, but large.'
        : 'Full-precision master — keep it if you may ever continue training, merge or re-quantize.',
    });
  }
  return files;
}

export function denseQuantizeTarget(run = {}) {
  const files = fullTransformerArtifactFiles(run);
  if (!files.length || files.some((file) => file.kind === 'fp8')) return null;
  const master = files.find((file) => file.kind === 'bf16');
  if (!master || !run.hf_repo_id) return null;
  return {
    repoId: run.hf_repo_id,
    filename: String(run.hf_weight_filename || '').split('/').pop() || null,
    family: run.train_type || null,
    name: master.name,
    sizeBytes: master.sizeBytes,
    label: 'The full model this dataset’s run delivered',
  };
}

export function fullTransformerFp8Note(run = {}) {
  const status = String(run.fp8_export_status || '').trim().toLowerCase();
  if (status === 'failed') {
    return String(run.fp8_export_detail || '')
      || 'The fp8 export did not complete — the full-precision model was delivered.';
  }
  return null;
}

export function denseDelivery(run = {}) {
  const value = String(run.dense_delivery || '').trim().toLowerCase();
  return ['local', 'hub', 'both'].includes(value) ? value : 'hub';
}

function denseDeliversToHub(run = {}) {
  return isFullTransformerRun(run) && denseDelivery(run) !== 'local';
}

export function canRecheckFullTransformerDelivery(run = {}) {
  const artifactStatus = String(run.artifact_status || '').trim().toLowerCase();
  const cleanupPending = artifactStatus === 'available'
    && String(run.artifact_cleanup_status || '').trim().toLowerCase() !== 'complete';
  return isFullTransformerRun(run)
    // A run delivered to this computer only has no Hub delivery to verify —
    // offering the button would be a dead end with a confusing name.
    && denseDeliversToHub(run)
    && run.status === 'error_pod_kept'
    && (artifactStatus !== 'available' || cleanupPending);
}

export function fullTransformerRecheckOutcome(result = {}) {
  if (!result?.ok) {
    return {
      kind: 'error',
      text: result?.error
        || 'Hugging Face delivery could not be verified. The pod remains available for recovery.',
    };
  }
  if (result.delivery === 'available' && result.cleanup_pending) {
    return {
      kind: 'warning',
      text: 'Hugging Face model verified and available. Pod cleanup is still pending, and the pod may still be billing; retry cleanup.',
    };
  }
  if (result.delivery === 'available') {
    return {
      kind: 'success',
      text: 'Hugging Face delivery verified. The model is available and pod cleanup is confirmed.',
    };
  }
  return {
    kind: 'info',
    text: result.delivery === 'missing'
      ? 'No full-model weights were verified in the repository. The pod remains available for recovery; check its logs before deleting anything.'
      : 'Hugging Face verification is still pending. Fix HF_CLOUD_TOKEN if needed, then try again.',
  };
}

export function cloudTierEstimateView(tier = {}, { fullMode = false } = {}) {
  const status = tier.estimate_status == null
    ? null
    : String(tier.estimate_status).trim().toLowerCase();
  const explicitlyAvailable = ['available', 'estimated', 'ok'].includes(status);
  const explicitlyUnavailable = status === 'unavailable' || status === 'pending';
  const minutes = tier.est_minutes == null || tier.est_minutes === ''
    ? Number.NaN
    : Number(tier.est_minutes);
  const available = Number.isFinite(minutes)
    && minutes >= 0
    && !explicitlyUnavailable
    && (!fullMode || explicitlyAvailable);
  const rawCost = tier.est_cost == null || tier.est_cost === ''
    ? Number.NaN
    : Number(tier.est_cost);
  return {
    available,
    minutes: available ? minutes : null,
    cost: available && Number.isFinite(rawCost) && rawCost >= 0 ? rawCost : null,
    exceedsCap: available && tier.exceeds_cap === true,
    status,
  };
}

function isKreaTurboVariant(variant) {
  return !['', 'base', 'raw'].includes(String(variant ?? '').trim().toLowerCase());
}

export function fullTransformerBaseLabel({
  baseModel = '', baseLabel = '', variant = 'base',
} = {}) {
  const picked = String(baseModel || '').trim();
  if (picked) {
    return String(baseLabel || '').trim()
      || `custom: ${picked.split(/[\\/]/).pop()}`;
  }
  return isKreaTurboVariant(variant) ? 'official Krea 2 Turbo' : 'official Krea 2 Raw';
}

export function denseTurboWarning({ baseModel = '', variant = 'base' } = {}) {
  if (String(baseModel || '').trim() || !isKreaTurboVariant(variant)) return null;
  return {
    title: 'Full-model training on Krea 2 Turbo — untested here',
    body: 'Krea officially recommends training a LoRA on Raw and applying it to '
      + 'Turbo. We have not measured full-model training on a distilled base, so '
      + 'we cannot tell you what this run produces. On other distilled models it '
      + 'has been seen to erode few-step behaviour: the result may need real '
      + 'guidance and more steps than Turbo does today. Nothing is blocked — this '
      + 'is what is unknown, not a predicted failure.',
  };
}
