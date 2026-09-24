import { registerBundledDescriptor } from '../../../frontend/tests/support/bundledDescriptors.mjs'
/**
 * The fp8 quantize tool has FOUR doors and must stay ONE implementation.
 *
 * It shipped reachable from a single place: the full-model recipe card, which
 * only exists inside a dense dataset. Someone who downloaded a 26 GB model from
 * Hugging Face — the person the tool was written for — has no dataset and never
 * saw it. Model tools settings is the findable door; each delivered full model's
 * card is the third; since the tool became the `model_tools` plugin's, every
 * door is a slot the core lends and the plugin fills.
 *
 * The failure this file exists to prevent is not "a door is missing": it is
 * the SECOND implementation. Copying the JSX into a host would look identical
 * on the day it lands and would then drift — the refusals (already quantized,
 * LoRA, overwriting the source) and the read-back verification live in the
 * component, so a copy is a second set of them. So the census below pins that
 * exactly one file talks to the endpoints, and the host assertions pin that
 * every door lends a slot rather than drawing a lookalike.
 */
import assert from 'node:assert/strict'
import test from 'node:test'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { createElement, renderToStaticMarkup } from '../../../frontend/tests/support/mountJsx.mjs'
import descriptor from '../frontend/index.js'
import { resetRegistry } from '../../../frontend/src/plugins/registry.js'

/* ⚠️ Dynamic — the hooks that teach Node to read .jsx are installed while
   mountJsx.mjs is evaluated, and a static import would already be linked. */
const { configureHostRuntime } = await import('../../../frontend/src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../../../frontend/src/plugins/loadPlugins.js')
globalThis.window = {}
configureHostRuntime()
publishRuntime()

const { default: Fp8QuantizeTool } = await import('../frontend/panels/Fp8QuantizeTool.jsx')
const { default: StorageQuantizeGroup } = await import('../frontend/panels/StorageQuantizeGroup.jsx')
const { allHelpTopics, getHelpTopic, searchHelpTopics } =
  await import('../../../frontend/src/help/helpRegistry.js')

const here = (rel) => fileURLToPath(new URL(rel, import.meta.url))
const read = (rel) => readFileSync(here(rel), 'utf8')

