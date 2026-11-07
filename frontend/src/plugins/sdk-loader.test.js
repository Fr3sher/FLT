import assert from 'node:assert/strict'
import test from 'node:test'
import { loadPlugins, publishRuntime } from './loadPlugins.js'
import { plugins, resetRegistry } from './registry.js'
import { loadPluginStyles } from './styles.js'

const entry = { id: 'camera_angles', active: true, official: true, schema_version: 2,
  frontend: '/api/plugins/camera_angles/ui/boot/one/index.js', styles: ['/api/plugins/camera_angles/ui/boot/one/styles.css'] }
const descriptor = { id: 'camera_angles', slots: { 'setup.card': [{ id: 'camera', panel: async () => ({ default: () => null }) }] } }

async function run(t, override = {}, options = {}) {
  resetRegistry()
  const before = globalThis.window
  globalThis.window = {}
  t.after(() => { globalThis.window = before })
  return loadPlugins({
    fetchImpl: async () => ({ ok: true, json: async () => ({ plugins: [{ ...entry, ...override }] }) }),
    attempts: 1, storage: null, doc: {},
    styleLoader: async () => ({ ok: true }),
    moduleLoader: async () => { globalThis.window.lds.registerPlugin(descriptor); return { ok: true } },
    ...options,
  })
}

test('verified official package mounts only after its styles are ready', async (t) => {
  const order = []
  const result = await run(t, {}, {
    styleLoader: async (urls) => { assert.deepEqual(urls, entry.styles); order.push('css'); return { ok: true } },
    moduleLoader: async () => { order.push('js'); assert.equal(globalThis.window.lds.registerPlugin(descriptor), true); return { ok: true } },
  })
  assert.deepEqual(order, ['css', 'js'])
  assert.deepEqual(result.loaded, ['camera_angles'])
  assert.equal(plugins().length, 1)
})

test('stylesheet failure refuses a package before any code is evaluated', async (t) => {
  const result = await run(t, {}, {
    styleLoader: async () => ({ ok: false, why: 'failed to load' }),
    moduleLoader: async () => { assert.fail('module must not run') },
  })
  assert.match(result.failed[0].why, /Stylesheet failed/)
  assert.equal(plugins().length, 0)
})

test('OFF package loads neither stylesheet nor module', async (t) => {
  const result = await run(t, { active: false }, {
    styleLoader: async () => { assert.fail('stylesheet must not load') },
    moduleLoader: async () => { assert.fail('module must not load') },
  })
  assert.deepEqual(result.loaded, [])
  assert.equal(plugins().length, 0)
})

test('a self-declared official descriptor cannot claim a reserved short id', async (t) => {
  let accepted
  const result = await run(t, { official: false }, {
    moduleLoader: async () => {
      accepted = globalThis.window.lds.registerPlugin({ ...descriptor, official: true })
      return { ok: true }
    },
  })
  assert.equal(accepted, false)
  assert.equal(result.loaded.length, 0)
  assert.equal(plugins().length, 0)
})

test('descriptor must match the exact plugin being loaded, and the window closes afterwards', async (t) => {
  const result = await run(t, {}, {
    moduleLoader: async () => {
      assert.equal(globalThis.window.lds.registerPlugin({ id: 'video' }), false)
      return { ok: true }
    },
  })
  assert.match(result.failed[0].why, /does not match/)
  assert.equal(plugins().length, 0)
  assert.equal(publishRuntime().registerPlugin(descriptor), false)
})

test('a failed or duplicate registration leaves no partial contributions', async (t) => {
  const result = await run(t, {}, {
    moduleLoader: async () => {
      assert.equal(globalThis.window.lds.registerPlugin(descriptor), true)
      assert.equal(globalThis.window.lds.registerPlugin(descriptor), false)
      return { ok: true }
    },
  })
  assert.equal(result.loaded.length, 0)
  assert.equal(plugins().length, 0)
})

test('an SDK module without its descriptor is diagnosed', async (t) => {
  let removed = false
  const result = await run(t, {}, {
    styleLoader: async () => ({ ok: true, remove: () => { removed = true } }),
    moduleLoader: async () => ({ ok: true }),
  })
  assert.match(result.failed[0].why, /did not register/)
  assert.equal(removed, true, 'failed packages leave no stylesheet behind')
})

test('styles await load, retry a failure and deduplicate successful URLs', async () => {
  const elements = []
  const doc = { createElement: () => ({ remove() {} }), head: { appendChild: (node) => elements.push(node) } }
  const first = loadPluginStyles(['/first.css'], 1000, doc)
  assert.equal(elements.length, 1)
  elements[0].onerror()
  assert.equal((await first).ok, false)
  const second = loadPluginStyles(['/first.css'], 1000, doc)
  assert.equal(elements.length, 2)
  elements[1].onload()
  assert.equal((await second).ok, true)
  assert.equal((await loadPluginStyles(['/first.css'], 1000, doc)).ok, true)
  assert.equal(elements.length, 2)
})
