import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canApplyRelocation, relocationApplyLabel, relocationDoneText,
  relocationSummary,
} from './bankRelocate.js';

const preview = (over) => ({
  folder: '/new/place', total: 10, found: 10, missing: 0, extra: 0,
  missing_sample: [], same_folder: false, ...over,
});

test('a folder holding none of the bank cannot be applied', () => {
  assert.equal(canApplyRelocation(preview({ found: 0, missing: 10 })), false);
  assert.equal(canApplyRelocation(preview({ found: 1, missing: 9 })), true);
  assert.equal(canApplyRelocation(null), false);
});

test('the mismatch verdict names the count and says what to pick instead', () => {
  const s = relocationSummary(preview({ found: 0, missing: 10 }));
  assert.equal(s.tone, 'error');
  assert.match(s.headline, /None of this bank's 10 image\(s\)/);
  assert.match(s.detail, /different folder/);
});

test('a full match promises the analysis is kept', () => {
  const s = relocationSummary(preview());
  assert.equal(s.tone, 'ok');
  assert.match(s.headline, /All 10 image\(s\)/);
  assert.match(s.detail, /keep\/reject decision is kept/);
});

test('a partial match warns with BOTH numbers and promises no deletion', () => {
  const s = relocationSummary(preview({ found: 6, missing: 4 }));
  assert.equal(s.tone, 'warn');
  assert.match(s.headline, /6 of 10 image\(s\) found — 4 are not there/);
  assert.match(s.detail, /nothing is deleted/);
});

test('extra files in the new folder are announced, not hidden', () => {
  assert.match(relocationSummary(preview({ extra: 3 })).detail,
    /3 extra image\(s\)/);
});

test('re-picking the current folder is called out instead of looking like a move', () => {
  const s = relocationSummary(preview({ same_folder: true }));
  assert.equal(s.tone, 'warn');
  assert.match(s.headline, /already points at/);
});

test('the apply label carries the number the user is agreeing to', () => {
  assert.match(relocationApplyLabel(preview({ found: 29759 })), /29,?759/);
});

test('the done toast reports what survived, and what is still absent', () => {
  assert.match(relocationDoneText({ found: 10, missing: 0 }),
    /10 image\(s\) found .*every analysis kept/);
  assert.match(relocationDoneText({ found: 6, missing: 4 }),
    /4 file\(s\) are still not on disk — their rows were kept/);
});
