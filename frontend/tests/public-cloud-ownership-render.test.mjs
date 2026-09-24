import assert from 'node:assert/strict'
import test from 'node:test'
import { createElement, renderToStaticMarkup } from './support/mountJsx.mjs'
import { readSource } from './support/readSource.mjs'

const { MemoryRouter } = await import('react-router')
const { renderToReadableStream } = await import('react-dom/server')
const { ToastProvider } = await import('../src/components/common/Toast.jsx')
const { configureHostRuntime } = await import('../src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../src/plugins/loadPlugins.js')
const { registerDescriptor, resetRegistry, setEnabled, contributions } = await import('../src/plugins/registry.js')
const { default: CloudSignupNote } = await import('../../bundled/cloud_training/frontend/setup/CloudSignupNote.jsx')
const { default: DenseModelsPanel } = await import('../../bundled/cloud_training/frontend/dataset/DenseModelsPanel.jsx')
const { FullTransformerAdvancedRecipe } = await import('../../bundled/cloud_training/frontend/dataset/FullTransformerRecipe.jsx')
const { default: modelTools } = await import('../../bundled/model_tools/frontend/index.js')
const modelManifest = JSON.parse(readSource('../bundled/model_tools/plugin.json'))

const wrap = (Component, props) => createElement(MemoryRouter, null,
  createElement(ToastProvider, null, createElement(Component, props)))
const render = (Component, props) => renderToStaticMarkup(wrap(Component, props))
const renderLoaded = async (Component, props) => {
  const stream = await renderToReadableStream(wrap(Component, props))
  await stream.allReady
  return new Response(stream).text()
}
const model = { run_id: 1, train_type: 'krea', variant: 'Raw', can_quantize: true,
  master: { path: 'X:/fixtures/model.safetensors', filename: 'model.safetensors', size_bytes: 1024 } }
const props = { datasetId: 1, models: [model] }

test.beforeEach(t => {
  const saved = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch }
  t.after(() => { Object.assign(globalThis, saved); resetRegistry() })
  globalThis.window = {}
  globalThis.document = { cookie: '', querySelector: () => null }
  globalThis.fetch = () => { throw new Error('Rendering must not contact any service') }
  resetRegistry()
  setEnabled([])
  configureHostRuntime()
  publishRuntime()
})

test('Cloud signup reads the host referral through the existing links contract', () => {
  const html = render(CloudSignupNote)
  assert.match(html, /cloud\.vast\.ai/)
  assert.match(html, new RegExp(`ref_id=${window.lds.links.vastReferralId}`))
})

test('Cloud full models and recipe load with Model Tools absent', () => {
  assert.deepEqual(contributions('dense.model.tool', 'dense'), [])
  const html = render(DenseModelsPanel, props)
  assert.match(html, /Full models/)
  assert.match(html, /model\.safetensors/)
  assert.doesNotMatch(html, /<button[^>]*>[^<]*(?:Quantize|Merge)/)
  const recipe = render(FullTransformerAdvancedRecipe, {})
  assert.doesNotMatch(recipe, /Quantize a model to fp8/)
})

test('Model Tools owns both optional dense surfaces and disables without breaking Cloud', async () => {
  assert.equal(registerDescriptor(modelTools, { guideOwnership: modelManifest.guide_ownership }), true)
  setEnabled(['model_tools'])
  const html = await renderLoaded(DenseModelsPanel, props)
  assert.match(html, /Quantize to fp8/)
  assert.match(html, /Merge a LoRA in/)
  const recipe = await renderLoaded(FullTransformerAdvancedRecipe, {})
  assert.match(recipe, /Quantize a model to fp8/)
  setEnabled([])
  const disabled = render(DenseModelsPanel, props)
  assert.match(disabled, /Full models/)
  assert.doesNotMatch(disabled, /<button[^>]*>[^<]*(?:Quantize|Merge)/)
})
