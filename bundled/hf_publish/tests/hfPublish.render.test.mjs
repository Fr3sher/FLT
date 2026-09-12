/**
 * 🤗 Publish to Hugging Face — RENDERED, not grepped.
 *
 * The contract test pins that the core lends the slot and the plugin fills
 * it. This file mounts the plugin's panels with the core's own harness
 * (frontend/tests/support/mountJsx.mjs) and reads the markup, so a
 * ReferenceError in a branch throws here instead of on a user's screen.
 * Effects never run under renderToStaticMarkup, so no request is made: the
 * dialog is proved in the state it opens in.
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { createElement, renderToStaticMarkup } from '../../../frontend/tests/support/mountJsx.mjs'

const { default: HfExportAction } = await import('../frontend/panels/HfExportAction.jsx')
const { default: PublishHfModal } = await import('../frontend/panels/PublishHfModal.jsx')

const dataset = { id: 7, name: 'Nova' }
const offered = { caps: { hf_publish: true }, hasKeptImages: true }

test('the ready row renders its publish button; no dataset still means no row', () => {
  const html = renderToStaticMarkup(createElement(HfExportAction, { dataset, kept: 3, context: offered }))
  assert.match(html, /id="ds-export-hugging-face"/)
  assert.match(html, /data-testid="export-hugging-face"/)
  assert.match(html, /🤗 Publish to Hugging Face/)
  assert.match(html, /private by default/)
  assert.doesNotMatch(html, /role="dialog"/, 'the dialog opens on the click, not with the row')
  assert.doesNotMatch(html, /data-testid="configure-hugging-face"/)
  assert.equal(renderToStaticMarkup(createElement(HfExportAction, { context: offered })), '', 'no dataset: no row')
})

test('unconfigured publishing explains the write token and links to its own settings without mounting a publish dialog', () => {
  for (const hasKeptImages of [false, true]) {
    const html = renderToStaticMarkup(createElement(HfExportAction, {
      dataset, context: { caps: { hf_publish: false }, hasKeptImages },
    }))
    assert.match(html, /id="ds-export-hugging-face"/)
    assert.match(html, /write access to your dataset repository/)
    assert.match(html, /href="#\/plugins\/hf_publish\/settings"/)
    assert.match(html, /Configure Hugging Face publishing/)
    assert.doesNotMatch(html, /data-testid="export-hugging-face"/)
    assert.doesNotMatch(html, /role="dialog"/)
  }
})

test('configured publisher with no kept images explains the missing input and disables publishing', () => {
  const html = renderToStaticMarkup(createElement(HfExportAction, {
    dataset, context: { caps: { hf_publish: true }, hasKeptImages: false },
  }))
  assert.match(html, /data-testid="export-hugging-face" disabled=""/)
  assert.match(html, /Keep at least one image/)
  assert.doesNotMatch(html, /role="dialog"/)
})

test('the dialog opens on its form: private, NFAA on, reference photo off, Publish disabled until consent', () => {
  const html = renderToStaticMarkup(createElement(PublishHfModal, { datasetId: 7, onClose: () => {} }))
  assert.match(html, /role="dialog"/)
  assert.match(html, /aria-label="Publish to Hugging Face"/)
  assert.match(html, /name="hf-visibility" checked="" value="private"/)
  assert.match(html, /Not-for-all-audiences tag/)
  assert.match(html, /Include the reference photo/)
  assert.match(html, /I have the right to share these images/)
  // Publish is the last button and it is disabled: no consent ticked, no repo id yet.
  const buttons = [...html.matchAll(/<button[^>]*>/g)].map((m) => m[0])
  assert.match(buttons[buttons.length - 1], /disabled=""/)
  assert.match(html, /Nothing is uploaded until you press Publish/)
})
