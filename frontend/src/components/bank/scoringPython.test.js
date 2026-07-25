import test from 'node:test';
import assert from 'node:assert/strict';
import {
  bestUpgrade,
  canSelect,
  detectionSummary,
  missingLabels,
  selectionNote,
  sortInterpreters,
  statusBadge,
} from './scoringPython.js';

const DEPS = ['PyTorch', 'OpenCLIP', 'Transformers', 'timm', 'NumPy', 'Pillow'];

function row(over = {}) {
  const missing = over.missingLabels || [];
  return {
    path: 'python',
    label: 'Some Python',
    status: 'gpu_ready',
    cuda: true,
    usable: missing.length === 0,
    selected: false,
    detail: '',
    deps: DEPS.map((label) => ({ label, present: !missing.includes(label) })),
    ...over,
  };
}

test('a CUDA interpreter missing OpenCLIP is not usable, and says which package', () => {
  const r = row({ status: 'incomplete', cuda: true, missingLabels: ['OpenCLIP'] });
  assert.deepEqual(missingLabels(r), ['OpenCLIP']);
  assert.equal(canSelect(r), false, 'CUDA alone must never be enough to pick it');
  assert.equal(statusBadge(r.status).label, 'Missing packages');
  // The summary names the interpreter AND the package — the whole point of the
  // feature is saying "ai-toolkit has CUDA but lacks OpenCLIP", not "no".
  const summary = detectionSummary([r]);
  assert.match(summary, /OpenCLIP/);
  assert.match(summary, /Some Python/);
});

test('the best suggestion is a GPU-ready interpreter that is not already in use', () => {
  const rows = [
    row({ label: 'App Python', status: 'unreachable', cuda: false, usable: false }),
    row({ label: 'Scoring env', status: 'cpu_only', cuda: false, selected: true }),
    row({ label: 'ai-toolkit', status: 'gpu_ready' }),
  ];
  assert.equal(bestUpgrade(rows).label, 'ai-toolkit');
  assert.equal(sortInterpreters(rows)[0].label, 'ai-toolkit');
  assert.equal(sortInterpreters(rows).at(-1).label, 'App Python');
  assert.equal(detectionSummary(rows), '1 of 3 can run ✨ Score on your GPU.');
});

test('the one already selected is never offered again', () => {
  const rows = [row({ label: 'ai-toolkit', selected: true })];
  assert.equal(bestUpgrade(rows), null);
  assert.equal(canSelect(rows[0]), false);
});

test('no GPU anywhere is stated plainly instead of inviting a hunt', () => {
  const rows = [row({ label: 'Scoring env', status: 'cpu_only', cuda: false })];
  assert.match(detectionSummary(rows), /stays on the CPU/);
  assert.equal(bestUpgrade(rows), null);
  assert.equal(canSelect(rows[0]), true, 'a complete CPU interpreter is still a valid choice');
});

test('an interpreter that did not answer is inert, never a crash', () => {
  const r = row({ status: 'unreachable', cuda: false, usable: false, deps: [] });
  assert.equal(canSelect(r), false);
  assert.equal(statusBadge(r.status).label, 'No answer');
  assert.deepEqual(missingLabels(r), []);
  assert.deepEqual(missingLabels(null), []);
  assert.equal(detectionSummary([]), 'No Python interpreters found to check yet.');
  assert.equal(detectionSummary(null), 'No Python interpreters found to check yet.');
});

test('the panel names the interpreter in use, and stays quiet on the default', () => {
  const chosen = row({ label: 'ai-toolkit', selected: true, detail: 'ready — scores on a 4090' });
  assert.match(selectionNote({ interpreters: [chosen] }), /ai-toolkit/);
  assert.match(selectionNote({ interpreters: [chosen] }), /4090/);
  assert.equal(selectionNote({ interpreters: [row()] }), null);
  assert.equal(selectionNote(null), null);
});
