import assert from 'node:assert/strict'
import test from 'node:test'
import descriptor from '../frontend/index.js'
import { registerBundledDescriptor } from '../../../frontend/tests/support/bundledDescriptors.mjs'
import { resetRegistry, setEnabled, contributions, problems } from '../../../frontend/src/plugins/registry.js'
import { availableImproveEngines, improvementAvailable } from '../../../frontend/src/utils/improveEngines.js'

test('Seed alone owns its setup, settings and engine with no Klein editor', () => {
  resetRegistry()
  assert.equal(registerBundledDescriptor(descriptor), true, JSON.stringify(problems()))
  setEnabled(['seedvr2'])
  assert.deepEqual(availableImproveEngines({ comfyui: { seedvr2_ready: true } }).map(e => e.id), ['seedvr2'])
  assert.equal(improvementAvailable('klein'), false)
  assert.equal(contributions('settings.group').length, 1)
  assert.equal(contributions('setup.card').length, 1)
  assert.equal(contributions('improve.editor').length, 0)
  setEnabled([])
  for (const slot of ['improve.engine', 'settings.group', 'setup.card', 'setup.step']) {
    assert.deepEqual(contributions(slot), [])
  }
  resetRegistry()
})
