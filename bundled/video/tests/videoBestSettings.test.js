import test from 'node:test';
import assert from 'node:assert/strict';
import { bestForLoraUrl, bestToControls, bestUnavailable, saveVideoBestUrl, videoBestUrl } from '../frontend/studio/video/videoBestSettings.js';
import { buildGeneratePayload } from '../frontend/studio/video/videoStudioApi.js';

const options = { base_official: 'official', base_eros: 'eros', base_light: 'light',
  eros_available: true, light: { available: true }, accelerations: [{ id: 'parasyte', available: true }] };
const best = { clip_id: 4, dataset_id: 12, run_id: 9, lora_filename: 'motion.safetensors',
  settings: { mode: 'i2v', aspect: 'portrait', lora: 'h3/lds/motion.safetensors',
    lora_strength: 1.5, base_model: 'light', frames: 56, seed: 15,
    megapixels: 0.4, steps: 6, accel: 'parasyte', sparse: 'max', latent_upscale: true } };

test('applying best settings restores effective generation dials into a fresh scene', () => {
  const current = { shots: 3, frames: 362, accel: 'turbo', eros: true, steps: '', seed: '' };
  const next = bestToControls(best, options, current);
  const scene = { prompt: 'The camera pans left', image: 'new-scene.png', endImage: 'new-end.png', continues: 41 };
  const payload = buildGeneratePayload({ ...scene, ...next.opts, mode: next.mode, aspect: next.aspect,
    lora: next.lora.lora, runId: next.lora.runId, datasetId: next.lora.datasetId, loraStrength: next.strength });
  assert.equal(payload.prompt, scene.prompt);
  assert.equal(payload.end_image, scene.endImage);
  assert.equal(payload.continues, scene.continues);
  assert.equal(next.aspect, 'portrait');
  assert.equal(payload.aspect, undefined); // An image continuation inherits its frame geometry.
  assert.equal(payload.frames, 56);
  assert.equal(payload.accel, 'parasyte');
  assert.equal(payload.steps, 6);
  assert.equal(payload.light, true);
  assert.equal(payload.eros, undefined);
  assert.equal(payload.lora_strength, 1.5);
  assert.equal(payload.dataset_id, 12);
  assert.equal(next.opts.shots, 3);
  assert.equal(current.frames, 362);
  for (const key of ['prompt', 'sources', 'image', 'endImage', 'continues']) assert.equal(key in next, false);
});

test('lookups use the LoRA video dataset, never the Studio page image id', () => {
  const url = bestForLoraUrl({ lora: best.settings.lora, runId: 9, datasetId: 12, pageDatasetId: 25 });
  assert.equal(new URL(url, 'http://test').searchParams.get('dataset_id'), '12');
  assert.ok(!url.includes('25'));
  assert.equal(videoBestUrl(12), '/api/video-dataset/12/best-settings');
  assert.equal(saveVideoBestUrl(4), '/api/video-studio/clip/4/best');
});

test('unavailable saved options explain the refusal instead of silently substituting a base', () => {
  assert.ok(bestUnavailable(best, null));
  assert.equal(bestUnavailable(best, options), '');
  assert.match(bestUnavailable(best, { ...options, light: { available: false } }), /W4A8/);
  assert.match(bestUnavailable(best, { ...options, accelerations: [{ id: 'parasyte', available: false }] }), /acceleration/);
  assert.match(bestUnavailable(best, { ...options, options_available: { sparse: { available: false } } }), /sparse/);
});

test('a best recipe cannot replace reference conditioning with FL2V controls', () => {
  assert.match(bestUnavailable(best, options, 'ref2va'), /References.*Reuse/);
  assert.match(bestUnavailable({ ...best, settings: { ...best.settings, mode: 'ref2va' } }, options), /References.*Reuse/);
  assert.equal(bestUnavailable(best, options, 'i2v'), '');
});
