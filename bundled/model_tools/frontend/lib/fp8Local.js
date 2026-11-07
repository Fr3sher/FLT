export function hasCloudDelivery(registry) {
  return Boolean(registry?.plugins?.some(plugin => plugin.id === 'cloud_training' && plugin.active));
}

export function localQuantizePlan(plan) {
  if (!plan?.ok) return plan;
  return {
    ...plan,
    source_kind: 'local',
    weight_basename: plan.source_name,
    destination_dir_kind: 'source',
    destination_dir_note: 'Saved next to the original model. The source stays unchanged.',
    download_bytes: 0,
  };
}

export function localQuantizeState(state) {
  return state?.status === 'running' ? { ...state, status: 'quantizing' } : state;
}
