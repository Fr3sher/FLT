/* 📷 The camera-angles LANE: the prompt grammar, the selection model, the
   refusals, the cost arithmetic and the wording — the plugin's half of what
   frontend/src/utils/cameraAngles.test.js used to pin in one file. */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  AZIMUTHS, CAMERA_ANGLE, DISTANCES, ELEVATIONS, LONG_RUN_SECONDS, MAX_VIEWS,
  POSE_COUNT, SECONDS_PER_VIEW, TRIGGER, cameraLaunchMessage,
  cameraRefusal, costSentence, datasetCameraLaunchMessage, datasetCameraRefusal,
  isLongRun, posePrompt, posesFor, runSeconds, selectionRefusal,
} from '../frontend/lib/cameraLane.js';

test('the grammar is the LoRA\'s, character for character', () => {
  assert.equal(TRIGGER, '<sks>');
  assert.equal(posePrompt('front', 'eye', 'medium'),
    '<sks> front view eye-level shot medium shot');
  assert.equal(posePrompt('back_left', 'low', 'wide'),
    '<sks> back-left quarter view low-angle shot wide shot');
  assert.equal(posePrompt('right', 'high', 'close'),
    '<sks> right side view high-angle shot close-up');
});

test('every pose builds, and every pose id is unique', () => {
  const all = posesFor({
    azimuths: AZIMUTHS.map((a) => a.id),
    elevations: ELEVATIONS.map((e) => e.id),
    distances: DISTANCES.map((d) => d.id),
  });
  assert.equal(all.length, 96);
  assert.equal(new Set(all).size, 96, 'every pose id is unique');
});

test('an unknown component never yields a half-built prompt', () => {
  // Silently dropping a token would render some OTHER angle and store it under
  // the name of the one that was asked for.
  assert.equal(posePrompt('nope', 'eye', 'medium'), null);
  assert.equal(posePrompt('front', 'nope', 'medium'), null);
  assert.equal(posePrompt('front', 'eye', 'nope'), null);
});

test('poses walk a full ring at one height before changing height', () => {
  // An interrupted run must leave a COMPLETE ring — that is the thing that is
  // useful as training data; a scattered handful is not.
  const poses = posesFor({
    azimuths: ['front', 'right', 'back', 'left'],
    elevations: ['eye', 'high'],
    distances: ['medium'],
  });
  assert.deepEqual(poses, [
    'front/eye/medium', 'right/eye/medium', 'back/eye/medium', 'left/eye/medium',
    'front/high/medium', 'right/high/medium', 'back/high/medium', 'left/high/medium',
  ]);
});

test('an empty selection is the ONLY thing refused', () => {
  assert.match(selectionRefusal({ azimuths: [], elevations: ['eye'], distances: ['medium'] }),
    /pick at least one/);
  assert.match(selectionRefusal({ azimuths: ['front'], elevations: [], distances: ['medium'] }),
    /pick at least one/);
  assert.equal(selectionRefusal({
    azimuths: ['front', 'right'], elevations: ['eye'], distances: ['medium'],
  }), null);
  // The regression this pins: eight sides at two distances is 16 views — an
  // ordinary request that an arbitrary 12-view cap used to refuse.
  assert.equal(selectionRefusal({
    azimuths: AZIMUTHS.map((a) => a.id), elevations: ['eye'], distances: ['close', 'medium'],
  }), null);
  // And nothing refuses the whole vocabulary either. Length is a cost, not an error.
  assert.equal(selectionRefusal({
    azimuths: AZIMUTHS.map((a) => a.id),
    elevations: ELEVATIONS.map((e) => e.id),
    distances: DISTANCES.map((d) => d.id),
  }), null);
  assert.equal(MAX_VIEWS, POSE_COUNT, 'the only ceiling is the vocabulary itself');
});

test('a long run warns instead of being blocked, on the SAME arithmetic', () => {
  // A warning that fires at a different number from the one on screen is worse
  // than no warning — both read runSeconds.
  assert.equal(isLongRun(1, { modelResident: true }), false);
  assert.equal(isLongRun(96, { modelResident: true }), true);
  const n = Math.ceil(LONG_RUN_SECONDS / SECONDS_PER_VIEW);
  assert.equal(isLongRun(n, { modelResident: true }), true);
  assert.equal(isLongRun(n - 1, { modelResident: true }), false);
  assert.equal(runSeconds(0), 0);
  assert.equal(costSentence(0), '');
});

test('a camera view cannot be re-shot — but an improve result CAN', () => {
  assert.equal(cameraRefusal({ id: 7, status: 'done' }), null);
  assert.match(cameraRefusal({ id: 7, derivation_kind: CAMERA_ANGLE }),
    /cannot itself be re-shot/);
  // ✨ Allowed on purpose: an upscale is the same scene from the same viewpoint,
  // only cleaner — the best source this lane can get. Refusing it greyed the verb
  // out on the newest six tiles of a real library, which were all improves.
  assert.equal(cameraRefusal({ id: 7, derivation_kind: 'canvas_image_improve' }), null);
  assert.match(cameraRefusal({ id: 7, status: 'pending' }), /still rendering/);
  // A picture the board holds only as a URL — no row, no id to send.
  assert.match(cameraRefusal({ id: 'ref' }), /no library entry/);
  assert.match(cameraRefusal(null), /no library entry/);
});

test('the cost is stated before it is spent, and the toast says where', () => {
  assert.equal(costSentence(0), '');
  assert.match(costSentence(1, { modelResident: true }), /^1 view, about a minute$/);
  assert.match(costSentence(8, { modelResident: true }), /^8 views, about 2 minutes$/);
  // The first view of a session also pays for loading a 20 GB model.
  assert.match(costSentence(8, { modelResident: false }), /about 3 minutes/);
  assert.match(cameraLaunchMessage(1), /^1 camera view queued/);
  assert.match(cameraLaunchMessage(4), /^4 camera views queued/);
  assert.match(cameraLaunchMessage(4), /arrive here/);
});

test('the dataset refusal speaks the dataset\'s own statuses', () => {
  // keep, pending-with-file and IMPORT are all valid sources; an improve
  // result too. Only a camera view is refused, plus a row with no file yet.
  assert.equal(datasetCameraRefusal({ id: 3, status: 'keep', filename: 'a.png' }), null);
  assert.equal(datasetCameraRefusal({ id: 3, status: 'reject', filename: 'a.png' }), null);
  assert.equal(datasetCameraRefusal(
    { id: 3, source: 'import', status: 'keep', filename: 'a.png' }), null);
  assert.equal(datasetCameraRefusal(
    { id: 3, derivation_kind: 'klein_image_improve', filename: 'a.png' }), null);
  assert.match(datasetCameraRefusal(
    { id: 3, derivation_kind: 'camera_angle', filename: 'a.png' }),
  /cannot itself be re-shot/);
  assert.match(datasetCameraRefusal({ id: 3, status: 'pending' }), /no file yet/);
  assert.match(datasetCameraRefusal(null), /no dataset entry/);
});

test('the dataset toast names the keep/reject cycle, not just "queued"', () => {
  assert.match(datasetCameraLaunchMessage(1), /^1 camera view queued/);
  assert.match(datasetCameraLaunchMessage(6), /pending candidates/);
  assert.match(datasetCameraLaunchMessage(6), /angle already in the caption/);
});
