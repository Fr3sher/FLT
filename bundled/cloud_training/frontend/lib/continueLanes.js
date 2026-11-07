// Cloud Training owns these recipe and lifecycle policies.
// Extracted from LDS under PolyForm-Noncommercial-1.0.0; no private host imports.
export function runsHubContinueLanes(run, opts = {}) {
  if (!run) return null;
  const {
    aitoolkitValid,          // caps.aitoolkit?.valid — undefined while caps load
    localActive = null,      // the hub payload's `local_active` (any dataset)
    actives = [],
    configured = false,      // a vast.ai API key is set
    limit = 1,               // max concurrent cloud runs
  } = opts;

  const localReason =
    aitoolkitValid === false
      ? 'Local training needs ai-toolkit — set it up in Settings, or continue in the cloud.'
    // A legacy row with no dataset can't address a local run dir — say so
    // instead of firing a request that would 404.
    : run.dataset_id == null
      ? 'This run’s dataset is unknown, so it can only be continued in the cloud.'
    : localActive
      ? 'A training is already running on this machine — continue in the cloud, or wait for it to finish.'
    : null;

  const cloudReason =
    !configured
      ? 'Cloud training needs a vast.ai API key — add it in Settings.'
    : actives.length >= limit
      ? `Cloud run limit reached (${actives.length}/${limit}) — stop one or raise the limit in Settings`
    : null;

  return {
    local: localReason ? { available: false, reason: localReason } : { available: true },
    cloud: cloudReason ? { available: false, reason: cloudReason } : { available: true },
  };
}
