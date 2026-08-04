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

/** Payload used by the atomic recipe-settings endpoint. Keep the official base
 * explicit (`base_model: ''`): omitting it would ask the server to reuse an old
 * custom base, which is not the dense Krea Raw recipe selected in the UI. */
export function trainingModeSettingsPayload(trainingMode, selection = {}) {
  const payload = { training_mode: normalizeTrainingMode(trainingMode) };
  if (selection.trainType !== undefined) payload.train_type = selection.trainType;
  if (Object.prototype.hasOwnProperty.call(selection, 'baseModel')) {
    payload.base_model = selection.baseModel == null ? '' : String(selection.baseModel);
  }
  if (selection.variant !== undefined) payload.variant = selection.variant;
  if (selection.disableSliderForFullTransformer === true) {
    payload.disable_slider_for_full_transformer = true;
  }
  return payload;
}

/** Normalize the two backend surfaces that can report whether a dense run may
 * use the dedicated Hugging Face delivery token. Missing metadata is not a
 * refusal (older servers did not expose it); an explicit failed check/status is. */
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

/** A full model is useful only after the backend has verified the Hub contents.
 * The model CTA stays gated by `artifact_status`; `hf_url` alone may expose only
 * a clearly labelled repository-inspection link while delivery is unverified. */
export function fullTransformerArtifactView(run = {}) {
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
    return {
      status, available, cleanupPending, href, repositoryHref,
      tone: cleanupPending ? 'warning' : 'success',
      label: 'Full model available',
      detail: cleanupPending
        ? (cleanupDetail
          || 'The model is verified, but pod cleanup has not been confirmed and the pod may still be billing.')
        : detail || (href
        ? 'The private Hugging Face repository contents have been verified.'
        : 'The contents were verified, but this status does not include the repository link.'),
    };
  }
  if (status === 'missing') {
    return {
      status, available: false, href: null, repositoryHref, tone: 'error',
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

/** The files a delivered full model actually contains, and which one to take.
 *
 * A dense run delivers a ~26 GB bf16 master and (when the export ran) a ~10 GB
 * fp8 twin. They are NOT interchangeable and the difference is the whole point:
 * the fp8 file is what ComfyUI loads to generate; the bf16 file is the only one
 * that can be trained again, merged or re-quantized. Listing them without
 * saying which is which is how someone downloads 26 GB they cannot use, or
 * deletes the only copy they could have continued from.
 *
 * Returns [] for a run that has not delivered — nothing to choose between.
 */
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

/** The model the fp8 tool should aim at on its own, or null.
 *
 * This is what turns "paste an absolute path" into one click, and it is
 * deliberately derived from the SAME `hf_weight_filename` the artifact card
 * lists above it: a dense repository holds the final save and several ~26 GB
 * step snapshots whose names differ by a number, and the card naming one while
 * the operation took another is exactly the bug this closes. One value, read
 * once, handed to both.
 *
 * Null when there is nothing to aim at: no delivered master, or an fp8 twin the
 * run already produced (converting it again would only lose precision).
 */
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

/** Why an expected fp8 export is not in the list. Never an error state: the
 * bf16 master is delivered either way, so this is a missing convenience. */
export function fullTransformerFp8Note(run = {}) {
  const status = String(run.fp8_export_status || '').trim().toLowerCase();
  if (status === 'failed') {
    return String(run.fp8_export_detail || '')
      || 'The fp8 export did not complete — the full-precision model was delivered.';
  }
  return null;
}

/** Where a full model is delivered. An older run carries no stamp at all: it was
 * delivered to Hugging Face and nothing else, which is what it must keep
 * meaning — reading a missing value as today's default would claim a local file
 * that never existed. */
export function denseDelivery(run = {}) {
  const value = String(run.dense_delivery || '').trim().toLowerCase();
  return ['local', 'hub', 'both'].includes(value) ? value : 'hub';
}

export function denseDeliversLocally(run = {}) {
  return isFullTransformerRun(run) && denseDelivery(run) !== 'hub';
}

export function denseDeliversToHub(run = {}) {
  return isFullTransformerRun(run) && denseDelivery(run) !== 'local';
}

/** The state of the copy on THIS computer, as a card can render it.
 * Returns null for a run that has no local delivery — there is nothing to say
 * about a file that was never meant to exist. */
export function denseLocalArtifactView(run = {}) {
  if (!denseDeliversLocally(run)) return null;
  const status = String(run.local_artifact_status || '').trim().toLowerCase();
  const detail = String(run.local_artifact_detail || '').trim();
  const dir = String(run.local_artifact_dir || '').trim();
  const name = String(run.local_weight_filename || '').trim();
  const ended = !!run.status && !['preparing', 'provisioning', 'uploading',
    'training', 'downloading', 'terminating'].includes(String(run.status));
  if (status === 'available') {
    return {
      status, available: true, tone: 'success', dir, name,
      label: 'Full model on this computer',
      detail: detail || 'Downloaded from the pod and verified.',
    };
  }
  if (run.status === 'downloading' || run.dense_fetch_active) {
    return {
      status, available: false, tone: 'info', dir, name,
      label: 'Downloading the full model…',
      detail: String(run.phase_detail || '')
        || 'The pod is kept until the file here is complete and verified.',
    };
  }
  return {
    status, available: false, tone: ended ? 'warning' : 'info', dir, name,
    label: ended ? 'Full model not downloaded' : 'Full model not downloaded yet',
    detail: detail || (ended
      ? 'The pod is kept so it can be fetched again. Free disk space if that is what stopped it.'
      : 'It is downloaded at the end of the run, and the pod is kept until it is verified.'),
  };
}

/** The Hugging Face BACKUP of a run that is delivered here first.
 * A different question from fullTransformerArtifactView, which describes the
 * artifact itself: once the model is on this computer, the Hub copy is only
 * about being able to continue this run later, and a failed backup must not
 * read as a lost model. Returns null for a hub-only run — that one keeps the
 * original view, unchanged. */
export function denseHubBackupView(run = {}) {
  if (!denseDeliversLocally(run) || !denseDeliversToHub(run)) return null;
  const state = String(run.hub_backup_status || '').trim().toLowerCase();
  const detail = String(run.hub_backup_detail || '').trim();
  const href = /^https:\/\/huggingface\.co\//i.test(String(run.hf_url || '').trim())
    ? String(run.hf_url).trim() : null;
  if (state === 'done') {
    return {
      state, tone: 'success', href,
      label: 'Hugging Face backup made',
      detail: detail || 'The full-precision master was uploaded from the pod, so '
        + 'this run can be continued later.',
    };
  }
  if (state === 'failed' || state === 'skipped') {
    return {
      state, tone: 'warning', href,
      label: 'No Hugging Face backup',
      detail: detail || 'The backup copy was not made. The model itself is on '
        + 'this computer; without a Hub copy this run cannot be continued later.',
    };
  }
  if (String(run.local_artifact_status || '').toLowerCase() === 'available') {
    return { state, tone: 'info', href, label: 'Hugging Face backup pending',
      detail: detail || 'The model is on this computer; the backup copy has not '
        + 'been reported yet.' };
  }
  return null;      // nothing to say before the local copy even landed
}

/** Why a full model cannot be continued, or null when it can.
 * The Hub copy is the only source a pod can be given: a ~26 GB master cannot be
 * uploaded to it from here. */
export function denseResumeBlocker(run = {}) {
  if (!isFullTransformerRun(run)) return null;
  if ((run.resume_steps || []).length) return null;
  if (!denseDeliversToHub(run)) {
    return 'This full model has no Hugging Face copy, so it cannot be continued: '
      + 'a pod cannot be handed the 26 GB file on this computer. Choose the '
      + '“This computer + Hugging Face” delivery to keep future runs resumable.';
  }
  return 'This run has no verified Hugging Face copy to continue from yet.';
}

/** Fetching to this computer is the recovery twin of “Verify Hugging Face
 * delivery”: it applies to a KEPT pod whose local copy is still missing. */
export function canFetchDenseLocally(run = {}) {
  return isFullTransformerRun(run) && run.can_fetch_local === true;
}

/** Delivery verification is safe only for the recovery state whose pod was
 * deliberately kept alive. Rechecking a live/finished run could otherwise race
 * the monitor and tear down an instance that is still uploading. */
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

/** Turn the transactional backend result into billing-safe user feedback. */
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

/** Dense estimates must be explicitly backed by a dense benchmark. Older
 * servers can still return LoRA-derived numbers without an estimate status; for
 * a full run those numbers are deliberately treated as unavailable. */
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

/** Dense fine-tuning is deliberately a single, narrow cloud recipe for the MVP:
 * the official Krea 2 Raw base. A local/custom base is not equivalent, even when
 * its architecture happens to be Krea-compatible. */
export function isFullTransformerEligible({
  trainType, variant, baseModel = '', customBase = false,
} = {}) {
  return !customBase
    && trainType === 'krea'
    && variant === 'base'
    && String(baseModel || '').trim() === '';
}

export function fullTransformerUnavailableReason(selection = {}) {
  if (selection.trainType !== 'krea') return 'Choose the Krea 2 family.';
  if (selection.variant !== 'base') return 'Choose Krea 2 Raw.';
  if (selection.customBase === true) return 'This MVP supports only the official Krea 2 Raw base.';
  if (String(selection.baseModel || '').trim()) return 'This MVP supports only the official Krea 2 Raw base.';
  return null;
}
