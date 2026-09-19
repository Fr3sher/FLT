import test from 'node:test'
import assert from 'node:assert/strict'
import {
  contributions, helpTopics, navItems, plugins, problems, registerDescriptor, resetRegistry,
  routes, setEnabled, validateDescriptor, whatsNewEntries,
} from './registry.js'
import { parityGaps, surfacesOf } from './parity.js'

const scrape = {
  id: 'scrape',
  nav: [{ to: '/scrape', label: 'Scrape', when: (caps) => !!caps.scrape_deps }],
  routes: [{ path: '/scrape', page: () => Promise.resolve({ default: () => null }) }],
  slots: { 'sources.panel': [{ id: 'web', label: 'Scrape the web' }] },
  help: [{ id: 'page-scrape', kind: 'page', title: 'Scrape' }],
  whatsNew: [{ id: '2026-09-05-scrape-plugin', date: '2026-09-05', title: 'x', blurb: 'y' }],
}

test.beforeEach(() => resetRegistry())

test('an optional video dialog provider registers before any video host', () => {
  assert.equal(registerDescriptor({id: 'example.renderer', slots: {
    'video.neural-render-dialog': [{id: 'dialog'}],
    'video.neural-compare': [{id: 'compare'}],
  }}), true)
  assert.equal(contributions('video.neural-render-dialog', 'studio').length, 1)
  assert.equal(contributions('video.neural-compare', 'dataset').length, 1)
  setEnabled([])
  assert.equal(contributions('video.neural-compare', 'studio').length, 0)
})

test('a valid descriptor registers and contributes on every paired surface', () => {
  assert.equal(registerDescriptor(scrape), true)
  assert.deepEqual(plugins().map((p) => p.id), ['scrape'])
  assert.equal(contributions('sources.panel', 'dataset').length, 1)
  assert.equal(contributions('sources.panel', 'bank').length, 1)
  assert.equal(contributions('sources.panel', 'videoBank').length, 1)
  assert.equal(contributions('sources.panel', 'settings').length, 0)
  assert.equal(contributions('sources.panel')[0].plugin, 'scrape')
})

test('a disabled plugin contributes nothing but stays registered', () => {
  registerDescriptor(scrape)
  setEnabled([])
  assert.deepEqual(plugins(), [])
  assert.deepEqual(contributions('sources.panel', 'dataset'), [])
  assert.deepEqual(routes(), [])
  setEnabled(['scrape'])
  assert.equal(routes().length, 1)
})

test('nav items honour their when(caps) predicate', () => {
  registerDescriptor(scrape)
  assert.equal(navItems({}).length, 0)
  assert.equal(navItems({ scrape_deps: true })[0].label, 'Scrape')
})

test('help topics and what-is-new entries carry the plugin id', () => {
  registerDescriptor(scrape)
  assert.equal(helpTopics()[0].plugin, 'scrape')
  assert.equal(whatsNewEntries()[0].plugin, 'scrape')
})

test('a bad descriptor is refused and the reason is kept', () => {
  assert.equal(registerDescriptor({ id: 'Bad Id' }), false)
  assert.equal(registerDescriptor({ id: 'ok_id', slots: { 'nowhere.slot': [] } }), false)
  assert.equal(registerDescriptor(scrape), true)
  assert.equal(registerDescriptor(scrape), false)
  const reasons = problems().map((p) => p.message)
  assert.match(reasons[0], /not a plugin id/)
  assert.match(reasons[1], /not a known slot/)
  assert.match(reasons[2], /twice/)
})

test('a slot hosted by another plugin becomes known', () => {
  registerDescriptor({ id: 'video', hosts: ['videoBank.sources'] })
  assert.equal(validateDescriptor({ id: 'acme.extra', slots: { 'videoBank.sources': [] } }), null)
})

test('an item may narrow its surfaces, and parity then needs a written skip', () => {
  const narrowed = { ...scrape, slots: { 'sources.panel': [{ id: 'web', surfaces: ['dataset'] }] } }
  assert.deepEqual(surfacesOf('sources.panel', narrowed.slots['sources.panel'][0]), ['dataset'])
  const gaps = parityGaps(narrowed)
  assert.deepEqual(gaps.map((g) => g.surface), ['bank', 'videoBank'])
  const excused = { ...narrowed, paritySkip: [
    { slot: 'sources.panel', surface: 'bank', reason: 'the bank has its own scrape intake' },
    { slot: 'sources.panel', surface: 'videoBank', reason: 'clips are not images' },
  ] }
  assert.deepEqual(parityGaps(excused), [])
  const silent = { ...narrowed, paritySkip: [{ slot: 'sources.panel', surface: 'bank' }] }
  assert.equal(parityGaps(silent).length, 2, 'a skip without a reason is not a skip')
})
