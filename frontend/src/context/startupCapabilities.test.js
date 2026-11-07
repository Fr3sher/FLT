import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeStartupCapabilities } from './startupCapabilities.js'

const initial = {
  configured: false,
  comfyui: { reachable: false, models: {} },
  aitoolkit: { configured: false, valid: false },
  engines: {},
  masks: false,
  captioners: { joycaption: false },
  training_visible: false,
  studio_visible: false,
}
const startup = {
  configured: true,
  comfyui: { reachable: true, api_url: 'http://localhost:8188' },
  aitoolkit: { configured: true, valid: true },
  training_visible: true,
  studio_visible: true,
}

test('tool presence opens Training and Studio while optional checks stay pending', () => {
  const result = mergeStartupCapabilities(initial, startup, false)
  assert.equal(result.configured, true)
  assert.equal(result.comfyui.reachable, true)
  assert.deepEqual(result.comfyui.models, {})
  assert.equal(result.aitoolkit.valid, true)
  assert.equal(result.training_visible, true)
  assert.equal(result.studio_visible, true)
  assert.deepEqual(result.engines, {})
  assert.equal(result.masks, false)
  assert.equal(result.captioners.joycaption, false)
  assert.equal(initial.comfyui.reachable, false)
})

test('a late startup response never overwrites a complete or forced snapshot', () => {
  const complete = { ...initial, configured: true, engines: { klein: true } }
  assert.equal(mergeStartupCapabilities(complete, startup, true), complete)
})
