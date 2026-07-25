import test from 'node:test';
import assert from 'node:assert/strict';
import {
  deleteDestination, isRecoverable, overlapNotice, sharedFileCount, sharedFilesWarning,
} from './bankOverlap.js';

test('a permanent delete is never described as recoverable', () => {
  assert.equal(isRecoverable('trash'), true);
  assert.equal(isRecoverable('app_trash'), true);
  assert.equal(isRecoverable('delete'), false);
  assert.match(deleteDestination('delete'), /for good/);
});

test('each destination names a place the user can actually go look', () => {
  assert.match(deleteDestination('trash'), /Recycle Bin/);
  assert.match(deleteDestination('app_trash'), /Settings/);
});

test('an unknown mode is treated as permanent, never as safe', () => {
  assert.equal(isRecoverable(undefined), false);
  assert.match(deleteDestination(undefined), /for good/);
});

test('overlapNotice: a bank on its own says nothing', () => {
  assert.equal(overlapNotice([]), null);
  assert.equal(overlapNotice(null), null);
  assert.equal(overlapNotice([{ id: 1 }]), null);   // nameless row is not a notice
});

test('overlapNotice names the other bank and why it matters', () => {
  const n = overlapNotice([{ id: 2, name: 'Everything', relation: 'parent' }]);
  assert.match(n, /Everything/);
  assert.match(n, /Delete rejected/);
});

test('overlapNotice lists every overlapping bank', () => {
  const n = overlapNotice([{ id: 2, name: 'A' }, { id: 3, name: 'B' }]);
  assert.match(n, /“A”, “B”/);
});

test('sharedFilesWarning: nothing shared -> no warning', () => {
  assert.equal(sharedFilesWarning({ shared: [] }), null);
  assert.equal(sharedFilesWarning(null), null);
  assert.equal(sharedFilesWarning({ shared: [{ name: 'A', files: 0 }] }), null);
});

test('sharedFilesWarning says how many files the other bank loses', () => {
  const w = sharedFilesWarning({ shared: [{ id: 2, name: 'Everything', files: 1541 }] });
  assert.match(w, /1541/);
  assert.match(w, /Everything/);
  assert.match(w, /decisions/);      // the cost is the triage, not just the bytes
});

test('sharedFileCount totals across banks and survives junk', () => {
  assert.equal(sharedFileCount({ shared: [{ files: 3 }, { files: 4 }] }), 7);
  assert.equal(sharedFileCount({ shared: [{ files: 'x' }] }), 0);
  assert.equal(sharedFileCount(null), 0);
});
