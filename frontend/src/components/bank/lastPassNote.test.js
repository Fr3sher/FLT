import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import { lastPassNote, lastPassSentence, relativeWhen } from './lastPassNote.js';

const NOW = 1_700_000_000_000;          // fixed clock — no Date.now() in assertions
const at = (secondsAgo) => (NOW - secondsAgo * 1000) / 1000;

test('a bank that has never run the pass says nothing at all', () => {
  assert.equal(lastPassNote({}, 'semantic_dedup', NOW), null);
  assert.equal(lastPassNote({ last_passes: {} }, 'semantic_dedup', NOW), null);
  assert.equal(lastPassNote({ last_passes: { semantic_dedup: {} } }, 'semantic_dedup', NOW), null);
  assert.equal(lastPassSentence(null), '');
});

test('the note carries what the last run found and when', () => {
  const note = lastPassNote({
    last_passes: {
      semantic_dedup: { at: at(3600 * 5), counts: { semantic_groups: 2358 } },
    },
  }, 'semantic_dedup', NOW);
  assert.equal(note.when, '5h ago');
  assert.match(note.summary, /2358 group/);
  assert.match(lastPassSentence(note), /Already run 5h ago, found 2358 group/);
});

test('zero groups is a result, not a missing one', () => {
  const note = lastPassNote({
    last_passes: { semantic_dedup: { at: at(60), counts: { semantic_groups: 0 } } },
  }, 'semantic_dedup', NOW);
  assert.match(note.summary, /^0 group/, 'a run that found nothing still ran');
  assert.equal(note.when, 'just now');
});

test('a pass with no count falls back to the detail the server recorded', () => {
  const note = lastPassNote({
    last_passes: { watermark: { at: at(3600 * 30), detail: 'done — 12 watermarked' } },
  }, 'watermark', NOW);
  assert.equal(note.summary, 'done — 12 watermarked');
  assert.equal(note.when, 'yesterday');
});

test('the age reads in the unit a human would use', () => {
  assert.equal(relativeWhen(at(30), NOW), 'just now');
  assert.equal(relativeWhen(at(600), NOW), '10 min ago');
  assert.equal(relativeWhen(at(3600 * 3), NOW), '3h ago');
  assert.equal(relativeWhen(at(86400 * 4), NOW), '4 days ago');
  assert.equal(relativeWhen(null, NOW), '');
});

test('the sentence never promises the groups are still current', () => {
  // The signature check that could promise that is a full-table read, and this
  // payload is polled while a job runs. The PASS answers it, once, for free.
  const note = lastPassNote({
    last_passes: { semantic_dedup: { at: at(120), counts: { semantic_groups: 3 } } },
  }, 'semantic_dedup', NOW);
  const sentence = lastPassSentence(note);
  assert.doesNotMatch(sentence, /still (current|valid|up to date)/i);
  assert.match(sentence, /says so instead of redoing it/);
});

test('the launch window actually shows the note', () => {
  const dialog = fs.readFileSync(new URL('./PassDialog.jsx', import.meta.url), 'utf8');
  assert.match(dialog, /lastPassNote|lastPassSentence/);
});
