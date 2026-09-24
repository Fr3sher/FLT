import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement, render } from './support/mountJsx.mjs'

const { MemoryRouter } = await import('react-router')
const { configureHostRuntime } = await import('../src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../src/plugins/loadPlugins.js')
const { default: VideoReferencesPanel } = await import('../../bundled/video/frontend/studio/video/VideoReferencesPanel.jsx')
const { default: ReferenceLibraryPicker } = await import('../../bundled/video/frontend/studio/video/ReferenceLibraryPicker.jsx')
const renderInRouter = (Component, props) => render(MemoryRouter, { children: createElement(Component, props) })

test.beforeEach(t => {
  const saved = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch }
  t.after(() => Object.assign(globalThis, saved))
  globalThis.window = {}
  globalThis.document = { cookie: '', querySelector: () => null }
  globalThis.fetch = () => { throw new Error('This render must not contact a service') }
  configureHostRuntime()
  publishRuntime()
})

test('RefMods upload and Library stay available beyond both old image caps', () => {
  const value = { references: Array.from({ length: 16 }, (_, i) => ({
    kind: 'image', name: `lds_vref_${i.toString(16).padStart(32, '0')}.png`,
  })), settings: {}, setStaging() {} }
  const html = renderInRouter(VideoReferencesPanel, { value, identitiesOnly: true })
  for (const label of ['Add reference images', 'Choose image references from library']) {
    const control = html.match(new RegExp(`<[^>]*aria-label="${label}"[^>]*>`))?.[0]
    assert.ok(control, label)
    assert.doesNotMatch(control, / disabled(?:=|[ >])/)
  }
  assert.doesNotMatch(html, /Infinity/)
  const native = renderInRouter(VideoReferencesPanel, { value })
  assert.match(native.match(/<input[^>]*aria-label="Add reference images"[^>]*>/)[0], / disabled(?:=|[ >])/)
})

test('RefMods Library explains an unrestricted selection without an infinite counter', () => {
  const html = renderInRouter(ReferenceLibraryPicker, { kind: 'image', limit: Infinity })
  assert.match(html, /Select images to add/)
  assert.doesNotMatch(html, /Infinity/)
})
