// ChatGPT: two lanes, one engine. Setup used to expose only the paid API key,
// so a Plus/Pro subscriber met "OpenAI API key — ○ Not set" and concluded the
// engine costs money. These lock the two facts that fix it: either lane makes
// the engine ready, and the key lane's own state is read from the SECRETS
// payload (engines.chatgpt is the backend's OR of the two and cannot answer
// "is a key also set"). Moved with the lane from the core's useSetupSteps tests.
import test from 'node:test'
import assert from 'node:assert/strict'
import { chatgptLanes, chatgptLaneSummary, CHATGPT_API_KEY_SECRET } from '../frontend/lib/chatgptLanes.js'
import { connectFeedback } from '../frontend/lib/chatgptConnectFeedback.js'

test('a connected subscription makes ChatGPT ready with no API key', () => {
  const l = chatgptLanes(
    { engines: { chatgpt: true }, chatgpt_subscription: { connected: true, email: 'a@b.c' } },
    {})
  assert.equal(l.ready, true)
  assert.equal(l.connected, true)
  assert.equal(l.keySet, false, 'a subscription must not be reported as an API key')
  assert.equal(l.both, false)
  assert.match(chatgptLaneSummary(l), /subscription/i)
  assert.doesNotMatch(chatgptLaneSummary(l), /Set up either one/)
})

test('an API key alone still makes ChatGPT ready', () => {
  const l = chatgptLanes({ engines: { chatgpt: true }, chatgpt_subscription: { connected: false } },
    { [CHATGPT_API_KEY_SECRET]: true })
  assert.equal(l.ready, true)
  assert.equal(l.keySet, true)
  assert.equal(l.connected, false)
  assert.match(chatgptLaneSummary(l), /API key/i)
})

test('neither lane leaves ChatGPT not-ready, and the copy names BOTH ways in', () => {
  const l = chatgptLanes({ engines: { chatgpt: false }, chatgpt_subscription: { connected: false } },
    {})
  assert.equal(l.ready, false)
  const s = chatgptLaneSummary(l)
  assert.match(s, /API key/i)
  assert.match(s, /subscription/i)
})

test('both lanes set up is reported as both, not as a conflict', () => {
  const l = chatgptLanes({ engines: { chatgpt: true }, chatgpt_subscription: { connected: true } },
    { [CHATGPT_API_KEY_SECRET]: true })
  assert.equal(l.both, true)
  assert.match(chatgptLaneSummary(l), /Both lanes/)
})

// A payload from before engines.chatgpt existed must not hide a lane the user can
// SEE is in place — a fresh install polls caps before its first save.
test('a legacy payload without engines still reports a connected subscription ready', () => {
  assert.equal(chatgptLanes({ chatgpt_subscription: { connected: true } }, {}).ready, true)
  assert.equal(chatgptLanes({}, { [CHATGPT_API_KEY_SECRET]: true }).ready, true)
  assert.equal(chatgptLanes(null, null).ready, false)
})

// A wizard that greets a first-time user with a red "✗ Network error" under an
// engine he has not touched reads as a broken app. Errors belong to the action
// that produced them; a state fetch failing on its own must stay off the screen.
test('the subscription row shows an error only when a user action produced it', () => {
  assert.equal(connectFeedback(null), null)
  assert.equal(connectFeedback({ message: 'Network error' }), null,
    'an error with no action behind it reaches the screen')
  assert.equal(connectFeedback({ action: 'connect' }), null)
  assert.equal(connectFeedback({ action: 'connect', message: 'Network error' }), 'Network error')
})
