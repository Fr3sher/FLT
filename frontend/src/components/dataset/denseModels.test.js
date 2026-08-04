import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  denseActions, denseFileRows, denseGuidanceLine, denseModelTitle,
  denseStudioTarget, denseWhereChip, fmtBytes, STUDIO_NEEDS_A_LORA,
} from './denseModels.js';

const local = (over = {}) => ({
  run_id: 146, dataset_id: 3, train_type: 'krea', variant: 'Raw', steps: 3000,
  active: false, can_quantize: false, can_send_to_comfyui: true, can_delete: true,
  master: {
    filename: 'Krea_full_x.safetensors', path: '/store/run_146/Krea_full_x.safetensors',
    size_bytes: 26e9, step: null, is_final: true, total_candidates: 1, others: [],
  },
  fp8: {
    filename: 'Krea_full_x_fp8.safetensors', size_bytes: 13e9,
    in_comfyui: false, comfyui_name: null,
  },
  hub: { repo_id: 'acme/dense-146', url: 'https://huggingface.co/acme/dense-146',
    status: 'available' },
  inference_hint: { guidance_scale: 4, steps: 25 },
  ...over,
});

const hubOnly = (over = {}) => ({
  run_id: 90, dataset_id: 3, train_type: 'krea', variant: 'Raw', active: false,
  master: null, fp8: null, can_quantize: false,
  hub: { repo_id: 'acme/dense-90', url: 'https://huggingface.co/acme/dense-90',
    status: 'available', weight_filename: 'Krea_full_y.safetensors' },
  inference_hint: { guidance_scale: 4, steps: 25 },
  ...over,
});

// --- identity ---------------------------------------------------------------

test('the title names the family AND the variant — Raw and Turbo want different settings', () => {
  assert.equal(denseModelTitle(local()), 'Krea 2 · Raw — run #146');
  assert.equal(denseModelTitle({ train_type: 'krea' }), 'Krea 2');
  assert.equal(denseModelTitle(null), 'Full model');
});

test('the where-chip mirrors the canvas vocabulary, never "missing" for a Hub model', () => {
  assert.equal(denseWhereChip(local()).label, 'On this computer');
  assert.equal(denseWhereChip(hubOnly()).label, 'On Hugging Face');
  assert.equal(denseWhereChip({}).label, 'Not found');
  // A run holding only the twin is still "on this computer".
  assert.equal(denseWhereChip({ fp8: { filename: 'a' } }).label, 'On this computer');
});

// --- the distinction this panel exists to make -------------------------------

test('the fp8 twin comes FIRST and is named as what ComfyUI loads', () => {
  const rows = denseFileRows(local());
  assert.deepEqual(rows.map((r) => r.kind), ['fp8', 'master']);
  assert.match(rows[0].role, /ComfyUI loads/);
});

test('the master says it is for re-training and that it is never sent to ComfyUI', () => {
  const master = denseFileRows(local()).find((r) => r.kind === 'master');
  assert.match(master.role, /train again or resume from/);
  assert.match(master.role, /never sent\s+to ComfyUI/);
  assert.equal(master.stateLabel, 'Keep to re-train');
});

test('a run that saved several 26 GB files says which one it takes, and over what', () => {
  const rows = denseFileRows(local({
    master: { filename: 'Krea_x_000002750.safetensors', size_bytes: 26e9,
      step: 2750, is_final: false, total_candidates: 3, others: ['a', 'b'] },
  }));
  assert.match(rows.find((r) => r.kind === 'master').choice,
    /the step 2750 checkpoint, chosen over 2 other checkpoints/);
});

test('one file only means one row, and no rows at all for a Hub-only run', () => {
  assert.equal(denseFileRows(local({ master: null })).length, 1);
  assert.equal(denseFileRows(hubOnly()).length, 0);
});

test('the fp8 row states whether ComfyUI can already see it', () => {
  const off = denseFileRows(local())[0];
  const on = denseFileRows(local({
    fp8: { filename: 'f', size_bytes: 1, in_comfyui: true, comfyui_name: 'krea\\f' },
  }))[0];
  assert.equal(off.stateLabel, 'Not in ComfyUI yet');
  assert.equal(on.stateLabel, '✓ In ComfyUI');
});

