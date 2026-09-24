import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { createElement, renderToStaticMarkup } from './support/mountJsx.mjs'
import { resetRegistry, registerDescriptor, setEnabled, contributions } from '../src/plugins/registry.js'
import { engineIds, engineLabel } from '../src/engines/catalog.js'
import { canonicalEngines, readEngines, writeEngines, STORAGE_ENGINES } from '../src/components/dataset/engineSelection.js'
import { settingsApiUrl, pluginSettingsAvailability, settingsPatch, reconcileSettings } from '../src/pages/pluginSettings.js'
import { preparationState, startPreparation, watchPreparation } from '../src/pages/store/preparation.js'
import { isDatasetImportBlocked, isStopGenerationBlocked } from '../src/components/dataset/activityGates.js'

const { MemoryRouter } = await import('react-router')
const { ToastProvider } = await import('../src/components/common/Toast.jsx')
const { CapabilitiesProvider } = await import('../src/context/CapabilitiesContext.jsx')
const { default: SetupStart } = await import('../src/components/setup/SetupStart.jsx')
const { default: StudioPage } = await import('../src/pages/StudioPage.jsx')
const { default: UnavailablePluginPage } = await import('../src/pages/UnavailablePluginPage.jsx')
const { default: PluginPreparation } = await import('../src/pages/store/PluginPreparation.jsx')
const { completeCoreSetup } = await import('../src/components/setup/completeCoreSetup.js')

const mount = (Component, props = {}, route = '/') => renderToStaticMarkup(createElement(MemoryRouter, { initialEntries: [route] },
  createElement(ToastProvider, null, createElement(CapabilitiesProvider, null, createElement(Component, props)))))
test.beforeEach(t => {
  const saved = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch,
    localStorage: globalThis.localStorage, sessionStorage: globalThis.sessionStorage }
  t.after(() => Object.assign(globalThis, saved))
  const data = new Map()
  const storage = { getItem: key => data.get(key) || null, setItem: (key, value) => data.set(key, value), removeItem: key => data.delete(key) }
  globalThis.localStorage = storage; globalThis.sessionStorage = storage
  globalThis.window = { localStorage: storage }
  globalThis.document = { cookie: 'csrf_token=fixture', querySelector: () => null }
  globalThis.fetch = () => { throw new Error('Unexpected request in neutral render') }
  resetRegistry(); setEnabled([])
})

test('zero plugins exposes the two public local engines and no product contribution', () => {
  assert.deepEqual(engineIds(), ['klein', 'krea'])
  for (const slot of ['studio.tab', 'engine.spec', 'improve.engine', 'training.launch', 'settings.group']) assert.deepEqual(contributions(slot), [])
  assert.deepEqual(canonicalEngines(['nanobanana', 'klein']), ['klein'])
  assert.equal(engineLabel('nanobanana'), 'nanobanana')
})

test('an OFF engine is excluded from execution while its stored preference survives', () => {
  localStorage.setItem(STORAGE_ENGINES, JSON.stringify(['fixture_engine']))
  assert.equal(registerDescriptor({ id: 'fixture_owner', slots: { 'engine.spec': [{ id: 'fixture_engine', kind: 'api', label: 'Fixture', order: 9 }] } }), true)
  assert.deepEqual(readEngines(localStorage), ['klein'])
  writeEngines(localStorage, ['klein'])
  assert.deepEqual(JSON.parse(localStorage.getItem(STORAGE_ENGINES)), ['klein', 'fixture_engine'])
  setEnabled(['fixture_owner'])
  assert.deepEqual(readEngines(localStorage), ['klein', 'fixture_engine'])
  setEnabled([])
  assert.deepEqual(canonicalEngines(['fixture_engine']), [])
})

test('first setup renders the core choice without an install prerequisite', () => {
  const html = mount(SetupStart, {}, '/setup')
  assert.match(html, /Your dataset workspace is ready/)
  assert.match(html, /Open LDS/)
  assert.doesNotMatch(html, /Install everything|Image generation.*Step 1 of 5|Python 3\.14/)
})

test('completing the dataset setup posts only the core goal', async () => {
  const calls=[]
  globalThis.fetch = async (url, options) => { calls.push({ url, options }); return Response.json({ ok: true }) }
  await completeCoreSetup('dataset')
  assert.deepEqual(calls.map(c => c.url), ['/api/setup-state/complete'])
  assert.deepEqual(JSON.parse(calls[0].options.body), { goal: 'dataset' })
  assert.equal(sessionStorage.getItem('lds_setup_redirected'), '1')
})

test('a failed core completion does not mark setup as completed', async () => {
  globalThis.fetch = async () => Response.json({ error: 'Cannot save core setup' }, { status: 500 })
  await assert.rejects(completeCoreSetup('dataset'), /Cannot save/)
  assert.equal(sessionStorage.getItem('lds_setup_redirected'), null)
})

test('missing historical workspaces explain the plugin state and link to the library', () => {
  const html = mount(UnavailablePluginPage)
  assert.match(html, /not active in this session/)
  assert.match(html, /\/plugins\?tab=installed/)
  assert.match(html, /Open datasets/)
})

