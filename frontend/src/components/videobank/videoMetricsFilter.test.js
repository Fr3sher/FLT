import test from 'node:test';
import assert from 'node:assert/strict';
import {
  FLAG_LABELS, cutSummary, filterByFlag, flagCounts, thresholdFields,
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
