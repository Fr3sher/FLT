import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import descriptor from '../../bundled/qwen_dataset/frontend/index.js'
import apiEngines from '../../bundled/api_engines/frontend/index.js'
import { modelPreparationRows, qwenUnavailableReason } from '../../bundled/qwen_dataset/frontend/lib/engine.js'
import { registerDescriptor, resetRegistry, setEnabled } from '../src/plugins/registry.js'
import { engineIds, localEngineIds, pluginEngineSpecs } from '../src/engines/catalog.js'
import { editEngines, defaultEditEngine } from '../src/components/dataset/referenceEdit.js'

const ownership = JSON.parse(readFileSync(new URL('../../bundled/qwen_dataset/plugin.json', import.meta.url), 'utf8')).guide_ownership
const apiOwnership = JSON.parse(readFileSync(new URL('../../bundled/api_engines/plugin.json', import.meta.url), 'utf8')).guide_ownership

test.afterEach(() => resetRegistry())

test('Qwen participates in local generation only while its plugin is enabled', () => {
  resetRegistry()
  assert.equal(registerDescriptor(descriptor, { guideOwnership: ownership }), true)
  setEnabled(['qwen_dataset'])
  assert.deepEqual(engineIds(), ['klein', 'krea', 'qwen_dataset'])
  assert.ok(localEngineIds().includes('qwen_dataset'))
  assert.deepEqual(pluginEngineSpecs().map(spec => spec.id), ['qwen_dataset'])
  assert.equal(pluginEngineSpecs()[0].remote, false)
  assert.equal(editEngines().includes('qwen_dataset'), false)
  const storage = { getItem: key => key === 'datasetGenerators' ? '["qwen_dataset"]' : null }
  assert.notEqual(defaultEditEngine(storage), 'qwen_dataset')
  setEnabled([])
  assert.equal(engineIds().includes('qwen_dataset'), false)
  assert.deepEqual(pluginEngineSpecs(), [])
})

test('preparation does not report unknown or invalid models as present', () => {
  assert.ok(modelPreparationRows({ comfyui: { dir_valid: true } }).every(row => !row.present && row.available))
  const rows = modelPreparationRows({ comfyui: { dir_valid: true }, qwen_dataset: {
    missing: ['qwen_dataset_text_encoder'], invalid: ['qwen_dataset_vae'],
    models: { unet: 'qwen_image_2.1_int8_convrot.safetensors', vae: 'qwen_image_2.1_vae_bf16.safetensors' },
  } })
  assert.deepEqual(rows.map(row => row.present), [true, false, false])
  assert.ok(modelPreparationRows({}).every(row => !row.available))
  assert.ok(modelPreparationRows({ qwen_dataset: { ok: false, detail: 'Probe failed.' } }).every(row => !row.present))
})

test('Qwen sits beside Klein and Krea before the installed API cards', () => {
  resetRegistry()
  assert.equal(registerDescriptor(apiEngines, { guideOwnership: apiOwnership }), true)
  assert.equal(registerDescriptor(descriptor, { guideOwnership: ownership }), true)
  setEnabled(['api_engines', 'qwen_dataset'])
  assert.deepEqual(engineIds().slice(0, 4), ['klein', 'krea', 'qwen_dataset', 'nanobanana'])
  assert.deepEqual(pluginEngineSpecs().map(spec => spec.id), ['qwen_dataset', 'nanobanana', 'chatgpt', 'openrouter'])
})

test('unavailable hints distinguish disabled engine, stopped ComfyUI and missing nodes or weights', () => {
  assert.match(qwenUnavailableReason({}, false), /Enable/)
  assert.match(qwenUnavailableReason({}), /Start ComfyUI/)
  assert.match(qwenUnavailableReason({ comfyui: { reachable: true }, qwen_dataset: { missing_nodes: ['TextEncodeQwenImage21'] } }), /Update ComfyUI/)
  assert.match(qwenUnavailableReason({ comfyui: { reachable: true }, qwen_dataset: { missing: ['qwen_dataset_model'] } }), /Prepare the Qwen model files/)
})
