import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { installRuntimeHost } from './support/runtimeHost.mjs'
import { setEnabled } from '../src/plugins/registry.js'
import { explicitRunContinuation, localContinuationAvailability, localContinuationRequest } from '../src/components/runs/localContinuation.js'
import { canvasContinueLanes, canvasContinueRequest } from '../../bundled/canvas/frontend/utils/canvasContinue.js'
import { graphContinueRefusal, resolveInitialLane } from '../src/components/dataset/lineageContinue.js'
import { render } from './support/mountJsx.mjs'

const { default: useRunsHubContinue } = await import('../src/components/runs/useRunsHubContinue.js')

test.beforeEach(installRuntimeHost)

const run = { source: 'cloud', record_id: 11, run_id: 7, dataset_id: 3,
  train_type: 'krea', variant: 'base', base_model: '', masked: false,
  resume_checkpoints: [{ step: 100, present: true }, { step: 300, present: true }] }

test('a harvested cloud checkpoint keeps its exact owner with Cloud absent', () => {
  setEnabled([])
  const selected = explicitRunContinuation(run, { lane: 'local', fromStep: 100, expectedRecordId: 999 })
  assert.equal(selected.expectedRecordId, 11)
  assert.equal(selected.fromStep, 100)
  const request = localContinuationRequest(run, { extraSteps: 200, fromStep: 100 })
  assert.equal(request.url, '/api/dataset/3/train/continue')
  assert.equal(request.body.expected_record_id, 11)
  assert.equal(request.body.from_step, 100)
  assert.equal(request.body.masked, false)
  assert.equal(localContinuationAvailability(run, { aitoolkitValid: true }).available, true)
  const node = { ...run, checkpoints: run.resume_checkpoints }
  assert.equal(canvasContinueLanes(node, node.checkpoints[0], { aitoolkitValid: true }).local.available, true)
  assert.equal(canvasContinueRequest(node, { lane: 'local', fromStep: 100 }).body.expected_record_id, 11)
  assert.equal(canvasContinueRequest(node, { lane: 'cloud', fromStep: 100 }), null)
  assert.equal(graphContinueRefusal(node, node.checkpoints[0], {
    steps: [], trainType: 'krea', variant: 'base', base: '',
  }), null, 'the graph addresses this run store even when the local lane holds no same-step save')
  let canContinue
  function Probe() {
    canContinue = useRunsHubContinue({ data: {}, poll: () => {}, cloud: null }).canContinueRun
    return null
  }
  render(Probe)
  assert.equal(canContinue(run), true, 'Runs keeps the local action when Cloud is absent')
  assert.equal(canContinue({ ...run, record_id: null }), false)
  const hook = readFileSync(new URL('../src/components/runs/useRunsHubContinue.js', import.meta.url), 'utf8')
  assert.match(hook, /cloud: remote \|\| \{\s*available: false/,
    'an absent plugin is an explicitly closed lane for the shared dialog')
  assert.equal(resolveInitialLane('cloud', { local: { available: true }, cloud: { available: false } }), 'local')
})

test('cloud local continuation refuses unknown identities, vanished saves and unsupported state', () => {
  for (const patch of [{ record_id: null }, { run_id: null }, { dataset_id: null },
    { dataset_table: 'video_dataset' }, { training_mode: 'full_transformer' }]) {
    assert.equal(explicitRunContinuation({ ...run, ...patch }, { lane: 'local', fromStep: 100 }), null)
  }
  assert.equal(explicitRunContinuation(run, { lane: 'local', fromStep: 999 }), null)
  assert.equal(explicitRunContinuation(run, { lane: 'local', fromStep: 100, resumeMode: 'full_state' }), null)
  const gone = { ...run, resume_checkpoints: [{ step: 100, present: false }] }
  assert.equal(localContinuationRequest(gone, { fromStep: 100 }), null)
  assert.equal(localContinuationAvailability(gone, { aitoolkitValid: true }).available, false)
  assert.equal(localContinuationAvailability(run, { aitoolkitValid: false }).available, false)
  assert.equal(localContinuationAvailability(run, { aitoolkitValid: true, localActive: true }).available, false)
  assert.match(graphContinueRefusal({ ...run, checkpoints: run.resume_checkpoints }, {}, {
    trainType: 'krea', variant: 'base', base: '',
  }), /unavailable/)
})
