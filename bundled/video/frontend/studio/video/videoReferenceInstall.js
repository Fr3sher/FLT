export const REFERENCE_BASE_ACTIONS = {
  official: 'h3_ref_base', light: 'h3_ref_base_light', eros: 'h3_ref_base_eros',
};
export const REFERENCE_ACCEL_ACTIONS = { ref4: 'h3_ref_turbo_4_lora', ref8: 'h3_ref_turbo_8_lora', vdn: 'h3_vdn_stage' };
// The shared VDN stage already owns its row in the general video install menu.
export const REFERENCE_ACTIONS = [...Object.values(REFERENCE_BASE_ACTIONS),
  ...Object.values(REFERENCE_ACCEL_ACTIONS).filter((action) => action !== 'h3_vdn_stage'), 'h3_reference_nodes'];

export function referenceInstallPlan(status, base = 'official', accel = 'ref4') {
  if (!status) return [];
  if (base === 'fused') accel = '';
  const wanted = new Set(['h3_text_encoder', 'h3_clip_projection', 'h3_clipproj_nodes', 'h3_video_vae', 'h3_audio_vae',
    REFERENCE_BASE_ACTIONS[base], REFERENCE_ACCEL_ACTIONS[accel]].filter(Boolean));
  const missing = (status.missing_weights || []).map((m) => m.action);
  const rows = missing.filter((action) => wanted.has(action));
  if ((status.missing_nodes || []).some((node) => node === 'ClipProjApply' || node?.action === 'h3_clipproj_nodes')) rows.push('h3_clipproj_nodes');
  for (const node of ['ref4', 'ref8'].includes(accel) ? status.missing_nodes || [] : []) {
    if (node?.action === 'h3_reference_nodes' || (typeof node === 'string' && node.startsWith('LDS'))) {
      rows.unshift('h3_reference_nodes'); break;
    }
  }
  return [...new Set(rows)];
}

export function referenceMissingActions(status) {
  return new Set(['official', 'light', 'eros'].flatMap((base) =>
    ['ref4', 'ref8', 'vdn'].flatMap((accel) => referenceInstallPlan(status, base, accel))));
}