test('a direct Live or Video Studio bookmark never silently shows Images while its owner is off', () => {
  for (const lane of ['live', 'video']) {
    const html = mount(StudioPage, {}, `/studio?lane=${lane}`)
    assert.match(html, /This Studio lane.*is unavailable/)
    assert.doesNotMatch(html, /data-testid="studio-lane-(live|video)"/)
  }
})

test('settings transport scopes read, write, secret removal and provider probes to one owner', () => {
  assert.equal(settingsApiUrl(null), '/api/settings')
  assert.equal(settingsApiUrl('cloud_training'), '/api/settings?plugin=cloud_training')
  assert.equal(settingsApiUrl('api_engines', '/api/settings/test/openai'), '/api/settings/test/openai?plugin=api_engines')
  assert.equal(settingsApiUrl('api_engines', '/api/settings/secret/OPENAI_API_KEY'), '/api/settings/secret/OPENAI_API_KEY?plugin=api_engines')
  assert.match(pluginSettingsAvailability(null), /not installed/)
  assert.match(pluginSettingsAvailability({ installed: true, enabled: false }), /Turn on/)
  assert.match(pluginSettingsAvailability({ pending_action: 'enable' }), /pending/)
})

test('saving an owned leaf preserves a concurrently edited sibling draft', () => {
  const saved = { klein: { strength: 0.5, improve: 'old' } }
  const atSubmit = { klein: { strength: 0.7, improve: 'old' } }
  const current = { klein: { strength: 0.7, improve: 'draft' } }
  const patch = settingsPatch(atSubmit, saved)
  assert.deepEqual(patch, { klein: { strength: 0.7 } })
  assert.deepEqual(reconcileSettings(current, saved, { klein: { strength: 0.65, improve: 'old' } }, patch, atSubmit),
    { klein: { strength: 0.65, improve: 'draft' } })
})

test('preparation sends only selected actions and follows the authoritative returned plan', async () => {
  let body
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/plugins/fixture_owner/preparation')
    body = JSON.parse(options.body)
    return Response.json({ plan: ['fixture_dependency', 'fixture_model'], statuses: { fixture_dependency: { state: 'queued' } } })
  }
  const result = await startPreparation('fixture_owner', ['fixture_model'])
  assert.deepEqual(body, { actions: ['fixture_model'] })
  assert.deepEqual(result.actions, ['fixture_dependency', 'fixture_model'])
  assert.equal(preparationState(result.actions, result.statuses), 'running')
})

test('OFF, missing, restart-pending or invalid plugin preparation refusals never start status polling', async () => {
  for (const status of [404, 409, 422, 503]) {
    let calls=0
    globalThis.fetch = async () => { calls++; return Response.json({ error: 'Plugin preparation refused' }, { status }) }
    await assert.rejects(startPreparation('fixture_owner', ['fixture_model']), /refused/)
    assert.equal(calls, 1)
  }
})

test('preparation observes actual terminal receipts and reports prepared, not ready', async () => {
  let calls=0
  const events=[]
  const result=await watchPreparation(['model'], { wait: async () => {}, onStatus: s => events.push(s),
    read: async () => ({ statuses: { model: { state: ++calls < 2 ? 'running' : 'success' } } }) })
  assert.equal(result, 'prepared'); assert.equal(events.length, 2)
  assert.equal(preparationState(['model'], { model: { state: 'error' } }), 'error')
})

test('preparation status errors and missing receipts stop after bounded attempts; retry attaches without a second POST', async () => {
  let calls=0
  await assert.rejects(watchPreparation(['model'], { wait: async () => {}, read: async () => { calls++; throw new Error('offline') } }), /unavailable/)
  assert.equal(calls, 3)
  calls=0
  await assert.rejects(watchPreparation(['model'], { wait: async () => {}, read: async () => { calls++; return {} } }), /no active status/)
  assert.equal(calls, 10)
  assert.equal(await watchPreparation(['model'], { read: async () => ({ statuses: { model: { state: 'success' } } }) }), 'prepared')
})

test('preparation render offers explicit selections and disabled prerequisites without starting downloads', () => {
  const html=mount(PluginPreparation, { pluginId: 'fixture_owner', items: [
    { action: 'model', label: 'Model weights', available: true, present: false },
    { action: 'nodes', label: 'Node pack', available: false, hint: 'Choose a ComfyUI folder first' },
  ] })
  assert.match(html, /Prepare selection \(1\)/)
  assert.match(html, /Choose a ComfyUI folder first/)
  assert.match(html, /checks the whole selection/)
})

test('public shared import and stop guards survive removal of the scraper module', () => {
  assert.equal(isDatasetImportBlocked({ activity: { kind: 'generate' } }), false)
  assert.equal(isDatasetImportBlocked({ activity: { kind: 'caption' } }), true)
  assert.equal(isStopGenerationBlocked({ busy: true, activity: { kind: 'generate' } }), false)
  assert.equal(isStopGenerationBlocked({ busy: true, activity: { kind: 'caption' } }), true)
})

test('Store entry has no bundled glob and development selects its separate source explicitly', async () => {
  const source=await fs.readFile(new URL('../src/plugins/bundled.js', import.meta.url), 'utf8')
  const config=await fs.readFile(new URL('../vite.config.js', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /import\.meta\.glob|\.\.\/.*bundled\//)
  assert.match(config, /!storeBuild.*importer/s)
  assert.match(config, /bundledDevelopment\.js/)
})
