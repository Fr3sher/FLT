/**
 * The dense card's verbs — RENDERED. The core's DenseModelsPanel hands this
 * panel its verdict (`denseActions`, the panel's own answer to what an entry
 * allows); the buttons, their refusal and the tools they open are drawn here.
 * Effects never run under renderToStaticMarkup, so the resting state is what
 * is proved — and a ReferenceError in a branch throws here, not on screen.
 */
import assert from 'node:assert/strict'
import nodeTest from 'node:test'
import { existsSync } from 'node:fs'
const hasCloud = existsSync(new URL('../../cloud_training/frontend/dataset/denseModels.js', import.meta.url))
const test = (name, run) => nodeTest(name, { skip: !hasCloud }, run)

import { createElement, renderToStaticMarkup } from '../../../frontend/tests/support/mountJsx.mjs'

const { default: DenseModelTools } = await import('../frontend/panels/DenseModelTools.jsx')
const { denseActions } = hasCloud ? await import('../../cloud_training/frontend/dataset/denseModels.js') : {}

/* A run that delivered to Hugging Face and left nothing here. */
const hubOnly = (hub = {}) => ({
  run_id: 90, dataset_id: 3, train_type: 'krea', variant: 'Raw', steps: 3000,
  active: false, master: null, fp8: null, can_quantize: false, can_delete: false,
  hub: {
    repo_id: 'acme/dense-90', url: 'https://huggingface.co/acme/dense-90',
    status: 'available', weight_filename: 'Krea_full_y.safetensors', ...hub,
  },
})
/* A run whose master is on this disk. */
const onDisk = () => ({
  run_id: 91, dataset_id: 3, train_type: 'krea', variant: 'Raw', steps: 3000,
  active: false, can_quantize: true, can_delete: true, fp8: null,
  master: { path: 'D:\\models\\Krea_full_z.safetensors', filename: 'Krea_full_z.safetensors', size_bytes: 25_600_000_000 },
  hub: null,
})

/* `presence` is THIS card's Hub presence — the panel hands `denseActions` the
   entry's own row of its presence map, the way DenseModelsPanel does. */
const render = (entry, presence = null, busy = false) => renderToStaticMarkup(
  createElement(DenseModelTools, { entry, busy, actions: denseActions(entry, presence) }))

test('a repository measured gone: the button is there, dead, with its reason before the click', () => {
  const html = render(hubOnly(), { state: 'gone' })
  assert.match(html, /Quantize to fp8<\/button>/)
  assert.match(html, /disabled=""/)
  assert.match(html, /the repository it would be downloaded from is gone/)
  // Nothing to merge into: the master is not here.
  assert.doesNotMatch(html, /Merge a LoRA in/)
})

test('an unreachable Hub keeps the button alive: the repository is very probably fine', () => {
  const html = render(hubOnly(), { state: 'unknown' })
  assert.match(html, /Quantize to fp8<\/button>/)
  assert.doesNotMatch(html, /disabled=""/)
})

test('a master on this disk gets both verbs, and the tools stay closed until asked', () => {
  const html = render(onDisk())
  assert.match(html, /✨ Quantize to fp8<\/button>/)
  assert.match(html, /🧬 Merge a LoRA in<\/button>/)
  assert.doesNotMatch(html, /aria-label="Path of the model file to quantize to fp8"/, 'the tool opens on the click')
  assert.doesNotMatch(html, /Hide<\/button>/)
})

test('a busy card disables the verbs; a run still working keeps only the merge; no entry draws nothing', () => {
  assert.equal((render(onDisk(), null, true).match(/disabled=""/g) || []).length, 2)
  // `denseActions` withholds the quantize verb while the run works (its files
  // are not final); the merge reads the master that IS here — the same two
  // rules the core's card applied when it drew these buttons itself.
  const working = render({ ...onDisk(), active: true })
  assert.doesNotMatch(working, /Quantize to fp8/)
  assert.match(working, /Merge a LoRA in<\/button>/)
  assert.equal(render(null), '')
  assert.equal(render(hubOnly({ repo_id: null })), '', 'no master here, no repository: no verb at all')
})
