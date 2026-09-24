import test from 'node:test'
import assert from 'node:assert/strict'
import { loadPlugins, ENABLED_CACHE_KEY } from './loadPlugins.js'
import { contributions, navItems, plugins, registerDescriptor, resetRegistry, routes, setEnabled, whatsNewEntries } from './registry.js'
import { registerBundledPlugins } from './bundled.js'

const snapshot = payload => async () => ({ ok: true, json: async () => payload })
const stored = ids => ({ getItem: key => key === ENABLED_CACHE_KEY ? JSON.stringify(ids) : null, setItem() {} })

function fixture() {
  resetRegistry()
  registerDescriptor({ id: 'example.tools', slots: { 'setup.card': [{ id: 'setup' }] } })
}

for (const storage of [null, stored([]), stored(['example.tools'])]) {
  test(`a missing authoritative list never enables bundled or cached products (${storage ? storage.getItem(ENABLED_CACHE_KEY) : 'no cache'})`, async () => {
    fixture()
    const result = await loadPlugins({ fetchImpl: async () => { throw Error('offline') }, storage, doc: null, attempts: 1 })
    assert.deepEqual(result.enabled, [])
    assert.deepEqual(plugins(), [])
    assert.ok(result.failed.length > 0)
  })
}

test('a fresh load closes the previous enabled set before awaiting the server', async () => {
  fixture()
  setEnabled(['example.tools'])
  let finish
  const pending = new Promise(resolve => { finish = resolve })
  const loading = loadPlugins({ fetchImpl: () => pending, storage: null, doc: null, attempts: 1 })
  assert.deepEqual(plugins(), [])
  finish({ ok: true, json: async () => ({ plugins: [] }) })
  await loading
})

for (const payload of [{}, { plugins: null }, { plugins: [null] }, { plugins: [{ id: 'bad id', active: true }] },
  { plugins: [{ id: 'example.tools', active: true }, { id: 'example.tools', active: true }] }]) {
  test(`a malformed plugin list fails closed with a diagnostic: ${JSON.stringify(payload)}`, async () => {
    fixture()
    const result = await loadPlugins({ fetchImpl: snapshot(payload), storage: null, doc: null, attempts: 1 })
    assert.deepEqual(result.enabled, [])
    assert.deepEqual(plugins(), [])
    assert.ok(result.failed.length)
  })
}

test('a transport that never resolves cannot block boot indefinitely', async () => {
  fixture()
  let calls = 0
  const loading = loadPlugins({ fetchImpl: () => { calls++; return new Promise(() => {}) },
    storage: null, doc: null, attempts: 1, timeoutMs: 5 })
  let timer
  const result = await Promise.race([loading, new Promise(resolve => { timer = setTimeout(() => resolve(null), 100) })])
  clearTimeout(timer)
  assert.notEqual(result, null, 'the list timeout must finish the boot')
  assert.deepEqual(result.enabled, [])
  assert.equal(calls, 1)
})

test('a stylesheet exception is local to its package and does not abort the next one', async (t) => {
  resetRegistry()
  const previous = globalThis.window
  globalThis.window = {}
  t.after(() => { globalThis.window = previous })
  const result = await loadPlugins({
    fetchImpl: snapshot({ plugins: [
      { id: 'example.broken', active: true, schema_version: 2, frontend: '/broken.js' },
      { id: 'example.working', active: true, schema_version: 2, frontend: '/working.js' },
    ] }), storage: null, doc: {}, attempts: 1,
    styleLoader: async () => { throw Error('DOM unavailable') },
    moduleLoader: async () => assert.fail('styles did not load'),
  })
  assert.deepEqual(result.loaded, [])
  assert.deepEqual(result.failed.map(p => p.plugin), ['example.broken', 'example.working'])
})

test('contributions cannot override the identity assigned by their descriptor', () => {
  resetRegistry()
  registerDescriptor({ id: 'example.owner',
    slots: { 'setup.card': [{ id: 'card', plugin: 'another.owner' }] },
    nav: [{ to: '/example', plugin: 'another.owner' }],
    routes: [{ path: '/example', plugin: 'another.owner' }],
    whatsNew: [{ id: 'example-news', plugin: 'another.owner' }],
  })
  setEnabled(['example.owner'])
  for (const values of [contributions('setup.card'), navItems(), routes(), whatsNewEntries()])
    assert.equal(values[0].plugin, 'example.owner')
})

test('the default Store entry registers no development or shipped descriptor', () => {
  resetRegistry()
  assert.deepEqual(registerBundledPlugins(), [])
  assert.deepEqual(plugins(), [])
})
