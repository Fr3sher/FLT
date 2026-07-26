import test from 'node:test';
import assert from 'node:assert/strict';
import { faceAnalysisState, autoTriageAvailable } from './faceScoringGate.js';

const BLOCKED = 'Face similarity needs a photographic face; it cannot read a drawn one. '
  + 'Set the subject type to Human if this dataset is photographic.';

test('a blocked dataset disables the pass AND carries the reason', () => {
  const s = faceAnalysisState({ blockedReason: BLOCKED, hasRef: true, busy: false });
  assert.equal(s.disabled, true);
  // "Disappears in silence" is the bug, not the fix: the reason IS the title.
  assert.equal(s.title, BLOCKED);
  assert.equal(s.blocked, true);
});

test('the reason wins over "set a reference photo first"', () => {
  // A drawn dataset with no reference must not be sent off to add one: it would
  // not have helped.
  const s = faceAnalysisState({ blockedReason: BLOCKED, hasRef: false, busy: false });
  assert.equal(s.title, BLOCKED);
});

test('a photographic dataset is strictly unchanged', () => {
  const s = faceAnalysisState({ blockedReason: null, hasRef: true, busy: false });
  assert.equal(s.disabled, false);
  assert.equal(s.blocked, false);
  assert.match(s.title, /facial resemblance/i);

  const noRef = faceAnalysisState({ blockedReason: null, hasRef: false, busy: false });
  assert.equal(noRef.disabled, true);
  assert.equal(noRef.title, 'Set a reference photo first');

  const busy = faceAnalysisState({ blockedReason: null, hasRef: true, busy: true });
  assert.equal(busy.disabled, true);
  assert.match(busy.title, /facial resemblance/i);
});

test('the gate is the SERVER string — the UI never re-derives the rule', () => {
  // Any non-empty reason blocks, whatever it says: when the server grows a second
  // reason, the UI already honours it. Nothing here mentions "anime".
  const s = faceAnalysisState({ blockedReason: 'some future reason', hasRef: true });
  assert.equal(s.disabled, true);
  assert.equal(s.title, 'some future reason');
  assert.doesNotMatch(faceAnalysisState.toString(), /anime/i);
});

test('auto-triage is withheld when scoring is blocked', () => {
  // Auto-triage BATCHES keep/reject from face_score. Letting it act on scores from
  // a pass that cannot read this dataset is the one place stale numbers do damage.
  assert.equal(autoTriageAvailable(BLOCKED), false);
  assert.equal(autoTriageAvailable(null), true);
  assert.equal(autoTriageAvailable(undefined), true);
  assert.equal(autoTriageAvailable(''), true);
});
