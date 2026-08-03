import test from 'node:test';
import assert from 'node:assert/strict';
import {
  SKIP_LABEL, acceptLabel, defaultPicked, folderLabel, notReachedLine,
  nothingFoundLine, preflightCostLine, preflightHeadline, preflightNeeded,
  preflightRows, preflightWillSample, savingLine, skipNote, togglePicked,
} from './personPreflight.js';

const probe = (subfolder, over = {}) => ({
  subfolder, verdict: 'consistent', sample: 15, scorable: 15, largest: 15,
  faces: 1, images: 300, stale: false, ...over,
});

const plan = (over = {}) => ({
  available: true, sample_size: 15, min_images: 5, candidates: 0, covered: 0,
  left: 0, sample_cost: 0, full_cost: 0, known: [], asserted: [], ...over,
});

// --- when the question is worth asking at all -------------------------------
test('no candidate and no verdict = no dialog: the pass starts straight away', () => {
  assert.equal(preflightNeeded(plan()), false);
  assert.equal(preflightNeeded(null), false);
});

test('the extra being absent skips the preflight entirely', () => {
  // There is no probe without the face extra, and no pass either — the pass
  // itself reports the missing install, so a dialog here would only be in the way.
  assert.equal(preflightNeeded(plan({ available: false, candidates: 9 })), false);
});

test('folders to sample, or verdicts already on file, both raise the question', () => {
  assert.equal(preflightNeeded(plan({ candidates: 4 })), true);
  assert.equal(preflightNeeded(plan({ known: [probe('a')] })), true);
  // …but only the first has any sampling left to pay for.
  assert.equal(preflightWillSample(plan({ candidates: 4 })), true);
  assert.equal(preflightWillSample(plan({ known: [probe('a')] })), false);
});

// --- the cost, said before it is paid ---------------------------------------
test('the cost line puts the sample next to the pass it replaces', () => {
  const line = preflightCostLine(plan({
    candidates: 12, covered: 12, sample_cost: 180, full_cost: 7316,
  }));
  assert.match(line, /12 folders/);
  assert.match(line, /180 in all/);
  assert.match(line, /7316 this pass would embed/);
});

test('no sampling left = no cost line to print', () => {
  assert.equal(preflightCostLine(plan({ known: [probe('a')] })), null);
});

test('a ceiling that is not reached is always stated', () => {
  // The whole point: silence about 300 folders would read as "they are not one
  // person", which is the opposite of what happened.
  assert.match(notReachedLine(plan({ left: 300 })), /300 folders were not checked/);
  assert.match(notReachedLine(plan({ left: 300 })), /full analysis/);
  assert.equal(notReachedLine(plan({ left: 0 })), null);
});

// --- the offer, and what is pre-ticked --------------------------------------
test('only a consistent verdict is pre-ticked; mixed and inconclusive are not', () => {
  const rows = preflightRows(plan({
    known: [
      probe('anna'),
      probe('bob', { verdict: 'mixed', faces: 3, largest: 6 }),
      probe('scraps', { verdict: 'inconclusive', scorable: 1, largest: 1 }),
    ],
  }));
  assert.deepEqual(rows.map((r) => r.preselect), [true, false, false]);
  assert.deepEqual(defaultPicked(rows), ['anna']);
  // And each says WHY, in the sample's own terms.
  assert.match(rows[0].line, /15\/15 of 15 sampled images look like the same person/);
  assert.match(rows[1].line, /3 different faces in the sample — analyzed in full/);
  assert.match(rows[2].line, /only 1 of 15 sampled images had a usable face/);
  assert.deepEqual(rows.map((r) => r.tone), ['ok', 'warn', 'muted']);
});

test('the headline is the sentence the critique asked for', () => {
  const rows = preflightRows(plan({
    known: [probe('a'), probe('b'), probe('c', { verdict: 'mixed', faces: 2 })],
  }));
  const line = preflightHeadline(rows);
  assert.match(line, /2 folders look like a single person/);
  assert.match(line, /treat each of them as one person/);
  assert.match(line, /skip their full analysis/);
});

test('one folder reads as one folder, not "1 folders"', () => {
  assert.match(preflightHeadline(preflightRows(plan({ known: [probe('a')] }))),
    /1 folder looks like a single person — treat it as one person and skip its full analysis/);
});

test('a preflight that found nothing says so instead of showing an empty list', () => {
  const rows = preflightRows(plan({ known: [probe('a', { verdict: 'mixed', faces: 2 })] }));
  assert.equal(preflightHeadline(rows), null);
  assert.match(nothingFoundLine(rows), /None of the 1 checked folders looked like a single person/);
  assert.match(nothingFoundLine([]), /Nothing to check here/);
});

// --- the two ways out -------------------------------------------------------
test('the primary button names both halves of what it does', () => {
  assert.equal(acceptLabel(['anna', 'bob']), '👤 Group 2 folders & analyze the rest');
  assert.equal(acceptLabel(['anna']), '👤 Group 1 folder & analyze the rest');
  // Untick everything and the primary IS the escape hatch — it must say so
  // rather than promising a grouping that will not happen.
  assert.equal(acceptLabel([]), '👥 Analyze everything');
});

test('"analyze everything anyway" states its own cost', () => {
  assert.equal(SKIP_LABEL, '👥 Analyze everything anyway');
  assert.match(skipNote(plan({ full_cost: 7316 })), /7316 images embedded/);
  assert.match(skipNote(plan()), /Every folder gets the full face pass\./);
});

test('the saving is counted from the boxes actually ticked', () => {
  const rows = preflightRows(plan({
    known: [probe('a', { images: 300 }), probe('b', { images: 120 })],
  }));
  assert.match(savingLine(rows, ['a', 'b']), /420 images are grouped instantly/);
  assert.match(savingLine(rows, ['b']), /120 images are grouped instantly/);
  assert.equal(savingLine(rows, []), null);
});

// --- the bank root is a folder like any other -------------------------------
test("'' is the bank root, a tickable folder with a name of its own", () => {
  const rows = preflightRows(plan({ known: [probe(''), probe('anna')] }));
  assert.deepEqual(defaultPicked(rows), ['', 'anna']);
  assert.equal(folderLabel(''), 'the bank root');
  assert.equal(folderLabel('anna'), 'anna');
  // Unticking it must remove '' and not be swallowed by a falsiness test.
  assert.deepEqual(togglePicked(['', 'anna'], ''), ['anna']);
  assert.deepEqual(togglePicked(['anna'], ''), ['anna', '']);
});
