import test from 'node:test'
import assert from 'node:assert/strict'

import {
  searchUnavailableReason, summarize, unsearchableNote, formatTimestamp,
  frameLabelPhrase, matchLine, seekFragment, playFromSecond,
  VIDEO_CLIP_LIMITS, limitsSentence,
} from './videoClipSearch.js'

// ---- what stops a search before it starts ------------------------------------

test('a bank whose shots were never embedded says which pass to run', () => {
  // Not "no results": the shots are there, they simply cannot be reached by any
  // phrase. Those two sentences send the user to two different places.
  const why = searchUnavailableReason({ clips: 40, embedded: 0 }, { available: true })
  assert.match(why, /Find scenes/i)
})

test('a partly embedded bank is searchable and says nothing', () => {
  assert.equal(searchUnavailableReason({ clips: 40, embedded: 12 },
    { available: true }), '')
})

test('an install that cannot run CLIP says so instead of offering the pass', () => {
  // Telling someone to run a pass that cannot start is a loop, not an answer.
  const why = searchUnavailableReason({ clips: 40, embedded: 0 },
    { available: false, reason: 'text search needs torch + open_clip' })
  assert.match(why, /torch/)
  assert.doesNotMatch(why, /Find scenes/i)
})

test('an empty bank is not scolded about embeddings', () => {
  assert.match(searchUnavailableReason({ clips: 0, embedded: 0 },
    { available: true }), /no shots/i)
})

// ---- the honest summary -------------------------------------------------------

test('the summary never claims a match, only a ranking', () => {
  const line = summarize({
    query: 'a red car', pool: 120, unembedded: 0, clip_ids: [1, 2, 3],
    score_range: { top: 0.24, bottom: 0.19 }, pool_median: 0.12,
  })
  assert.match(line, /3 closest/)
  assert.match(line, /120/)
  // The load-bearing disclaimer: every shot scores something against every
  // phrase, so a full-looking result list is not evidence of anything.
  assert.match(line, /does not select|not a filter/i)
})

test('shots that could not be searched are named in the summary', () => {
  const line = summarize({
    query: 'a red car', pool: 12, unembedded: 28, clip_ids: [1],
    score_range: { top: 0.2, bottom: 0.2 }, pool_median: 0.1,
  })
  assert.match(line, /28/)
})

test('an empty result set still explains itself', () => {
  const line = summarize({ query: 'a red car', pool: 0, unembedded: 40, clip_ids: [] })
  assert.match(line, /a red car/)
  assert.match(line, /40/)
})

test('nothing at all is an empty string, not the word undefined', () => {
  assert.equal(summarize(null), '')
  assert.equal(unsearchableNote({ unembedded: 0 }), '')
})

// ---- pointing at the right second ---------------------------------------------

test('a timestamp is minutes and seconds, not raw float seconds', () => {
  // "83.4" is not a position anyone can find in a player.
  assert.equal(formatTimestamp(83.4), '1:23.4')
  assert.equal(formatTimestamp(4), '0:04.0')
  assert.equal(formatTimestamp(3671.2), '61:11.2')
  assert.equal(formatTimestamp(null), '—')
  assert.equal(formatTimestamp('nope'), '—')
})

test('the frame that matched is described in words, not by its internal label', () => {
  assert.match(frameLabelPhrase('start'), /start/i)
  assert.match(frameLabelPhrase('end'), /end/i)
  assert.match(frameLabelPhrase('key'), /sharp/i)
  // An unknown label must degrade to nothing rather than leak a key name.
  assert.equal(frameLabelPhrase('wat'), '')
})

test('the match line gives the second AND says it is one moment of the shot', () => {
  // The whole reason several frames are embedded: the phrase may describe two
  // seconds of a thirty-second shot, and pretending otherwise oversells it.
  const line = matchLine({ frame_s: 12.5, frame_label: 'end', score: 0.21 })
  assert.match(line, /0:12\.5/)
  assert.match(line, /end/i)
})

test('a match line for a shot with no timestamp does not invent one', () => {
  assert.equal(matchLine(null), '')
  assert.equal(matchLine({ score: 0.2 }), '')
})

// ---- seeking the player to the matched second ---------------------------------

test('the media fragment seeks to the matched second inside the shot', () => {
  // The player streams the SOURCE file, so the offset is absolute — using the
  // second as if it were relative to the shot lands in the wrong place.
  assert.equal(seekFragment({ start_s: 10, end_s: 20 }, 14.5), '#t=14.5,20')
})

test('a matched second outside the shot falls back to the shot itself', () => {
  // Bounds can be re-cut after embedding. Seeking outside the span would show a
  // frame from a neighbouring shot and call it the match.
  assert.equal(seekFragment({ start_s: 10, end_s: 20 }, 55), '#t=10,20')
  assert.equal(seekFragment({ start_s: 10, end_s: 20 }, null), '#t=10,20')
})

test('the player opens on the matched second, and never outside the shot', () => {
  assert.equal(playFromSecond({ start_s: 10, end_s: 20 }, 14.5), 14.5)
  assert.equal(playFromSecond({ start_s: 10, end_s: 20 }, 9.9), 10)
  assert.equal(playFromSecond({ start_s: 10, end_s: 20 }, undefined), 10)
})

// ---- what CLIP genuinely cannot do --------------------------------------------

test('the negation trap is stated, because it fails invisibly', () => {
  // Measured on this exact checkpoint: "without a helmet" scored HIGHER on a
  // helmeted astronaut than "with a helmet". The results come back full and
  // confident, carrying exactly what was asked to be gone.
  const all = VIDEO_CLIP_LIMITS.join(' ')
  assert.match(all, /without/i)
  assert.match(limitsSentence(), /-/)
})
