import assert from 'node:assert/strict'
import test from 'node:test'
import {
  SEEDVR2_ACTIONS, seedvr2InstallPlan, seedvr2NeedsComfyuiRestart, catalog,
  seedvr2PreparationPlan, seedvr2PreparationState, seedvr2PreparationError,
} from '../frontend/lib/setup.js'

test('preparation includes the node pack and the missing or broken models only', () => {
  const caps = { comfyui: { dir_valid: true, seedvr2_nodes_installed: false,
    seedvr2_missing: ['seedvr2_model'], seedvr2_invalid: [{ asset: 'seedvr2_vae', blocking: true }] } }
  assert.deepEqual(seedvr2InstallPlan(caps), SEEDVR2_ACTIONS)
  assert.deepEqual(catalog(caps).map(item => item.present), [false, false, false])
  assert.deepEqual(seedvr2InstallPlan({}), [])
})

test('a pack on disk with absent live classes asks for restart and no reinstall', () => {
  const caps = { comfyui: { dir_valid: true, seedvr2_nodes_installed: true, seedvr2_nodes_missing: ['SeedVR2'],
    seedvr2_missing: [], seedvr2_ready: false } }
  assert.deepEqual(seedvr2InstallPlan(caps), [])
  assert.equal(seedvr2NeedsComfyuiRestart(caps), true)
  assert.equal(catalog(caps)[0].present, true)
})

test('live classes from another ComfyUI Manager folder do not require another node pack', () => {
  const caps = { comfyui: { dir_valid: true, reachable: true, seedvr2_nodes_installed: false,
    seedvr2_nodes_missing: [], seedvr2_missing: ['seedvr2_model'], seedvr2_ready: false } }
  assert.deepEqual(seedvr2InstallPlan(caps), ['seedvr2_model'])
  assert.deepEqual(catalog(caps).map(item => item.present), [true, false, true])
  assert.equal(seedvr2NeedsComfyuiRestart(caps), false)
  caps.comfyui.seedvr2_missing = []
  assert.deepEqual(seedvr2InstallPlan(caps), [])
  caps.comfyui.reachable = false
  assert.deepEqual(seedvr2InstallPlan(caps), ['seedvr2_nodes'])
})

test('only a complete server plan is accepted, including an empty plan', () => {
  assert.deepEqual(seedvr2PreparationPlan([]), [])
  assert.deepEqual(seedvr2PreparationPlan(['seedvr2_vae']), ['seedvr2_vae'])
  for (const value of [null, {}, ['other_plugin'], ['seedvr2_vae', 'seedvr2_vae']]) {
    assert.throws(() => seedvr2PreparationPlan(value), /could not be read/)
  }
})

test('errors stop tracking immediately, while empty plans settle without inventing readiness', () => {
  assert.equal(seedvr2PreparationState([], {}), 'prepared')
  assert.equal(seedvr2PreparationState(SEEDVR2_ACTIONS, { seedvr2_nodes: { state: 'error' }, seedvr2_model: { state: 'running' } }), 'error')
  assert.equal(seedvr2PreparationState(['seedvr2_vae'], {}), 'unavailable')
  assert.equal(seedvr2PreparationState(['seedvr2_vae'], { seedvr2_vae: { state: 'running' } }), 'running')
  assert.match(seedvr2PreparationError(['seedvr2_nodes'], { seedvr2_nodes: {
    state: 'error', log: ['ComfyUI uses Python 3.11; this node recipe requires Python >=3.12.'] } }), /Python >=3.12/)
})
