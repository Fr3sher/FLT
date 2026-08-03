import test from 'node:test'
import assert from 'node:assert/strict'

import {
  frameOptions, clipSeconds, frameOptionLabel, defaultFrames, needsManualFrames,
  sizeOptions, targetWarnings, targetBadge, promoteProblem, promotePayload,
  promoteScopeLabel,
} from './videoTargetChoice.js'

// Verbatim shapes of GET /api/video/targets — kept as fixtures rather than
// invented, so a catalogue change that breaks the picker breaks a test.
const WAN14B = {
  key: 'wan22_14b', label: 'Wan 2.1 / 2.2 14B', fps: 16,
  frame_choices: [17, 25, 33, 49, 65, 81, 97, 121], frame_default: 81,
  default_seconds: 5, size_multiple: 16,
  recommended_sizes: [[832, 480], [480, 832], [1280, 720], [720, 1280]],
  keep_audio: false, caption_style: 'freeform',
  training_verified: true, licence_note: null,
}
const TI2V5B = {
  key: 'wan22_ti2v5b', label: 'Wan 2.2 TI2V-5B', fps: 24,
  frame_choices: [25, 49, 81, 97, 121], frame_default: 121, default_seconds: 5,
  size_multiple: 32, recommended_sizes: [[1280, 704], [704, 1280]],
  keep_audio: false, caption_style: 'freeform',
  training_verified: false, licence_note: null,
}
const MINIMAX = {
  key: 'minimax_h3', label: 'MiniMax H3', fps: 24,
  frame_choices: [39, 56, 73, 90, 107, 124], frame_default: 124,
  size_multiple: 32, recommended_sizes: [[1344, 768]],
  keep_audio: true, caption_style: 'paragraph_with_audio',
  training_verified: false,
  licence_note: 'MiniMax H3 Community License grants NO rights in the EU, UK, '
    + 'South Korea or USA — and the restriction covers the outputs, not just '
    + 'the model. Check your territory first.',
}
const GENERIC = {
  key: 'generic', label: 'Generic / other', fps: null, frame_choices: [],
  frame_default: null, size_multiple: null, recommended_sizes: [],
  keep_audio: false, caption_style: 'freeform',
  training_verified: false, licence_note: null,
}

// ---- the two fields that save a week ---------------------------------------

test('a target with no known trainer SAYS SO at the picker', () => {
  // Exactly one of the four clears this bar. Someone who discovers it after
  // cutting and captioning has lost the week.
  const w = targetWarnings(TI2V5B)
  assert.ok(w.some((x) => x.key === 'unverified'))
  assert.match(w.find((x) => x.key === 'unverified').text, /No LoRA trainer is known/)
  assert.equal(targetBadge(TI2V5B).text, 'Not trainable yet')
})

test('the trainable target carries no scare text', () => {
  assert.deepEqual(targetWarnings(WAN14B), [])
  assert.equal(targetBadge(WAN14B).text, 'Trainable')
})

test('the MiniMax licence names the excluded territories AND the outputs', () => {
  // The restriction reaching the outputs is the part people get wrong — keeping
  // the training private is not a way around it.
  const licence = targetWarnings(MINIMAX).find((w) => w.key === 'licence')
  assert.ok(licence, 'the licence note must be surfaced')
  assert.equal(licence.tone, 'danger')
  for (const territory of ['EU', 'UK', 'South Korea', 'USA']) {
    assert.ok(licence.text.includes(territory), `territory ${territory} not named`)
  }
  assert.match(licence.text, /outputs/)
})

test('the licence outranks the missing trainer in the warning order', () => {
  // A licence that grants nothing where you live costs more than a trainer that
  // does not exist yet, and both apply to MiniMax.
  const keys = targetWarnings(MINIMAX).map((w) => w.key)
  assert.ok(keys.indexOf('licence') < keys.indexOf('unverified'))
})

test('a joint audio-video target says the soundtrack is kept', () => {
  assert.ok(targetWarnings(MINIMAX).some((w) => w.key === 'audio'))
  assert.ok(!targetWarnings(WAN14B).some((w) => w.key === 'audio'))
})

// ---- lengths: the menu, never a seconds field -------------------------------

test('the length options come from frame_choices and nowhere else', () => {
  assert.deepEqual(frameOptions(WAN14B).map((o) => o.frames), WAN14B.frame_choices)
  assert.deepEqual(frameOptions(MINIMAX).map((o) => o.frames), MINIMAX.frame_choices)
})

