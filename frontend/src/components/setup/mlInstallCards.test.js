/** WHY THIS FILE EXISTS — the day the video wave landed, its capability strip
 * told the first real user "→ Install the video extra from Setup", and Setup
 * had no such button: both installs existed only as API actions. A promise in
 * one file, its keeper in another, nothing holding them together. These tests
 * are that hold. */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ML_INSTALL_CARDS } from './mlInstallCards.js'
import { VIDEO_PIECES } from '../videobank/videoCapability.js'

test('every install the video capability strip points at has a Setup card', () => {
  // A piece whose `fix` line says "from Setup" MUST carry `setupCap`, and a
  // card must exist whose `cap` turns that exact probe green — otherwise the
  // remedy is a dead end the user walks into.
  const offered = new Set(ML_INSTALL_CARDS.map((c) => c.cap))
  for (const piece of VIDEO_PIECES) {
    if (!/from Setup/i.test(piece.fix)) continue
    assert.ok(piece.setupCap,
      `"${piece.label}" sends the user to Setup but names no setupCap to look for`)
    assert.ok(offered.has(piece.setupCap),
      `the strip sends the user to Setup for "${piece.setupCap}" and Setup has no card for it`)
  }
})

test('the strip actually names at least one Setup-installable piece', () => {
  // Guards the test above against silently testing nothing: if no piece said
  // "from Setup" any more, the loop would pass while pinning zero promises.
  assert.ok(VIDEO_PIECES.some((p) => /from Setup/i.test(p.fix)),
    'no strip piece points at Setup — the contract test has gone blind')
})

test('cards are unique per action and carry the fields the page renders', () => {
  const actions = ML_INSTALL_CARDS.map((c) => c.action)
  assert.equal(new Set(actions).size, actions.length, 'duplicate action in ML_INSTALL_CARDS')
  for (const c of ML_INSTALL_CARDS) {
    for (const field of ['action', 'cap', 'icon', 'title', 'body']) {
      assert.ok(c[field], `card ${c.action || '?'} is missing "${field}"`)
    }
  }
})