// Every .js/.jsx under a root, with its path — the endpoint census needs names.
const walk = (dirUrl) => {
  const out = []
  for (const entry of readdirSync(dirUrl, { withFileTypes: true })) {
    const child = new URL(`${entry.name}${entry.isDirectory() ? '/' : ''}`, dirUrl)
    if (entry.isDirectory()) out.push(...walk(child))
    else if (/\.jsx?$/.test(entry.name) && !/\.test\.jsx?$/.test(entry.name)) {
      out.push([fileURLToPath(child), readFileSync(fileURLToPath(child), 'utf8')])
    }
  }
  return out
}
const CORE_FILES = walk(new URL('../../../frontend/src/', import.meta.url))
const PLUGIN_FILES = walk(new URL('../frontend/', import.meta.url))
const rel = (path) => path.replace(/\\/g, '/').split(/\/(?:frontend\/src|bundled)\//)[1]

// ---- one implementation ----------------------------------------------------

test('exactly one component talks to the quantize endpoints', () => {
  // `/api/tools/fp8-deliver` is the endpoint that can also FETCH a master that
  // is not on this machine and place the result in ComfyUI's own folder (the
  // Cloud training extension). The same component uses this plugin's local
  // `/api/tools/fp8-quantize` service when that extension is absent. Both reuse
  // the same server guards; another component would duplicate the UI.
  const callers = [...CORE_FILES, ...PLUGIN_FILES]
    .filter(([, src]) => src.includes('/api/tools/fp8-deliver'))
    .map(([path]) => rel(path))
  assert.deepEqual(callers, ['model_tools/frontend/panels/Fp8QuantizeTool.jsx'],
    'a second file calling the quantize endpoints means the tool was copied, not reused')
  const local = [...CORE_FILES, ...PLUGIN_FILES]
    .filter(([, src]) => src.includes('/api/tools/fp8-quantize'))
    .map(([path]) => rel(path))
  assert.deepEqual(local, callers)
})

test('every door lends a slot to the shared component instead of drawing its own controls', () => {
  const core = (p) => ['components/dataset/FullTransformerRecipe.jsx', 'components/dataset/DenseModelsPanel.jsx'].includes(p)
    ? (existsSync(here(`../../cloud_training/frontend/dataset/${p.split('/').pop()}`)) ? read(`../../cloud_training/frontend/dataset/${p.split('/').pop()}`) : '')
    : read(`../../../frontend/src/${p}`)
  if (existsSync(here('../../cloud_training/frontend/dataset/FullTransformerRecipe.jsx'))) assert.match(read('../../cloud_training/frontend/dataset/FullTransformerRecipe.jsx'), /<PluginSlot slot="dense\.recipe\.tool"/)
  if (existsSync(here('../../cloud_training/frontend/dataset/DenseModelsPanel.jsx'))) assert.match(read('../../cloud_training/frontend/dataset/DenseModelsPanel.jsx'), /<PluginSlot slot="dense\.model\.tool"/)
  assert.doesNotMatch(core('components/settings/StorageSection.jsx'), /withPluginGroups|PluginPanel/)
  assert.match(core('pages/PluginSettingsPage.jsx'), /contributions\('settings\.group', 'settings'\)\.filter\(group => group\.plugin === pluginId\)/)
  assert.match(core('pages/pluginSettingsGroups.jsx'), /<PluginPanel[^>]*importer=\{group\.panel\}/s)
  for (const p of ['components/dataset/FullTransformerRecipe.jsx', 'components/dataset/DenseModelsPanel.jsx',
    'components/settings/StorageSection.jsx', 'pages/PluginSettingsPage.jsx', 'pages/pluginSettingsGroups.jsx']) {
    assert.doesNotMatch(core(p), /Fp8QuantizeTool/, `${p}: imports the tool instead of lending a slot`)
  }
  // …and the descriptor fills them, with the one component.
  const doors = [
    ...descriptor.slots['dense.recipe.tool'], ...descriptor.slots['dense.model.tool'],
    ...descriptor.slots['settings.group'],
  ]
  assert.equal(doors.length, 3)
  for (const door of doors) assert.equal(typeof door.panel, 'function', `${door.id}: no panel`)
  assert.match(read('../frontend/panels/StorageQuantizeGroup.jsx'), /<Fp8QuantizeTool framed=\{false\} \/>/)
  assert.match(read('../frontend/panels/DenseModelTools.jsx'), /<Fp8QuantizeTool framed=\{false\} manualPath=\{false\}/)
})

test('no poller in the plugin treats apiFetch as if it resolved a Response', () => {
  // The core's census (fp8-one-click-contract) stops at frontend/src; the
  // plugin's own pollers get the same rule here.
  const offenders = PLUGIN_FILES
    .filter(([, src]) => /apiFetch\([^)]*\)[\s\S]{0,120}?\.then\(\s*\(?\w+\)?\s*=>\s*\w+\.json\(\)/.test(src))
    .map(([path]) => rel(path))
  assert.deepEqual(offenders, [])
})

// ---- the tool renders in both chromes --------------------------------------

const CONTROLS = [
  /aria-label="Path of the model file to quantize to fp8"/,
  /Quantize to fp8<\/button>/,
]

test('the recipe-card door keeps its accent frame and its own title', () => {
  const html = renderToStaticMarkup(createElement(Fp8QuantizeTool, {}))
  assert.match(html, /bg-sky-400\/10/)
  // "an EXISTING model" was dropped from the title with the words "on this
  // machine" from the blurb: the block now also reaches a master that only
  // exists in a private Hugging Face repo, which is the whole point.
  assert.match(html, /Quantize a model to fp8/)
  assert.doesNotMatch(html, /on this machine into/)
  for (const re of CONTROLS) assert.match(html, re)
})

test('the Settings door drops only the chrome — every control survives', () => {
  const html = renderToStaticMarkup(createElement(Fp8QuantizeTool, { framed: false }))
  // The Card around it already carries the title and the one-sentence what/when,
  // so saying them again inside is the only thing framed={false} removes.
  assert.doesNotMatch(html, /bg-sky-400\/10/)
  assert.doesNotMatch(html, /not the same thing as the/)
  for (const re of CONTROLS) assert.match(html, re)
})

test('a disabled tool disables both controls in either chrome', () => {
  for (const framed of [true, false]) {
    const html = renderToStaticMarkup(createElement(Fp8QuantizeTool, { framed, disabled: true }))
    assert.equal((html.match(/disabled=""/g) || []).length, 2,
      `framed=${framed}: the path field and the button must both be disabled`)
  }
})

// ---- the Settings door renders --------------------------------------------

test('the Model tools settings group renders its tool and retains the historical focus target', () => {
  // The group's body, as the section mounts it (the section's prop bag is
  // passed and ignored). The whole tab is the core's render test's.
  const html = renderToStaticMarkup(createElement(StorageQuantizeGroup, { config: {}, setField: () => {} }))
  assert.match(html, /id="storage-fp8-quantize"/)
  assert.match(html, /Quantize an existing model to fp8/)
  for (const re of CONTROLS) assert.match(html, re)
})

// ---- the door is addressable ----------------------------------------------

test('the Settings door has its own help topic, pointing at that focus id', () => {
  resetRegistry()
  assert.ok(registerBundledDescriptor(descriptor))
  try {
    const topic = getHelpTopic('storage.fp8_quantize')
    assert.ok(topic, 'no help topic for the Model tools settings door')
    assert.equal(topic.app.route, '/plugins/model_tools/settings')
    assert.equal(topic.app.legacyRoute, '/settings/storage')
    assert.equal(topic.app.focus, 'storage-fp8-quantize')
    // Two doors, two topics, two distinct titles — a search result that reads the
    // same twice cannot tell you which screen you are being sent to.
    const other = getHelpTopic('training.fp8_quantize_local')
    assert.ok(other && other.title !== topic.title)
    assert.equal(allHelpTopics().filter((t) => t.app.route === '/plugins/model_tools/settings'
      && t.app.focus === 'storage-fp8-quantize').length, 1)
    // A second door nobody can search for is not a second door. These are the
    // terms of the problem as it is felt ("this file is too big"), not the terms
    // of the solution — which is the vocabulary the person who never opened a
    // dense dataset actually has.
    for (const query of ['quantize', 'fp8', 'shrink', 'smaller', 'comfyui', 'safetensors']) {
      assert.ok(searchHelpTopics(query).some((t) => t.id === 'storage.fp8_quantize'),
        `"${query}" does not surface the Model tools settings door`)
    }
  } finally {
    resetRegistry()
  }
})

test('with the plugin off, the topics are gone with the doors', () => {
  resetRegistry()
  assert.equal(getHelpTopic('storage.fp8_quantize'), undefined)
  assert.equal(getHelpTopic('workspace-lora-merge'), undefined)
})
