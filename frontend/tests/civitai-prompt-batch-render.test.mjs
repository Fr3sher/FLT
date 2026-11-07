/**
 * Execute the Civitai button, and document why its modal cannot use this harness.
 * CivitaiBrowserButton renders with and without a batch; a ReferenceError in
 * either branch fails a test instead of producing a blank screen.
 *
 * CivitaiBrowserModal is now PORTALED to document.body to escape the sticky,
 * scrollable aside's stacking context and clipping. Previously result votes
 * painted over prompts despite a high z-index; see studioModalsArePortaled.contract.test.js.
 * react-dom/server explicitly rejects portals with "Portals are not currently
 * supported by the server renderer." Rendering THROWS rather than returning
 * empty markup, so neither modal markup nor execution can be asserted through SSR.
 *
 * Do not remove the portal to restore that coverage. Instead, source contracts
 * in civitaiBrowser.contract.test.js check prop wiring and the batchable gate,
 * while the responsive probe's civitai state opens the real modal at five sizes.
 * Caveat: data-probe-layer is excluded from overlap pairs, so a green responsive
 * probe says nothing about this stacking defect. Only a screenshot verifies it.
 */
import assert from 'node:assert/strict'
import test from 'node:test'

import { createElement, render } from './support/mountJsx.mjs'

const { default: CivitaiBrowserButton } =
  await import('../src/components/dataset/studio/CivitaiBrowserButton.jsx')
/* The button opens a modal containing Link. The app supplies a router;
   this harness must provide one explicitly. */
const { MemoryRouter } = await import('react-router')

const noop = () => {}
const underRouter = (Component) => (props) =>
  createElement(MemoryRouter, null, createElement(Component, props))

test('the button renders without a batch, preserving the original state', () => {
  const html = render(underRouter(CivitaiBrowserButton), { prompt: '', onPrompt: noop })
  assert.ok(html.includes('Civitai'), 'the button must render')
})

test('the button renders with a batch and executes the count branch', () => {
  const html = render(underRouter(CivitaiBrowserButton),
    { prompt: '', onPrompt: noop, picks: ['a', 'b', 'c'], onTogglePick: noop })
  assert.ok(html.includes('Civitai'))
})

test('the portaled modal is outside this harness, verified rather than assumed', async () => {
  /* Establish the coverage limit documented above. If react-dom/server gains
     portal support, this test will fail, prompting restoration of the missing
     assertions instead of leaving the gap undiscovered. */
  const { default: CivitaiBrowserModal } =
    await import('../src/components/dataset/studio/CivitaiBrowserModal.jsx')
  // Without a DOM we cannot reach createPortal. Stub only enough to observe
  // the server renderer's actual rejection.
  globalThis.document = { body: { nodeType: 1 } }
  try {
    assert.throws(
      () => render(underRouter(CivitaiBrowserModal),
        { open: true, onClose: noop, onUse: noop, picks: ['a'], onTogglePick: noop }),
      /Portals are not currently supported by the server renderer/,
    )
  } finally {
    delete globalThis.document
  }
})
