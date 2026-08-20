// Wiring: the auto-triage bar must route non-scorable verdicts through the
// fidelity gate, and the grid must receive the dataset's fidelity.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const grid = readFileSync(new URL('./DatasetGrid.jsx', import.meta.url), 'utf8');
const ws = readFileSync(new URL('./DatasetWorkspace.jsx', import.meta.url), 'utf8');

test('auto-triage uses the fidelity gate and includes non-scorable verdicts', () => {
  assert.match(grid, /import \{ isAutoTriagable, autoTriageDecision \} from '\.\.\/\.\.\/utils\/faceTriageGate\.js'/);
  assert.match(grid, /status === 'pending' && isAutoTriagable\(i\)/);
  assert.match(grid, /autoTriageDecision\(i, t, bodyFid\) === 'keep'/);
  assert.match(grid, /autoTriageDecision\(i, t, bodyFid\) === 'reject'/);
  assert.match(grid, /bodyFid = false/);
  assert.match(grid, /bodyFid=\{bodyFid\} /);
});

test('workspace hands the grid the body-fidelity flag', () => {
  assert.match(ws, /bodyFid=\{bodyFid\} dualCaptions/);
});
