import test from 'node:test';
import assert from 'node:assert/strict';
import { buildGeneratePayload } from '../frontend/studio/video/videoStudioApi.js';
import { performanceSettings, referenceBaseMissing } from '../frontend/studio/video/videoPerformance.js';
import { readReferenceDraft, writeReferenceDraft } from '../frontend/studio/video/videoReferences.js';
import { bestToControls } from '../frontend/studio/video/videoBestSettings.js';

const selected = { fused: true, h3_attention: 'sage', h3_spectrum: true,
  h3_video_vae: 'int8', h3_video_writer: 'fast' };

test('performance survives a reference draft and reaches the queued recipe', () => {
  let data;
  const storage = { setItem: (_, value) => { data = value; }, getItem: () => data };
  writeReferenceDraft({ settings: { ...selected, base: 'fused', accel: '' } }, storage);
  const restored = readReferenceDraft(storage);
  assert.equal(restored.settings.base, 'fused');
  assert.deepEqual(performanceSettings(restored.settings), selected);
  const payload = buildGeneratePayload({ ...restored.settings, mode: 'ref2va', refBase: 'fused' });
  assert.equal(payload.ref_base, 'fused');
  assert.equal(payload.accel, '');
  for (const key of Object.keys(selected).filter(k => k !== 'fused')) assert.equal(payload[key], selected[key]);
  assert.equal(payload.image, undefined);
});

test('best settings preserve performance while old clips use existing defaults', () => {
  const best = bestToControls({ settings: selected }, {}, {});
  assert.deepEqual(performanceSettings(best.opts), selected);
  assert.equal(performanceSettings(null).h3_attention, 'auto');
});

test('INT8 decoding replaces the FP16 requirement without hiding missing nodes or other weights', () => {
  const base = { available: true, ready: false, nodes_ready: true, missing_weights: [{ action: 'h3_video_vae' }] };
  assert.equal(referenceBaseMissing(base, selected, { int8: { available: true } }), false);
  assert.equal(referenceBaseMissing(base, selected, { int8: { available: false } }), true);
  assert.equal(referenceBaseMissing({ ...base, nodes_ready: false }, selected, { int8: { available: true } }), true);
  assert.equal(referenceBaseMissing({ ...base, missing_weights: [{ action: 'h3_text_encoder' }] }, selected, { int8: { available: true } }), true);
});
