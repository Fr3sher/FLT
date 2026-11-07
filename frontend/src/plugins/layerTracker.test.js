import test from 'node:test'
import assert from 'node:assert/strict'
import { contributionKey, createLayerTracker } from './layerTracker.js'

// The refutation's sequence, replayed on the tracker: contribution A opens its
// picker, the host re-renders and contribution B's effect reports "closed" —
// with one flag for the slot, B's report erased A's open layer and the host's
// arrows walked the list under the picker.
test('a second contribution reporting closed does not close the first one\'s layer', () => {
  const t = createLayerTracker()
  const a = t.onLayerFor('camera_angles:camera')
  const b = t.onLayerFor('civitai_publish:civitai')
  a(true)
  assert.equal(t.any(), true)
  b(false)                       // the host re-rendered, B's effect replayed with open=false
  assert.equal(t.any(), true, 'B closed nothing of its own; A\'s picker is still on screen')
  assert.deepEqual(t.openKeys(), ['camera_angles:camera'])
  a(false)
  assert.equal(t.any(), false)
})

test('the callback of one contribution is stable, so a panel effect keyed on it does not churn', () => {
  const t = createLayerTracker()
  assert.equal(t.onLayerFor('p:x'), t.onLayerFor('p:x'))
  assert.notEqual(t.onLayerFor('p:x'), t.onLayerFor('p:y'))
})

test('onChange fires on the transitions only — the host re-renders for a change of truth, not per report', () => {
  const seen = []
  const t = createLayerTracker((any) => seen.push(any))
  const a = t.onLayerFor('a')
  const b = t.onLayerFor('b')
  a(true); a(true); b(true); b(false); a(false)
  assert.deepEqual(seen, [true, false])
  t.reset()
  assert.deepEqual(seen, [true, false], 'a reset with nothing open announces nothing')
  a(true); t.reset()
  assert.deepEqual(seen, [true, false, true, false])
})

test('the key of a contribution is its plugin and its id', () => {
  assert.equal(contributionKey({ plugin: 'civitai_publish', id: 'civitai' }), 'civitai_publish:civitai')
})
