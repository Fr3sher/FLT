import test from 'node:test';
import assert from 'node:assert/strict';
import { hasCloudDelivery, localQuantizePlan, localQuantizeState } from '../frontend/lib/fp8Local.js';

test('only an active Cloud training product offers delivery', () => {
  for (const registry of [null, {}, { plugins: [{ id: 'model_tools', active: true }] }, { plugins: [{ id: 'cloud_training', active: false }] }]) {
    assert.equal(hasCloudDelivery(registry), false);
  }
  assert.equal(hasCloudDelivery({ plugins: [{ id: 'cloud_training', active: true }] }), true);
});

test('the local plan retains server space amounts and does not claim a download or ComfyUI placement', () => {
  const plan = { ok: true, source_name: 'model.safetensors', destination_dir: 'C:/models',
    destination_name: 'model_fp8.safetensors', source_bytes: 20, estimated_bytes: 10, free_bytes: 90, required_bytes: 30 };
  const view = localQuantizePlan(plan);
  assert.equal(view.weight_basename, plan.source_name);
  assert.equal(view.destination_dir, plan.destination_dir);
  assert.equal(view.required_bytes, 30);
  assert.equal(view.free_bytes, 90);
  assert.equal(view.source_kind, 'local');
  assert.equal(view.destination_dir_kind, 'source');
  assert.equal(view.download_bytes, 0);
  const refusal = { ok: false, error: 'Already quantized' };
  assert.equal(localQuantizePlan(refusal), refusal);
});

test('local running jobs survive remount mapping while errors and completion retain their details', () => {
  const state = { status: 'running', done: 3, total: 7, destination_dir: 'C:/models' };
  assert.deepEqual(localQuantizeState(state), { ...state, status: 'quantizing' });
  for (const status of ['done', 'error']) {
    const finished = { status, result: { verified: true }, error: 'reason' };
    assert.equal(localQuantizeState(finished), finished);
  }
  assert.equal(localQuantizeState(null), null);
});
