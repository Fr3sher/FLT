import test from 'node:test';
import assert from 'node:assert/strict';
import { isAutoTriagable, autoTriageDecision } from './faceTriageGate.js';

const img = (face_state, face_score = null) => ({
  filename: 'x.jpg', status: 'pending', face_state, face_score,
});

test('scorable faces follow the threshold in both fidelities', () => {
  assert.equal(autoTriageDecision(img('scorable', 0.8), 0.5, false), 'keep');
  assert.equal(autoTriageDecision(img('scorable', 0.3), 0.5, false), 'reject');
  assert.equal(autoTriageDecision(img('scorable', 0.8), 0.5, true), 'keep');
});

test('no_face is rejected at any fidelity', () => {
  assert.equal(autoTriageDecision(img('no_face'), 0.5, false), 'reject');
  assert.equal(autoTriageDecision(img('no_face'), 0.5, true), 'reject');
});

test('too_small / low_det are rejected for face fidelity but kept for body', () => {
  for (const st of ['too_small', 'low_det']) {
    assert.equal(autoTriageDecision(img(st), 0.5, false), 'reject', `${st} face`);
    assert.equal(autoTriageDecision(img(st), 0.5, true), 'keep', `${st} body`);
  }
});

test('extreme_pose (profile) is kept for body, rejected for face', () => {
  assert.equal(autoTriageDecision(img('extreme_pose'), 0.5, false), 'reject');
  assert.equal(autoTriageDecision(img('extreme_pose'), 0.5, true), 'keep');
});

test('unknown / unscored states are left alone (null)', () => {
  assert.equal(autoTriageDecision(img('unreadable'), 0.5, false), null);
  assert.equal(autoTriageDecision(img(null), 0.5, false), null);
  assert.equal(autoTriageDecision(img('scorable', null), 0.5, false), null);
});

test('isAutoTriagable gates on a scored, decidable verdict', () => {
  assert.equal(isAutoTriagable(img('scorable', 0.5)), true);
  assert.equal(isAutoTriagable(img('too_small')), true);
  assert.equal(isAutoTriagable(img('no_face')), true);
  assert.equal(isAutoTriagable(img(null)), false);
  assert.equal(isAutoTriagable(img('scorable', null)), false);
  assert.equal(isAutoTriagable({ ...img('too_small'), filename: null }), false);
});
