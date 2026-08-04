import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CAPTION_SCOPE_OPTIONS, captionButtonLabel, captionCountsKnown,
  captionForcePileSize, captionOverwriteCount, captionRecaptionConfirmation,
  captionRecaptionDisabledReason, captionRecaptionLabel, captionRecaptionNote,
  captionScopeCount, captionScopeDisabledReason, captionScopeNote,
  captionScopeStatuses,
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

test('a selection overrides the scope in the label, and says "up to"', () => {
  // The server intersects the selection with the non-rejected, uncaptioned set, so a
  // selection of 12 can run on 6. "up to" is the bound the pass really honours; a bare
  // "12" would be the same broken promise the scope counts exist to end.
  assert.equal(captionButtonLabel(7, counts, 'keep'), '🏷️ Caption up to 7 selected');
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

/* 🔄 RE-CAPTION — the forced pass. Two numbers, and neither may be the other:
   what it REWRITES (the whole pile) and what it DESTROYS (the captions already there). */

test('the forced run size is the PILE, not the uncaptioned part of it', () => {
  assert.equal(captionForcePileSize(counts, 'keep'), 40);        // not 12
  assert.equal(captionForcePileSize(counts, 'pending'), 900);    // not 300
  assert.equal(captionForcePileSize(counts, ''), 940);           // keep + pending
});

test('the rejected pile is in no forced run either', () => {
  assert.equal(captionForcePileSize({ ...counts, reject: 99999 }, ''), 940);
});

test('the overwrite count is the pile minus what has no caption yet', () => {
  assert.equal(captionOverwriteCount(counts, 'keep'), 28);       // 40 - 12
  assert.equal(captionOverwriteCount(counts, 'pending'), 600);   // 900 - 300
  assert.equal(captionOverwriteCount(counts, ''), 628);
});

test('the overwrite count never goes negative on an inconsistent payload', () => {
  // Two numbers polled a moment apart can disagree; a "-3 captions overwritten" is
  // worse than a stale 0, and clamping keeps the confirmation readable.
  assert.equal(captionOverwriteCount(
    { keep: 2, caption_todo_keep: 5, pending: 0, caption_todo_pending: 0 }, 'keep'), 0);
});

test('the re-caption button quotes the number it REWRITES', () => {
  assert.equal(captionRecaptionLabel(counts, 'keep'), '🔄 Re-caption 40 kept');
  assert.equal(captionRecaptionLabel(counts, 'pending'), '🔄 Re-caption 900 undecided');
  assert.equal(captionRecaptionLabel(counts, ''), '🔄 Re-caption 940 images');
  // …and never a number nobody measured.
  assert.equal(captionRecaptionLabel(null, ''), '🔄 Re-caption');
});

test('an inert re-caption button quotes NO number at all', () => {
  // A greyed button still offering "24 images" is the same defect one rung down: a
  // figure on screen that no click will act on. The reason is in the tooltip; the
  // label goes back to the bare verb.
  const why = captionRecaptionDisabledReason(5, false, counts, 'keep');
  assert.notEqual(why, '');
  assert.equal(captionRecaptionLabel(counts, 'keep', why), '🔄 Re-caption');
  assert.equal(captionRecaptionLabel(counts, 'keep', ''), '🔄 Re-caption 40 kept');
});

test('the two buttons quote different numbers, on purpose', () => {
  // 🏷️ Caption fills 12; 🔄 Re-caption rewrites 40 of which 28 already had a caption.
  // If these ever collapsed into one figure, one of the two buttons would be lying.
  assert.equal(captionScopeCount(counts, 'keep'), 12);
  assert.equal(captionForcePileSize(counts, 'keep'), 40);
  assert.equal(captionOverwriteCount(counts, 'keep'), 28);
});

test('re-caption refuses to run on a selection, and says why', () => {
  const why = captionRecaptionDisabledReason(5, false, counts, 'keep');
  assert.match(why, /selection/i);
  assert.match(why, /5/);
  // The REASON matters: a selection can span pages that were never loaded, so the
  // overwrite count is unknowable client-side — and this button never runs on a
  // number it cannot state.
  assert.match(why, /cannot be counted|pile/i);
});

test('re-caption is inert while a pass runs, and before the counts land', () => {
  assert.match(captionRecaptionDisabledReason(0, true, counts, ''), /already running/i);
  assert.match(captionRecaptionDisabledReason(0, false, null, ''), /counts/i);
  assert.match(captionRecaptionDisabledReason(0, false, {}, ''), /counts/i);
});

test('re-caption is inert when there is no caption to overwrite', () => {
  const fresh = { keep: 40, pending: 900, caption_todo_keep: 40,
    caption_todo_pending: 900 };
  assert.match(captionRecaptionDisabledReason(0, false, fresh, 'keep'),
    /Nothing to re-caption/i);
  // …and it points at the button that CAN do something, instead of dead-ending.
  assert.match(captionRecaptionDisabledReason(0, false, fresh, 'keep'), /🏷️ Caption/);
  assert.equal(captionRecaptionDisabledReason(0, false, counts, 'keep'), '');
});

test('the warning names both numbers, the hand-edits and the missing undo', () => {
  const note = captionRecaptionNote(0, false, counts, 'keep');
  assert.match(note, /40/);                       // what it rewrites
  assert.match(note, /28/);                       // what it destroys
  assert.match(note, /by hand/i);
  assert.match(note, /no undo/i);
});

test('the warning is silent whenever the button cannot run', () => {
  // A warning about an impossible action is what teaches people to skip warnings.
  assert.equal(captionRecaptionNote(5, false, counts, 'keep'), '');
  assert.equal(captionRecaptionNote(0, true, counts, 'keep'), '');
  assert.equal(captionRecaptionNote(0, false, null, 'keep'), '');
  assert.equal(captionRecaptionNote(
    0, false, { keep: 4, caption_todo_keep: 4, pending: 0, caption_todo_pending: 0 },
    'keep'), '');
});

test('the confirmation is the Dataset\'s sentence, plus the two bank facts', () => {
  const q = captionRecaptionConfirmation(counts, 'keep');
  // Same opening and same closing word as dataset/captionCategory.js — the app asks
  // this question one way, not two.
  assert.match(q, /^Re-captioning overwrites the 28 existing caption\(s\)/);
  assert.match(q, /Continue\?$/);
  // …and the two things the dataset never has to say.
  assert.match(q, /40 kept image\(s\)/);
  assert.match(q, /cannot be told apart/i);
  assert.match(q, /cannot be undone/i);
});

test('the confirmation names the right pile for each scope', () => {
  assert.match(captionRecaptionConfirmation(counts, 'pending'),
    /900 undecided image\(s\)/);
  assert.match(captionRecaptionConfirmation(counts, ''),
    /940 kept and undecided image\(s\)/);
});
