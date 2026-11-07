import assert from 'node:assert/strict'
import test from 'node:test'
import klein from '../frontend/index.js'
import { registerBundledDescriptor } from '../../../frontend/tests/support/bundledDescriptors.mjs'
import { resetRegistry, problems, setEnabled, contributions } from '../../../frontend/src/plugins/registry.js'
import { availableImproveEngines, improveEngine, improvementAvailable } from '../../../frontend/src/utils/improveEngines.js'

test('independent products contribute only their own complete engine experience', () => {
  resetRegistry()
  assert.equal(registerBundledDescriptor(klein), true, JSON.stringify(problems()))
  for (const [ids, engines] of [[[], []], [['image_upscale'], ['klein']]]) {
    setEnabled(ids)
    assert.deepEqual(availableImproveEngines({ comfyui: { seedvr2_ready: true } }).map(x => x.id), engines)
    assert.equal(improvementAvailable(), engines.length > 0)
    assert.equal(improvementAvailable('klein'), engines.includes('klein'))
    assert.equal(contributions('improve.editor').length, engines.includes('klein') ? 1 : 0)
    assert.equal(contributions('setup.card').length, 0)
    assert.equal(contributions('settings.group').length, engines.length)
  }
  assert.equal(improveEngine('seedvr2').label, 'SeedVR2')
  resetRegistry()
})
