/** Merge only verified tool presence; readiness of unprobed features stays put. */
export function mergeStartupCapabilities(previous, startup, fullSnapshotReceived) {
  if (fullSnapshotReceived) return previous
  return {
    ...previous,
    configured: startup.configured,
    comfyui: { ...previous.comfyui, ...startup.comfyui },
    aitoolkit: { ...previous.aitoolkit, ...startup.aitoolkit },
    training_visible: startup.training_visible,
    studio_visible: startup.studio_visible,
  }
}
