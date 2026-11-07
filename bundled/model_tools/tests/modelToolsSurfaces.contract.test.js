import { registerBundledDescriptor } from '../../../frontend/tests/support/bundledDescriptors.mjs'
// The plugin's descriptor and the partition it implies: what moved here is not
// in the core any more, and the core lends exactly the slots it says it does.
import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import descriptor from '../frontend/index.js'
import { resetRegistry, contributions } from '../../../frontend/src/plugins/registry.js'
import { parityGaps, SINGLE_SURFACE_SLOTS } from '../../../frontend/src/plugins/parity.js'
import { STORAGE_GROUPS } from '../../../frontend/src/components/settings/settingsGroups.js'

const here = (rel) => fileURLToPath(new URL(rel, import.meta.url))
const read = (rel) => readFileSync(here(rel), 'utf8')
const core = (rel) => ['components/dataset/DenseModelsPanel.jsx', 'components/dataset/FullTransformerRecipe.jsx'].includes(rel)
  ? (existsSync(here(`../../cloud_training/frontend/dataset/${rel.split('/').pop()}`)) ? read(`../../cloud_training/frontend/dataset/${rel.split('/').pop()}`) : '') : read(`../../../frontend/src/${rel}`)
const back = (rel) => read(`../../../backend/${rel}`)

test('the descriptor contributes the four doors, on the surfaces the core lends', () => {
  resetRegistry()
  assert.ok(registerBundledDescriptor(descriptor))
  assert.equal(contributions('training.tool', 'dataset').length, 1)
  assert.equal(contributions('dense.model.tool', 'dense').length, 1)
  assert.equal(contributions('dense.recipe.tool', 'dense').length, 1)
  assert.equal(SINGLE_SURFACE_SLOTS['dense.model.tool'], 'dense')
  assert.equal(SINGLE_SURFACE_SLOTS['dense.recipe.tool'], 'dense')
  const [group] = contributions('settings.group', 'settings')
  assert.equal(group.section, 'storage')
  assert.equal(group.after, 'models')
  assert.ok(group.keywords.includes('fp8'), 'the product keeps searchable tool vocabulary')
  assert.equal(group.plugin, 'model_tools', 'the generic product page selects this owner')
  assert.deepEqual(contributions('settings.group', 'settings')
    .filter(item => item.plugin === 'model_tools').map(item => item.id), ['model-tools'])
  assert.equal(STORAGE_GROUPS.some(item => item.id === 'model-tools'), false,
    'the product is never an intrinsic general Storage group')
  assert.deepEqual(parityGaps(descriptor), [], 'single-surface slots only: nothing to pair')
  resetRegistry()
})

test('the manifest owns the help topics the descriptor contributes, and the quantize section', () => {
  const manifest = JSON.parse(read('../plugin.json'))
  assert.deepEqual([...manifest.owns.help_topics].sort(), descriptor.help.map((t) => t.id).sort())
  assert.deepEqual(manifest.owns.config_sections, ['quantize'])
  assert.equal(manifest.python_package, 'lds_model_tools')
  assert.equal(manifest.in_process_requirements, false, 'torch belongs to the isolated plugin runtime')
  assert.equal(manifest.requirements, 'requirements-workers.txt')
  assert.equal(manifest.schema_version, 2)
  assert.equal(manifest.compatibility.api, '>=1.15,<2')
  assert.deepEqual(manifest.requires, [])
})

