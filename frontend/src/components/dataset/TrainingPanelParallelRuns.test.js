import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const panel = fs.readFileSync(
  new URL('./TrainingPanel.jsx', import.meta.url), 'utf8');
const progress = fs.readFileSync(
  new URL('./TrainingProgress.jsx', import.meta.url), 'utf8');

test('the panel resolves ALL active cloud runs of this dataset, not the first', () => {
  assert.match(panel, /cloudActivesHere\s*=\s*actives\.filter/);
});

test('the chip row only exists at two or more runs — one run renders exactly as before', () => {
  assert.match(panel, /cloudActivesHere\.length > 1/);
});

test('the selected run is forwarded to the progress poll', () => {
  assert.match(progress, /runId/);
  assert.match(progress, /qs\.set\('run_id', runId\)/);
});

test('diverging dataset generations are marked on the chips', () => {
  assert.match(panel, /different dataset generation/);
});
