export const TRAINING_MODE_LORA = 'lora';
export const TRAINING_MODE_FULL_TRANSFORMER = 'full_transformer';

export function normalizeTrainingMode(value) {
  return value === TRAINING_MODE_FULL_TRANSFORMER
    ? TRAINING_MODE_FULL_TRANSFORMER
    : TRAINING_MODE_LORA;
}

export function trainingModeLabel(value) {
  return normalizeTrainingMode(value) === TRAINING_MODE_FULL_TRANSFORMER
    ? 'Modèle complet'
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
      ? 'Le token dédié HF_CLOUD_TOKEN est absent.'
      : 'Le token dédié HF_CLOUD_TOKEN est invalide ou ses permissions sont insuffisantes.';
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
      label: 'Modèle complet disponible',
      detail: cleanupPending
        ? (cleanupDetail
          || 'Le modèle est vérifié, mais le nettoyage du pod n’est pas confirmé et il peut encore facturer.')
        : detail || (href
        ? 'Le contenu du dépôt Hugging Face privé a été vérifié.'
        : 'Le contenu a été vérifié, mais le lien du dépôt manque dans ce statut.'),
    };
  }
  if (status === 'missing') {
    return {
      status, available: false, href: null, repositoryHref, tone: 'error',
      label: 'Modèle complet introuvable',
      detail: detail || 'Aucun poids complet vérifié dans le dépôt. Vérifiez les logs du run et le dépôt Hugging Face avant de supprimer toute copie de récupération.',
    };
  }
  if (status === 'verification_pending') {
    return {
      status, available: false, href: null, repositoryHref, tone: 'warning',
      label: 'Vérification Hugging Face en attente',
      detail: detail || 'Vérifiez le token dédié HF_CLOUD_TOKEN dans Settings ▸ Local tools et la connexion, puis actualisez la page Runs. Le modèle ne doit pas encore être considéré comme récupérable.',
    };
  }
  if (status === 'creating_repository' || status === 'pending' || status === 'uploading') {
    return {
      status, available: false, href: null, repositoryHref, tone: 'info',
      label: status === 'creating_repository'
        ? 'Création du dépôt Hugging Face…'
        : 'Envoi du modèle complet en cours…',
      detail: detail || 'Gardez le run et son pod actifs jusqu’à la vérification du dépôt.',
    };
  }
  return {
    status, available: false, href: null, repositoryHref, tone: 'warning',
    label: 'Statut du modèle complet indisponible',
    detail: detail || 'Actualisez la page Runs. Si le statut reste absent, vérifiez les logs du run et votre configuration Hugging Face.',
  };
}

/** Delivery verification is safe only for the recovery state whose pod was
 * deliberately kept alive. Rechecking a live/finished run could otherwise race
 * the monitor and tear down an instance that is still uploading. */
export function canRecheckFullTransformerDelivery(run = {}) {
  const artifactStatus = String(run.artifact_status || '').trim().toLowerCase();
  const cleanupPending = artifactStatus === 'available'
    && String(run.artifact_cleanup_status || '').trim().toLowerCase() !== 'complete';
  return isFullTransformerRun(run)
    && run.status === 'error_pod_kept'
    && (artifactStatus !== 'available' || cleanupPending);
}

/** Turn the transactional backend result into billing-safe user feedback. */
export function fullTransformerRecheckOutcome(result = {}) {
  if (!result?.ok) {
    return {
      kind: 'error',
      text: result?.error
        || 'La livraison Hugging Face n’a pas pu être vérifiée. Le pod reste conservé.',
    };
  }
  if (result.delivery === 'available' && result.cleanup_pending) {
    return {
      kind: 'warning',
      text: 'Modèle Hugging Face vérifié et disponible. Le nettoyage du pod reste en attente et il peut encore facturer ; réessayez le nettoyage.',
    };
  }
  if (result.delivery === 'available') {
    return {
      kind: 'success',
      text: 'Livraison Hugging Face vérifiée. Le modèle est disponible et le nettoyage du pod est confirmé.',
    };
  }
  return {
    kind: 'info',
    text: result.delivery === 'missing'
      ? 'Aucun poids dense vérifié dans le dépôt. Le pod reste conservé : consultez ses logs avant toute suppression.'
      : 'Vérification Hugging Face toujours en attente. Corrigez HF_CLOUD_TOKEN si nécessaire, puis réessayez.',
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
  if (selection.trainType !== 'krea') return 'Choisissez la famille Krea 2.';
  if (selection.variant !== 'base') return 'Choisissez Krea 2 Raw.';
  if (selection.customBase === true) return 'Le MVP utilise uniquement la base officielle Krea 2 Raw.';
  if (String(selection.baseModel || '').trim()) return 'Le MVP utilise uniquement la base officielle Krea 2 Raw.';
  return null;
}
