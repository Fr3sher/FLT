import test from 'node:test';
import assert from 'node:assert/strict';

import {
  captionChips, captionStyle, tagsParam, tagFilterSummary, MAX_CHIPS,
} from './bankTags.js';

// ---- which shape is this caption? ------------------------------------------

test('booru captions are detected by SHORT comma segments, not by commas alone', () => {
  assert.equal(captionStyle('a woman, red dress, balcony, golden hour'), 'booru');
  // Prose uses commas too — treating this as four tags would produce four
  // sentence-long chips nobody can click.
  assert.equal(captionStyle(
    'a woman in a red dress, seen from behind, standing on a stone balcony'), 'prose');
  assert.equal(captionStyle('a woman in a red dress on a balcony'), 'prose');
  // Too few segments to tell: prose is the safe fallback (it always yields
  // usable chips; booru on a sentence yields one unusable one).
  assert.equal(captionStyle('a woman, a balcony'), 'prose');
  assert.equal(captionStyle(''), 'prose');
});

// ---- the chips themselves ---------------------------------------------------

test('a booru caption keeps its tags WHOLE, in order', () => {
  assert.deepEqual(captionChips('a woman, red dress, golden hour, balcony'),
    ['a woman', 'red dress', 'golden hour', 'balcony']);
});

test('a prose caption yields meaningful words, without the grammar', () => {
  const chips = captionChips('A woman in a red dress standing on the balcony');
  assert.deepEqual(chips, ['woman', 'red', 'dress', 'standing', 'balcony']);
  // The stop list must not eat real subjects — these are attributes someone
  // would genuinely filter on.
  for (const kept of ['woman', 'red', 'dress', 'balcony']) {
    assert.ok(chips.includes(kept), kept);
  }
});

test('words that survive every caption are dropped, real ones are not', () => {
  const chips = captionChips('the photo of a young woman with long hair');
  for (const dropped of ['the', 'of', 'a', 'with', 'photo']) {
    assert.ok(!chips.includes(dropped), `${dropped} should be dropped`);
  }
  // 'young' and 'long' are deliberately NOT in the stop list.
  assert.deepEqual(chips, ['young', 'woman', 'long', 'hair']);
});

test('hyphens and apostrophes survive inside a word', () => {
  assert.deepEqual(captionChips('a woman in a t-shirt holding her friend’s hand'),
    ['woman', 't-shirt', 'holding', 'friend’s', 'hand']);
});

test('no empty, duplicate, single-letter or numeric chips', () => {
  const chips = captionChips('a dress, dress,  , 2, x, DRESS, red dress');
  assert.deepEqual(chips, ['a dress', 'dress', 'red dress']);
  assert.equal(new Set(chips).size, chips.length);
});

test('an absent caption yields nothing at all (the UI then says so)', () => {
  assert.deepEqual(captionChips(''), []);
  assert.deepEqual(captionChips(null), []);
  assert.deepEqual(captionChips(undefined), []);
});

test('a caption dump cannot flood the row', () => {
  const long = Array.from({ length: 80 }, (_, i) => `tag${String.fromCharCode(97 + i % 26)}${i}`).join(' ');
  assert.equal(captionChips(long).length, MAX_CHIPS);
  // A whole sentence that slipped through as one booru segment is not a tag.
  assert.deepEqual(captionChips(`${'x'.repeat(40)}, red dress, y, z`), ['red dress']);
});

// ---- what gets sent, and what the user is told -----------------------------

test('the query value is comma-joined, and an empty pick is NO filter', () => {
  assert.equal(tagsParam(new Set(['red dress', 'balcony'])), 'red dress,balcony');
  // null, not '' — an empty-string filter is a filter, and would be a bug the
  // server has to guess about.
  assert.equal(tagsParam(new Set()), null);
  assert.equal(tagsParam(null), null);
});

test('the summary SPELLS OUT that several chips mean AND', () => {
  assert.match(tagFilterSummary(new Set(['red'])), /mentions “red”/);
  const two = tagFilterSummary(new Set(['red', 'dress']));
  assert.match(two, /ALL of/, 'AND must be stated, not inferred from the chips');
  assert.match(two, /“red” \+ “dress”/);
  assert.equal(tagFilterSummary(new Set()), '');
});
