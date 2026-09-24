/* 📷 The two lightbox verbs, EXECUTED: rendered with the core's own harness so
   a renamed prop or an import that resolves nowhere throws here rather than on
   a user's screen. Effects never run server-side (the picker stays closed),
   which is the state that matters: the button, its testid, its gate.

   React comes through the harness, not a bare import: this folder has no
   node_modules above it, and the harness resolves the frontend package's copy
   for everything under bundled/ — the node-side twin of Vite's resolve.dedupe. */
import assert from 'node:assert/strict'
import test from 'node:test'

const { createElement, renderToStaticMarkup } =
  await import('../../../frontend/tests/support/mountJsx.mjs')
const { ToastProvider } = await import('../../../frontend/src/components/common/Toast.jsx')
const { configureHostRuntime } = await import('../../../frontend/src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../../../frontend/src/plugins/loadPlugins.js')
globalThis.window = {}
configureHostRuntime()
publishRuntime()
const { default: GalleryCameraAction } = await import('../frontend/panels/GalleryCameraAction.jsx')
const { default: DatasetCameraAction } = await import('../frontend/panels/DatasetCameraAction.jsx')

const inApp = (node) => renderToStaticMarkup(createElement(ToastProvider, null, node))

test('the gallery verb renders on a library row, disabled with its reason on a camera view, and not at all without a row', () => {
  const html = inApp(createElement(GalleryCameraAction, { img: { id: 7, status: 'done' }, hasRow: true }))
  assert.match(html, /data-testid="lightbox-camera-angles"/)
  assert.doesNotMatch(html, /disabled=""/)
  const view = inApp(createElement(GalleryCameraAction,
    { img: { id: 8, status: 'done', derivation_kind: 'camera_angle' }, hasRow: true }))
  assert.match(view, /disabled=""/)
  assert.match(view, /cannot itself be re-shot/)
  const bare = inApp(createElement(GalleryCameraAction, { img: { url: '/p.png' }, hasRow: false }))
  assert.equal(bare, '')
})

test('the dataset verb renders only for a row the lane can re-shoot', () => {
  const html = inApp(createElement(DatasetCameraAction, { img: { id: 3, status: 'keep', filename: 'a.png' } }))
  assert.match(html, /data-testid="dataset-camera-angles"/)
  assert.match(html, /pending candidates of this dataset/)
  const none = inApp(createElement(DatasetCameraAction, { img: { id: 3, status: 'pending' } }))
  assert.equal(none, '', 'a row with no file yet shows no button')
  const preview = inApp(createElement(DatasetCameraAction,
    { img: { id: 3, status: 'keep', filename: 'a.png', _rescueReviewPreview: true } }))
  assert.equal(preview, '', 'the rescue preview is half a Curation decision, not a library picture')
})
