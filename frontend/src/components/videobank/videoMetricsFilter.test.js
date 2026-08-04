import test from 'node:test';
import assert from 'node:assert/strict';
import {
  FLAG_LABELS, cutSummary, draftThresholds, editThreshold, filterByFlag,
  flagCounts, payloadFromDraft, thresholdFields,
} from './videoMetricsFilter.js';

const CLIPS = [
  { id: 1, flags: ['still'], metrics: { motion_mean: 0.0001 } },
  { id: 2, flags: [], metrics: { motion_mean: 0.004 } },
  { id: 3, flags: ['black', 'still'], metrics: { motion_mean: 0.0002 } },
  { id: 4, flags: [], metrics: null },          // not measured yet
];

// --- counting ----------------------------------------------------------------

test('each flag counts the clips that carry it', () => {
  const counts = flagCounts(CLIPS);
  assert.equal(counts.still, 2);
  assert.equal(counts.black, 1);
});

test('unmeasured clips are counted as such, never as clean', () => {
  // "No flags because nothing was measured" and "no flags because the clip is
  // fine" are different facts; showing them as one would make a half-scanned
  // bank look healthy.
  assert.equal(flagCounts(CLIPS).unmeasured, 1);
});

test('a clip with two flags is one clip in the total, not two', () => {
  assert.equal(flagCounts(CLIPS).flagged, 2);
});

// --- filtering ---------------------------------------------------------------

test('filtering by a flag keeps exactly the carriers', () => {
  assert.deepEqual(filterByFlag(CLIPS, 'still').map(c => c.id), [1, 3]);
});

test('the unmeasured pseudo-flag selects clips with no metrics', () => {
  assert.deepEqual(filterByFlag(CLIPS, 'unmeasured').map(c => c.id), [4]);
});

test('no filter returns everything', () => {
  assert.equal(filterByFlag(CLIPS, null).length, 4);
});

// --- the threshold panel -----------------------------------------------------

test('every threshold field is described for the panel', () => {
  // The panel renders from this table; a cut the backend supports but the table
  // omits would be configurable only by editing config.json, invisibly.
  const keys = thresholdFields().map(f => f.key);
  assert.deepEqual(keys, ['motion_floor', 'motion_ceiling', 'luma_floor',
                          'freeze_max', 'sharpness_floor']);
});

test('each field says which flag it feeds and which way the cut points', () => {
  for (const f of thresholdFields()) {
    assert.ok(FLAG_LABELS[f.flag], `${f.key} names an unknown flag`);
    assert.ok(['below', 'above'].includes(f.direction));
  }
});

// --- the dry-run sentence ----------------------------------------------------

test('the dry-run summary is a sentence with real numbers', () => {
  const text = cutSummary({ still: 31, black: 4, total_flagged: 33 }, 470);
  assert.match(text, /33/);
  assert.match(text, /470/);
  assert.match(text, /still: 31/);
});

test('an empty dry run says nothing would be removed', () => {
  assert.match(cutSummary({ total_flagged: 0 }, 470), /nothing|no clips/i);
});

test('a dry run that would flag most of the bank warns instead of celebrating', () => {
  // The Hugging Face failure mode: a mis-set threshold kept 47 of 1493 and
  // nobody noticed until after. Above half the bank, the sentence changes tone.
  const text = cutSummary({ still: 400, total_flagged: 400 }, 470);
  assert.match(text, /⚠|most of/i);
});

// --- the panel's draft state -------------------------------------------------
// The panel edits a DRAFT and the dry run previews the draft; nothing reaches
// config until Apply. Editing live thresholds would re-flag the grid on every
// keystroke — including through the states the user is merely passing through.

test('a draft starts from the saved cuts and tracks edits', () => {
  const d = draftThresholds({ motion_floor: 0.001, luma_floor: null });
  assert.equal(d.motion_floor, 0.001);
  const edited = editThreshold(d, 'luma_floor', '0.05');
  assert.equal(edited.luma_floor, 0.05);
  assert.equal(d.luma_floor, null);          // the original is not mutated
});

test('clearing a field disables that cut rather than making it zero', () => {
  // Zero is a real threshold (flag everything below 0 = nothing, above = all);
  // an empty input means "no cut", and those must not be confused.
  const d = editThreshold(draftThresholds({}), 'motion_floor', '');
  assert.equal(d.motion_floor, null);
});

test('garbage input leaves the previous draft value in place', () => {
  const d = editThreshold(draftThresholds({ motion_floor: 0.002 }), 'motion_floor', 'abc');
  assert.equal(d.motion_floor, 0.002);
});

test('only the fields the backend knows ever leave the draft', () => {
  const d = editThreshold(draftThresholds({}), 'motion_floor', '0.001');
  d.garbage = 42;
  assert.deepEqual(Object.keys(payloadFromDraft(d)),
                   ['motion_floor']);
});

test('a draft with no active cut yields an empty payload and no dry run', () => {
  assert.deepEqual(payloadFromDraft(draftThresholds({})), {});
});
