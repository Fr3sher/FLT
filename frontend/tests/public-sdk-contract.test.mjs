import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'
import { apiFetch, postJson, postJsonResult, registerPlugin, useToast } from '../../sdk/frontend/runtime.js'
import { checkpointFileLabel } from '../../sdk/frontend/data.js'
import { checkpointFileLabel as publicLabel } from '../src/utils/generatedImageFacts.js'

test('plugin services reject an absent or incompatible host before calling it', t => {
  const before = globalThis.window
  t.after(() => { globalThis.window = before })
  for (const lds of [undefined, { api: 2, sdkVersion: '2.0.0' }, { api: 1, sdkVersion: '1.6.0' },
    { api: 1, sdkVersion: '1.invalid.0' }]) {
    globalThis.window = { lds }
    assert.throws(() => apiFetch('/api/example'), /requires LDS frontend SDK/)
  }
})

test('plugin HTTP envelopes and context values retain host semantics', async t => {
  const before = globalThis.window
  t.after(() => { globalThis.window = before })
  const toast = { success: () => {} }
  const refusal = { ok: false, error: 'not ready', details: { retry: true } }
  const args = []
  globalThis.window = { lds: { api: 1, sdkVersion: '1.15.0',
    postJson: async () => { throw new Error('not ready') },
    postJsonResult: (...values) => { args.push(values); return refusal },
    useToast: () => toast, registerPlugin: () => false,
  } }
  await assert.rejects(postJson('/api/example', {}), /not ready/)
  assert.equal(await postJsonResult('/api/example', { field: 'value' }, true), refusal)
  assert.deepEqual(args, [['/api/example', { field: 'value' }, true]])
  assert.equal(useToast(), toast)
  assert.throws(() => registerPlugin({ id: 'sample.tool' }), /refused the descriptor/)
})

test('stored checkpoint labels preserve public main representations', () => {
  for (const value of [undefined, null, '', 0, 'family/model.safetensors', 'family\\model.ckpt', 'x.bin']) {
    assert.equal(checkpointFileLabel(value), publicLabel(value))
  }
})

test('every exported product descriptor imports with the public SDK and declares no required sibling', async () => {
  const bundled = new URL('../../bundled/', import.meta.url)
  const checked = []
  const fp8HelpOwners = []
  for (const entry of await fs.readdir(bundled, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const root = new URL(entry.name + '/', bundled)
    const manifest = JSON.parse(await fs.readFile(new URL('plugin.json', root), 'utf8'))
    const { default: descriptor } = await import(new URL('frontend/index.js', root).href)
    assert.equal(descriptor.id, manifest.id)
    assert.deepEqual(manifest.requires, [], manifest.id)
    const help = new Set(manifest.owns.help_topics)
    if (help.has('training.fp8_deliver')) fp8HelpOwners.push(manifest.id)
    for (const topic of descriptor.help || []) assert.ok(help.has(topic.id), `${manifest.id}: ${topic.id}`)
    const news = new Set(manifest.owns.whats_new_ids)
    for (const item of descriptor.whatsNew || []) assert.ok(news.has(item.id), `${manifest.id}: ${item.id}`)
    checked.push(manifest.id)
  }
  assert.deepEqual(fp8HelpOwners, ['model_tools'])
  assert.ok(checked.includes('live') && checked.includes('resource_monitor') && checked.includes('civitai_publish'))
})