// --- what the buttons may do -------------------------------------------------

test('sending is offered only for a twin ComfyUI cannot see yet', () => {
  assert.ok(denseActions(local()).send);
  assert.equal(denseActions(local({
    fp8: { filename: 'f', in_comfyui: true, comfyui_name: 'k\\f' },
  })).send, null);
  assert.equal(denseActions(local({ fp8: null })).send, null);
});

test('an active run offers nothing and says why', () => {
  const a = denseActions(local({ active: true, can_quantize: true }));
  assert.equal(a.send, null);
  assert.equal(a.quantize, null);
  assert.match(a.activeNote, /still working/);
});

test('a Hub-only master can still be quantized — the job downloads it first', () => {
  assert.ok(denseActions(hubOnly()).quantize);
});

test('a run with a twin already is not offered a second quantization', () => {
  assert.equal(denseActions(local()).quantize, null);
});

// --- the Raw sampler settings ------------------------------------------------

test('the guidance line carries the undistilled settings, and degrades quietly', () => {
  assert.equal(denseGuidanceLine({ guidance_scale: 4, steps: 25 }), 'CFG 4 · 25 steps');
  assert.equal(denseGuidanceLine({ guidance_scale: 4 }), 'CFG 4');
  assert.equal(denseGuidanceLine(null), '');
  assert.equal(denseGuidanceLine({}), '');
});

// --- the honest limit --------------------------------------------------------

test('a Studio target exists only once ComfyUI can really load the file', () => {
  assert.equal(denseStudioTarget(local()), null);          // twin not in ComfyUI
  const t = denseStudioTarget(local({
    fp8: { filename: 'f', in_comfyui: true, comfyui_name: 'krea\\f_fp8.safetensors' },
  }));
  assert.deepEqual(t, { base: 'krea\\f_fp8.safetensors', family: 'krea', datasetId: 3 });
});

test('the Studio limit is stated with its workaround, not just as a refusal', () => {
  assert.match(STUDIO_NEEDS_A_LORA, /strength to 0/);
  assert.match(STUDIO_NEEDS_A_LORA, /bare model/);
});

// --- sizes -------------------------------------------------------------------

test('sizes read in the unit that matches the file, and never render "0 GB"', () => {
  assert.equal(fmtBytes(26e9), '26.0 GB');
  assert.equal(fmtBytes(13.4e9), '13.4 GB');
  assert.equal(fmtBytes(0), '');
  assert.equal(fmtBytes(null), '');
  assert.equal(fmtBytes('nope'), '');
  // A file below a kilobyte exists; "0 kB" would say it does not — and a
  // truncated weight file is exactly when a size is worth reading.
  assert.equal(fmtBytes(137), '137 B');
  assert.equal(fmtBytes(2400), '2 kB');
});

// --- the panel's own source: two invariants worth pinning --------------------

const panel = readFileSync(
  fileURLToPath(new URL('./DenseModelsPanel.jsx', import.meta.url)), 'utf8');

test('no control in the panel can send the MASTER to ComfyUI', () => {
  // Every place that triggers a send sits behind `row.kind === 'fp8'`. A future
  // edit that moves one out of that guard fails here rather than in production,
  // with 26 GB landing in a model folder.
  const calls = [...panel.matchAll(/askSend\(entry\.run_id\)/g)].map((m) => m.index);
  assert.ok(calls.length >= 1, 'the panel must offer a send at all');
  for (const at of calls) {
    const before = panel.slice(0, at);
    assert.ok(before.lastIndexOf("row.kind === 'fp8'") > before.lastIndexOf('<FileRow'),
      'the send button must sit inside the fp8 branch of a file row');
  }
  // And the master's own row carries no send affordance of any kind.
  assert.ok(!/master[\s\S]{0,400}Send to ComfyUI/.test(panel));
});

test('the card survives 400 px: long names wrap, rows wrap, nothing scrolls sideways', () => {
  assert.ok(panel.includes('break-all'), 'weight filenames must be allowed to wrap');
  assert.ok((panel.match(/flex-wrap/g) || []).length >= 4,
    'the header, the action rows and the plan buttons all wrap');
  assert.ok(!panel.includes('overflow-x-scroll'));
  assert.ok(!panel.includes('whitespace-nowrap'));
});
