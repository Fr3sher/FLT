// What the boot loader promises: the runtime an external plugin may use, and
// a plugin list that fails CLOSED. Both were measured wrong by the wave-1
// refutation (2026-09-04): `apiFetch` alone could not POST (no CSRF header),
// and one dropped /api/plugins/ request brought a switched-off plugin back on
// every surface.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { SDK_VERSION } from '../../../sdk/frontend/runtime.js'
import { ENABLED_CACHE_KEY, loadPlugins, publishRuntime } from './loadPlugins.js'
import { contributions, registerDescriptor, resetRegistry } from './registry.js'

const memoryStorage = (initial = {}) => {
  const m = new Map(Object.entries(initial))
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), dump: () => Object.fromEntries(m) }
}

const ok = (payload) => async () => ({ ok: true, json: async () => payload })
const failing = () => async () => { throw new Error('dropped') }
const http503 = () => async () => ({ ok: false, status: 503 })

function withBundledScrape() {
  resetRegistry()
  registerDescriptor({
    id: 'scrape',
    slots: { 'sources.panel': [{ id: 'scan', panel: () => Promise.resolve({ default: () => null }) }] },
  }, { external: false })
}

test('the runtime publishes the CSRF-aware writers, not only apiFetch', () => {
  const win = {}
  const runtime = publishRuntime(win)
  for (const name of ['apiFetch', 'postJson', 'putJson', 'patchJson', 'del', 'postForm', 'registerPlugin', 'React', 'ReactDOM', 'router']) {
    assert.equal(typeof runtime[name], name === 'router' || name === 'React' || name === 'ReactDOM' ? 'object' : 'function', name)
  }
  assert.equal(win.lds, runtime)
})

test('the browser host and distributed SDK advertise the same current version', () => {
  const manifest = JSON.parse(readFileSync(new URL('../../../sdk/frontend/package.json', import.meta.url), 'utf8'))
  const lock = JSON.parse(readFileSync(new URL('../../../sdk/frontend/package-lock.json', import.meta.url), 'utf8'))
  assert.equal(publishRuntime({}).sdkVersion, '1.15.0')
  for (const version of [SDK_VERSION, manifest.version, lock.version, lock.packages[''].version]) {
    assert.equal(version, publishRuntime({}).sdkVersion)
  }
})

test('a successful list is applied and remembered', async () => {
  withBundledScrape()
  const storage = memoryStorage()
  const result = await loadPlugins({
    fetchImpl: ok({ plugins: [{ id: 'scrape', enabled: false, state: 'loaded', bundled: true }] }),
    doc: null, storage, attempts: 1, delayMs: 0,
  })
  assert.deepEqual(result.enabled, [])
  assert.equal(contributions('sources.panel', 'dataset').length, 0, 'a disabled plugin contributes nothing')
  assert.equal(storage.getItem(ENABLED_CACHE_KEY), '[]')
})

test('a reload keeps the actual runtime while a saved disable waits for restart', async () => {
  withBundledScrape()
  const storage = memoryStorage()
  const result = await loadPlugins({
    fetchImpl: ok({ plugins: [{ id: 'scrape', enabled: false, desired_enabled: false, active: true, state: 'loaded', bundled: true }] }),
    doc: null, storage, attempts: 1,
  })
  assert.deepEqual(result.enabled, ['scrape'])
  assert.equal(contributions('sources.panel', 'dataset').length, 1)
  assert.equal(storage.getItem(ENABLED_CACHE_KEY), '["scrape"]')
})

test('a pending enable cannot mount UI before its backend has loaded', async () => {
  withBundledScrape()
  const result = await loadPlugins({
    fetchImpl: ok({ plugins: [{ id: 'scrape', enabled: true, desired_enabled: true, active: false, state: 'disabled', bundled: true }] }),
    doc: null, storage: memoryStorage(), attempts: 1,
  })
  assert.deepEqual(result.enabled, [])
  assert.equal(contributions('sources.panel', 'dataset').length, 0)
})

test('a dropped list keeps plugins off even with a cached disabled set', async () => {
  withBundledScrape()
  const storage = memoryStorage({ [ENABLED_CACHE_KEY]: '[]' })
  const result = await loadPlugins({ fetchImpl: failing(), doc: null, storage, attempts: 2, delayMs: 0 })
  assert.deepEqual(result.enabled, [])
  assert.equal(contributions('sources.panel', 'dataset').length, 0)
  assert.ok(result.failed.some((f) => /confirms the active set/.test(f.why)), JSON.stringify(result.failed))
})

test('a 503 with nothing cached keeps bundled plugins off and reports the unavailable list', async () => {
  withBundledScrape()
  const result = await loadPlugins({ fetchImpl: http503(), doc: null, storage: memoryStorage(), attempts: 1, delayMs: 0 })
  assert.deepEqual(result.enabled, [])
  assert.equal(contributions('sources.panel', 'dataset').length, 0)
  assert.ok(result.failed.some((f) => /confirms the active set/.test(f.why)))
})

test('the list is retried before giving up', async () => {
  withBundledScrape()
  let calls = 0
  const flaky = async () => {
    calls += 1
    if (calls < 3) throw new Error('dropped')
    return { ok: true, json: async () => ({ plugins: [{ id: 'scrape', enabled: true, state: 'loaded', bundled: true }] }) }
  }
  const result = await loadPlugins({ fetchImpl: flaky, doc: null, storage: memoryStorage(), attempts: 3, delayMs: 0 })
  assert.equal(calls, 3)
  assert.deepEqual(result.enabled, ['scrape'])
  assert.equal(result.failed.length, 0)
})