test('the core lends the slots and imports neither tool', () => {
  assert.match(core('components/dataset/TrainingPanel.jsx'),
    /<PluginSlot slot="training\.tool" surface="dataset" family=\{checkpointTrainType\} \/>/)
  if (existsSync(here('../../cloud_training/frontend/dataset/DenseModelsPanel.jsx'))) assert.match(read('../../cloud_training/frontend/dataset/DenseModelsPanel.jsx'),
    /<PluginSlot slot="dense\.model\.tool" surface="dense"\s+entry=\{entry\} busy=\{busy\} actions=\{actions\} \/>/)
  if (existsSync(here('../../cloud_training/frontend/dataset/FullTransformerRecipe.jsx'))) assert.match(read('../../cloud_training/frontend/dataset/FullTransformerRecipe.jsx'),
    /<PluginSlot slot="dense\.recipe\.tool" surface="dense" disabled=\{disabled\} target=\{quantizeTarget\}/)
  assert.doesNotMatch(core('components/settings/StorageSection.jsx'), /withPluginGroups|PluginPanel/)
  assert.match(core('pages/PluginSettingsPage.jsx'), /contributions\('settings\.group', 'settings'\)\.filter\(group => group\.plugin === pluginId\)/)
  assert.match(core('pages/pluginSettingsGroups.jsx'), /<PluginPanel[^>]*importer=\{group\.panel\}/s)
  for (const rel of ['components/dataset/TrainingPanel.jsx', 'components/dataset/DenseModelsPanel.jsx',
    'components/dataset/FullTransformerRecipe.jsx', 'components/settings/StorageSection.jsx',
    'pages/PluginSettingsPage.jsx', 'pages/pluginSettingsGroups.jsx']) {
    assert.doesNotMatch(core(rel), /Fp8QuantizeTool|LoraMergeTool|loraMerge\b/,
      `${rel}: the tool is imported, not lent a slot`)
  }
  for (const gone of ['components/dataset/Fp8QuantizeTool.jsx', 'components/dataset/LoraMergeTool.jsx',
    'components/dataset/loraMerge.js']) {
    assert.ok(!existsSync(here(`../../../frontend/src/${gone}`)), `${gone} is still in the core`)
  }
})

test('the help topics moved out of the core registry', () => {
  const topics = core('help/topics/settingsFields.js') + core('help/topics/workspaceSections.js')
  for (const id of ['storage.fp8_quantize', 'training.fp8_quantize_local', 'workspace-lora-merge']) {
    assert.ok(!topics.includes(`id: '${id}'`), `${id} is still a core topic`)
  }
})

test('the backend mounts the tools through their plugin and retains shared file primitives', () => {
  for (const own of ['fp8_quantize.py', 'lora_merge.py', 'lora_merge_job.py', 'routes.py']) {
    assert.ok(existsSync(here(`../lds_model_tools/${own}`)), `${own} is missing from the plugin`)
  }
  // fp8_export.py stays: the pod runs it, the forecasts read it.
  assert.ok(existsSync(here('../../../backend/app/services/fp8_export.py')))
  const training = back('app/routes/training.py')
  assert.doesNotMatch(training, /tools\/fp8-quantize/)
  assert.doesNotMatch(training, /tools\/fp8-deliver/)
  assert.doesNotMatch(back('app/routes/__init__.py'), /'tools'/)
  assert.match(read('../lds_model_tools/routes.py'), /Blueprint\('model_tools', __name__\)/)
  assert.match(read('../lds_model_tools/__init__.py'), /ctx\.register_blueprint\(bp, url_prefix='\/api'\)/)
})

test('the cloud plugin owns one-click delivery and uses the host converter independently', () => {
  assert.match(read('../../cloud_training/lds_cloud_training/routes.py'),
    /tools\/fp8-deliver\/plan/)
  const delivery = read('../../cloud_training/lds_cloud_training/fp8_local_delivery.py')
  assert.match(delivery,
    /from lds_sdk\.cloud_host\.services import comfy_model_paths, fp8_export, fp8_quantize/)
  assert.doesNotMatch(delivery, /from lds_model_tools|import lds_model_tools/)
  const host = back('lds_sdk/cloud_host/services/__init__.py')
  assert.match(host, /from app\.services import \([\s\S]*\bfp8_quantize,/)
  const manifest = JSON.parse(read('../../cloud_training/plugin.json'))
  assert.ok(!manifest.requires.includes('model_tools'))
})

test('explicit bundled development generates the classes the plugin screens use', async () => {
  // A class only a plugin panel uses would otherwise render unstyled — the
  // markup tests cannot see CSS, so this is pinned at the config: the VALUE
  // the build reads, not a string a comment could satisfy (a refutation
  // finding, 2026-09-05: the glob commented out left this test green).
  const { createTailwindConfig } = await import('../../../frontend/tailwind.config.js')
  const tailwind = createTailwindConfig('bundled')
  assert.ok(Array.isArray(tailwind.content))
  assert.ok(tailwind.content.some((g) => typeof g === 'string' && /bundled\/\*\/frontend\/\*\*/.test(g)),
    `no bundled/*/frontend glob in tailwind content: ${JSON.stringify(tailwind.content)}`)
})