test('seconds are DISPLAYED per option, computed at the target’s own rate', () => {
  // The cross-check that (frames-1)/fps is the right arithmetic: both Wan
  // variants land on exactly 5.00 s at their own rate — 81 @ 16 and 121 @ 24.
  assert.equal(clipSeconds(WAN14B, 81), 5)
  assert.equal(clipSeconds(TI2V5B, 121), 5)
  assert.equal(frameOptionLabel(WAN14B, 81), '81 frames — 5.00s')
})

test('a target with no fps shows frames alone rather than a wrong duration', () => {
  assert.equal(clipSeconds(GENERIC, 60), null)
  assert.equal(frameOptionLabel(GENERIC, 60), '60 frames')
})

test('a catalogue with no verified lengths asks for a frame count, not seconds', () => {
  // "Generic / other" imposes nothing. Falling back to Wan's menu here would
  // offer 4n+1 lengths for a model nobody said anything about.
  assert.deepEqual(frameOptions(GENERIC), [])
  assert.equal(needsManualFrames(GENERIC), true)
  assert.equal(needsManualFrames(WAN14B), false)
  assert.equal(defaultFrames(GENERIC), null)
  assert.match(promoteProblem({ name: 'x', target: GENERIC, frames: null }),
    /type a frame count/)
})

test('the default length is the catalogue’s own', () => {
  assert.equal(defaultFrames(WAN14B), 81)
  assert.equal(defaultFrames(TI2V5B), 121)
})

// ---- sizes ------------------------------------------------------------------

test('“keep the source size” is always the first size option', () => {
  const opts = sizeOptions(WAN14B)
  assert.equal(opts[0].key, 'source')
  assert.equal(opts[0].width, null)
  assert.deepEqual(opts.slice(1).map((o) => o.key),
    ['832x480', '480x832', '1280x720', '720x1280'])
})

test('a target with no recommended sizes still offers the source size', () => {
  assert.deepEqual(sizeOptions(GENERIC).map((o) => o.key), ['source'])
})

// ---- the payload ------------------------------------------------------------

test('the source size sends NO width and NO height', () => {
  const body = promotePayload({
    name: ' wan set ', targetKey: 'wan22_14b', frames: 81,
    size: { width: null, height: null }, ids: [],
  })
  assert.deepEqual(body, { name: 'wan set', target_profile: 'wan22_14b', frames: 81 })
})

test('a lone width is never sent — the server reads the PAIR or nothing', () => {
  // width without height is silently ignored server-side, so the user would get
  // a source-size cut while the dialog said 832 wide.
  const body = promotePayload({
    name: 'x', targetKey: 'wan22_14b', frames: 81, size: { width: 832, height: null },
  })
  assert.ok(!('width' in body) && !('height' in body))
})

test('an EMPTY selection omits ids, because empty means "every kept clip"', () => {
  // The server's convention. Sending `ids: []` and expecting "nothing" would
  // promote the whole bank.
  assert.ok(!('ids' in promotePayload({ name: 'x', targetKey: 'k', frames: 81, ids: [] })))
  assert.deepEqual(
    promotePayload({ name: 'x', targetKey: 'k', frames: 81, ids: [3, 7] }).ids, [3, 7])
})

test('the button says which clips it is about to encode', () => {
  assert.equal(promoteScopeLabel(0, 128), 'all 128 kept clips')
  assert.equal(promoteScopeLabel(1, 128), '1 selected clip')
  assert.equal(promoteScopeLabel(12, 128), '12 selected clips')
  assert.equal(promoteScopeLabel(0, 1), 'all 1 kept clip')
})

// ---- refusals ---------------------------------------------------------------

test('the dialog refuses what the server would refuse, before the round trip', () => {
  assert.match(promoteProblem({ name: '  ', target: WAN14B, frames: 81 }), /Name the dataset/)
  assert.match(promoteProblem({ name: 'x', target: null, frames: 81 }), /Pick a target/)
  assert.match(promoteProblem({ name: 'x', target: WAN14B, frames: null }), /Pick a clip length/)
  assert.match(promoteProblem({ name: 'x', target: GENERIC, frames: 12.5 }),
    /whole number of frames/)
  assert.equal(promoteProblem({ name: 'x', target: WAN14B, frames: 81 }), null)
})
