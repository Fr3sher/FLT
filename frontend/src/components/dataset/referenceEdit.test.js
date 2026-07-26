import test from 'node:test';
import assert from 'node:assert/strict';
import {
  EDIT_ENGINES, defaultEditEngine, editBlockedReason, editEngineChoiceMessage,
  batchLiveNote, editPhase,
} from './referenceEdit.js';
import {
  STORAGE_ENGINES, STORAGE_PRIMARY, API_ENGINES, ENGINE_LABELS,
} from './engineSelection.js';

function fakeStorage(seed = {}) {
  const data = { ...seed };
  return { getItem(k) { return k in data ? data[k] : null; }, setItem(k, v) { data[k] = String(v); } };
}

/* What this file must keep guaranteeing about the list is that KLEIN IS OUT — the
   local GPU engine cannot edit a reference. It must NOT pin a fixed length: the
   old assertion said "exactly these two", which is why OpenRouter shipping as a
   generation engine left the ✦ Edit modal silently one engine short. */
test('EDIT_ENGINES excludes Klein — editing goes through an API engine', () => {
  assert.ok(!EDIT_ENGINES.includes('klein'));
  assert.ok(EDIT_ENGINES.length >= 2);
});

test('EDIT_ENGINES is derived from API_ENGINES, so it cannot drift from it', () => {
  assert.deepEqual(EDIT_ENGINES, [...API_ENGINES]);
  assert.notEqual(EDIT_ENGINES, API_ENGINES);   // a copy: mutating one can't move the other
});

test('OpenRouter can edit the reference, like the other API engines', () => {
  // Regression pin for the gap this wave closed: the engine existed for
  // generation while the edit path still refused it.
  assert.ok(EDIT_ENGINES.includes('openrouter'));
  assert.equal(editBlockedReason('add glasses', 'openrouter'), null);
});

test('defaultEditEngine mirrors the primary generation engine when it can edit', () => {
  assert.equal(defaultEditEngine(fakeStorage({ [STORAGE_ENGINES]: JSON.stringify(['nanobanana']) })),
    'nanobanana');
  assert.equal(defaultEditEngine(fakeStorage({ [STORAGE_PRIMARY]: 'chatgpt' })), 'chatgpt');
});

test('defaultEditEngine falls back to ChatGPT when the primary cannot edit', () => {
  // Klein is the primary but cannot edit -> a live default, not a dead selection.
  assert.equal(defaultEditEngine(fakeStorage({ [STORAGE_ENGINES]: JSON.stringify(['klein']) })),
    'chatgpt');
});

test('defaultEditEngine with no stored preference uses the historic default (Nano Banana)', () => {
  // readEngines falls back to DEFAULT_ENGINE (nanobanana), which CAN edit.
  assert.equal(defaultEditEngine(fakeStorage()), 'nanobanana');
});

test('editBlockedReason blocks an empty prompt and an un-editable engine', () => {
  assert.equal(editBlockedReason('add glasses', 'chatgpt'), null);
  assert.match(editBlockedReason('', 'chatgpt'), /describe/i);
  assert.match(editBlockedReason('   ', 'nanobanana'), /describe/i);
  assert.equal(editBlockedReason('x', 'klein'), editEngineChoiceMessage());
});

test('the refusal names the engines that DO edit, derived from the list', () => {
  // Pinned by construction, not by a fixed sentence: a hardcoded sentence is the
  // hardcoded list again, and it is what made the old message name two engines
  // after a third became editable.
  const msg = editEngineChoiceMessage();
  for (const e of EDIT_ENGINES) assert.ok(msg.includes(ENGINE_LABELS[e]), e);
  assert.ok(!msg.includes(ENGINE_LABELS.klein));
  assert.equal(msg, 'Pick Nano Banana Pro, ChatGPT or OpenRouter');
});

test('batchLiveNote informs only while a generate batch runs, never blocks', () => {
  assert.equal(batchLiveNote(null), null);
  assert.equal(batchLiveNote({ kind: 'caption' }), null);
  assert.match(batchLiveNote({ kind: 'generate' }), /future batches/i);
});

test('editPhase derives the modal phase from the server reference_edit object', () => {
  assert.equal(editPhase(null), 'idle');
  assert.equal(editPhase(undefined), 'idle');
  assert.equal(editPhase({ status: 'running' }), 'running');
  assert.equal(editPhase({ status: 'ready', candidate_filename: 'x.webp' }), 'ready');
  assert.equal(editPhase({ status: 'failed', error: 'boom' }), 'failed');
  assert.equal(editPhase({ status: 'weird' }), 'idle');   // unknown → idle (form)
});
