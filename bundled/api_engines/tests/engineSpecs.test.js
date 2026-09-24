// Plugin-owned catalog facts; host activation/dispatch is tested by the host.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import descriptor from '../frontend/index.js'
import { API_ENGINE_SPECS, chatgptViaSubscription } from '../frontend/lib/engineSpecs.js'

const read = (rel) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8')

test('the three image engines keep their historical ids, credentials and ordering', () => {
  assert.deepEqual(API_ENGINE_SPECS.map(spec => spec.id), ['nanobanana', 'chatgpt', 'openrouter'])
  assert.deepEqual(API_ENGINE_SPECS.map(spec => spec.order), [2, 3, 4])
  assert.deepEqual(API_ENGINE_SPECS.map(spec => spec.secret),
    ['GEMINI_API_KEY', 'OPENAI_API_KEY', 'OPENROUTER_API_KEY'])
  assert.deepEqual(API_ENGINE_SPECS.map(spec => spec.keyTestTarget), ['gemini', 'openai', 'openrouter'])
  for (const spec of API_ENGINE_SPECS) {
    assert.equal(spec.kind, 'api')
    assert.ok(spec.remote && spec.billable)
    assert.equal(typeof spec.card, 'function')
    assert.ok(spec.setupKey && spec.setupRow && spec.modelSettingKey)
    for (const key of ['card', 'title', 'text', 'icon', 'pill', 'dot']) assert.ok(spec.accent[key])
  }
  const python = read('../lds_api_engines/__init__.py')
  for (const spec of API_ENGINE_SPECS) {
    assert.ok(python.includes(`id='${spec.id}'`))
    assert.ok(python.includes(`rate_usd_per_image=${spec.rate}`))
    assert.ok(python.includes(`model_setting_key='${spec.modelSettingKey}'`))
  }
})

test('the subscription cost lane follows the configured authentication mode', () => {
  const connected = { chatgpt_subscription: { connected: true } }
  assert.equal(chatgptViaSubscription({ caps: connected, engineConfig: {} }), true)
  assert.equal(chatgptViaSubscription({ caps: {}, engineConfig: { chatgpt_auth: 'subscription' } }), true)
  assert.equal(chatgptViaSubscription({ caps: connected, engineConfig: { chatgpt_auth: 'api' } }), false)
  assert.equal(chatgptViaSubscription({ caps: {}, engineConfig: {} }), false)
  assert.equal(chatgptViaSubscription(), false)
})

test('manifest, descriptor, news and guide ownership agree', () => {
  const manifest = JSON.parse(read('../plugin.json'))
  assert.equal(descriptor.id, manifest.id)
  assert.deepEqual(manifest.requires, [])
  assert.deepEqual(descriptor.slots['engine.spec'], API_ENGINE_SPECS)
  assert.equal(descriptor.slots['settings.group'].length, 1)
  assert.deepEqual(descriptor.whatsNew.map(entry => entry.id), manifest.owns.whats_new_ids)
  assert.deepEqual(descriptor.guide.sections.map(section => `${section.chapter}#${section.anchor}`),
    manifest.guide_ownership.sections)
  assert.ok(descriptor.guide.sections.every(section => section.markdown.startsWith('## ')))
})

test('the Settings group asks for the same three secrets the specs name', () => {
  const group = read('../frontend/panels/ApiEnginesSettingsGroup.jsx')
  const keys = [...group.matchAll(/\{ key: '([A-Z_]+)', label: '[^']*', testTarget: '(\w+)'/g)]
  assert.deepEqual(keys.map((m) => m[1]), API_ENGINE_SPECS.map((s) => s.secret))
  assert.deepEqual(keys.map((m) => m[2]), API_ENGINE_SPECS.map((s) => s.keyTestTarget))
})

test('the manifest owns the help topics the descriptor contributes', () => {
  const manifest = JSON.parse(read('../plugin.json'))
  assert.deepEqual([...manifest.owns.help_topics].sort(), descriptor.help.map((t) => t.id).sort())
  assert.deepEqual([...manifest.owns.engines].sort(), API_ENGINE_SPECS.map((s) => s.id).sort())
})
