import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CAPTION_SCOPE_OPTIONS, captionButtonLabel, captionCountsKnown, captionScopeCount,
  captionScopeDisabledReason, captionScopeNote, captionScopeStatuses,
} from './bankCaptionScope.js';

/* The bank caption scope: three options, two vocabularies, and one number that has to
   be the number the pass moves. */

const counts = { keep: 40, pending: 900, reject: 60, caption_todo_keep: 12,
  caption_todo_pending: 300 };

test('exactly three scopes, and the bin is not one of them', () => {
  assert.equal(CAPTION_SCOPE_OPTIONS.length, 3);
  const ids = CAPTION_SCOPE_OPTIONS.map((o) => o.id);
  assert.deepEqual(ids, ['', 'keep', 'pending']);
  // Not a stylistic check: offering the rejected pile would mean curating from the
  // bin, and the server refuses it with a 400.
  const wire = JSON.stringify(CAPTION_SCOPE_OPTIONS);
  assert.ok(!wire.includes('reject'), 'reject must never be an offered scope');
});

test('the wire carries the stored column values, the labels carry the human words', () => {
  assert.deepEqual(captionScopeStatuses('keep'), ['keep']);
  assert.deepEqual(captionScopeStatuses('pending'), ['pending']);
  const labels = CAPTION_SCOPE_OPTIONS.map((o) => o.label);
  assert.ok(labels.some((l) => /Kept/.test(l)));
  assert.ok(labels.some((l) => /Undecided/.test(l)));
  // …and never the raw column values, which are an implementation detail.
  assert.ok(!labels.some((l) => /\bkeep\b|\bpending\b/.test(l)));
});

test('the DEFAULT scope sends nothing at all', () => {
  // The byte-identical contract: a run that leaves the select alone must post the
  // same body the pass posted before this control existed. `null` is what the caller
  // spreads away; anything truthy would add a key.
  assert.equal(captionScopeStatuses(''), null);
  assert.equal(captionScopeStatuses(undefined), null);
  assert.equal(captionScopeStatuses('nonsense'), null);
});

test('the count is the UNCAPTIONED rows of the scope, not the size of the pile', () => {
  assert.equal(captionScopeCount(counts, 'keep'), 12);        // not 40
  assert.equal(captionScopeCount(counts, 'pending'), 300);    // not 900
  assert.equal(captionScopeCount(counts, ''), 312);
});

test('the rejected pile is in no count', () => {
  assert.equal(captionScopeCount({ ...counts, reject: 99999 }, ''), 312);
});

test('the button quotes the number it will move', () => {
  assert.equal(captionButtonLabel(0, counts, ''), '🏷️ Caption 312 images');
  assert.equal(captionButtonLabel(0, counts, 'keep'), '🏷️ Caption 12 kept');
  assert.equal(captionButtonLabel(0, counts, 'pending'), '🏷️ Caption 300 undecided');
});

test('a selection overrides the scope in the label', () => {
  assert.equal(captionButtonLabel(7, counts, 'keep'), '🏷️ Caption 7 selected');
});

test('"not measured yet" is not rendered as zero', () => {
  // Before the first payload lands there is no count. Showing "Caption 0 images"
  // then would be a lie the user cannot distinguish from an empty bank.
  assert.equal(captionCountsKnown(null), false);
  assert.equal(captionCountsKnown({ keep: 3 }), false);
  assert.equal(captionCountsKnown(counts), true);
  assert.equal(captionButtonLabel(0, null, ''), '🏷️ Caption all');
  assert.equal(captionButtonLabel(0, {}, 'keep'), '🏷️ Caption kept');
});

test('the scope goes inert while a selection is live, and says why', () => {
  assert.equal(captionScopeDisabledReason(0, false), '');
  const why = captionScopeDisabledReason(5, false);
  assert.match(why, /selection/i);
  assert.match(why, /5/);
  assert.match(captionScopeDisabledReason(0, true), /already running/i);
});

test('the note names the number, the skip rule and the bin — every time', () => {
  const note = captionScopeNote(0, counts, 'keep');
  assert.match(note, /12/);
  assert.match(note, /no caption yet/i);
  assert.match(note, /Rejected images are never captioned/i);
});

test('the note switches to the selection when there is one', () => {
  const note = captionScopeNote(9, counts, 'keep');
  assert.match(note, /9 selected/);
  assert.ok(!/12/.test(note), 'a selection must not quote a status count');
});

test('an empty scope says so instead of offering a pass that does nothing', () => {
  const note = captionScopeNote(0, { caption_todo_keep: 0, caption_todo_pending: 3 }, 'keep');
  assert.match(note, /Nothing to caption/i);
});
