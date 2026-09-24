/* 🔍 The Studio viewer, EXECUTED: the adapter mounts the unified viewer with
   the Studio's extras — and the facts the backend now serves actually render.

   A source-text pin can prove the adapter exists; only rendering proves the
   wrapper's props survive contact with GeneratedImageLightbox (a renamed prop
   would parse fine and show nothing). Same harness as the other render tests. */
import assert from 'node:assert/strict'
import test from 'node:test'

import { createElement, render } from './support/mountJsx.mjs'
import { readFileSync } from 'node:fs'

const { default: StudioResultViewer } =
  await import('../src/components/dataset/studio/StudioResultViewer.jsx')

const { configureHostRuntime } = await import('../src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../src/plugins/loadPlugins.js')
const { registerDescriptor, resetRegistry, setEnabled } = await import('../src/plugins/registry.js')
const { default: cameraPlugin } = await import('../../bundled/camera_angles/frontend/index.js')
const cameraManifest = JSON.parse(readFileSync(new URL('../../bundled/camera_angles/plugin.json', import.meta.url), 'utf8'))
const { renderToReadableStream } = await import('react-dom/server')
const { ToastProvider } = await import('../src/components/common/Toast.jsx')
const { CapabilitiesProvider } = await import('../src/context/CapabilitiesContext.jsx')
const { MemoryRouter } = await import('react-router')
test.beforeEach(t => {
  const saved = { window: globalThis.window, document: globalThis.document, fetch: globalThis.fetch }
  t.after(() => { Object.assign(globalThis, saved); resetRegistry() })
  globalThis.window = {}
  globalThis.document = { cookie: '', querySelector: () => null }
  globalThis.fetch = () => { throw new Error('A render must not contact a service') }
  resetRegistry()
  setEnabled([])
  configureHostRuntime()
  publishRuntime()
})
const renderInstalled = async (Component, props) => {
  const stream = await renderToReadableStream(createElement(MemoryRouter, null,
    createElement(ToastProvider, null, createElement(CapabilitiesProvider, null,
      createElement(Component, props)))))
  await stream.allReady
  // Streamed SSR inserts hydration comments between adjacent text nodes.
  return (await new Response(stream).text()).replace(/<!--.*?-->/gs, '')
}

const row = (over = {}) => ({
  id: 41, dataset_id: 7, url: '/api/dataset/7/img/cell.png', rating: 0,
  prompt: 'a probe scene', seed: 424242, strength: 0.9,
  checkpoint: 'z image\\lola_2000.safetensors', base_model: 'zimage_turbo.safetensors',
  sampler: 'euler', cfg: 1, steps: 8, inject_trigger: false, ...over,
})

test('the studio viewer renders the shared facts and its own verdict', async () => {
  assert.equal(registerDescriptor(cameraPlugin, { guideOwnership: cameraManifest.guide_ownership }), true)
  setEnabled(['camera_angles'])
  const html = await renderInstalled(StudioResultViewer, {
    img: row(), items: [row(), row({ id: 42 })],
    onRate: () => {}, onNavigate: () => {}, onClose: () => {},
  })
  // The unified viewer, not a fifth lightbox.
  assert.match(html, /data-testid="generated-image-lightbox"/)
  // The facts the comparison used to hide: seed, checkpoint, trigger state.
  assert.match(html, /424242/)
  assert.match(html, /lola_2000/)
  assert.match(html, /not injected/)
  // The viewer's own verbs arrived for free.
  assert.match(html, /data-testid="lightbox-camera-angles"/)
  assert.match(html, /data-testid="lightbox-repair"/)
  assert.match(html, /data-testid="lightbox-download"/)
  // The Studio's extras: the verdict pair and the loop counter.
  assert.match(html, /👍 Like/)
  assert.match(html, /👎 Not a fan/)
  assert.match(html, /1 \/ 2/)
  // Both chevrons: the comparison set wraps, so neither end loses one.
  assert.match(html, /aria-label="Previous image"/)
  assert.match(html, /aria-label="Next image"/)
})

test('a lone image drops the loop and the counter, keeps the verdict', () => {
  const html = render(StudioResultViewer, {
    img: row(), items: [row()], onRate: () => {}, onNavigate: () => {}, onClose: () => {},
  })
  assert.doesNotMatch(html, /1 \/ 1/)
  assert.doesNotMatch(html, /aria-label="Previous image"/)
  assert.match(html, /👍 Like/)
})


test('without Camera angles the viewer keeps repair and download, and offers no camera action', () => {
  const html = render(StudioResultViewer, {
    img: row(), items: [row()], onRate: () => {}, onNavigate: () => {}, onClose: () => {},
  })
  assert.match(html, /data-testid="lightbox-repair"/)
  assert.match(html, /data-testid="lightbox-download"/)
  assert.doesNotMatch(html, /data-testid="lightbox-camera-angles"/)
})
