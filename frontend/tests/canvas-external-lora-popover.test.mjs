/**
 * 🔌 THE EXTERNAL-LoRA POPOVER CLOSES — the ✕ that did nothing at all.
 *
 * "🔌 Add an external LoRA" is PORTALLED to <body>, and that is what made it
 * look innocent: nothing on screen is above it, its ✕ has an onClick, and the
 * handler is wired. It still could not be closed. A React portal moves the
 * DOM node, not the REACT tree — events from it bubble up through the
 * component that rendered it, and that path runs straight through the canvas
 * frame's `onPointerDown`. The frame found no control marker on the press,
 * took pointer capture to start a pan, and the `click` that followed was
 * retargeted to the frame. Measured headless on a disposable instance:
 * `btn pointerdown` → `gotpointercapture on lds-canvas-frame` → the click's
 * target is the frame. The button never heard it.
 *
 * `data-canvas-control` is the board's documented opt-out for exactly this —
 * the lane header's 🪪 thumbnail and a group's ✕ were the two previous
 * victims. It was never put on the popover, which is the whole bug.
 *
 * The other two ways out (Escape, a press anywhere else) were simply absent,
 * where every other Canvas popover has all three (CanvasFilterMenu).
 *
 * Read as source text plus the REAL hit-test: `renderToStaticMarkup` cannot
 * render a portal at all, so what a test can hold on to is the markup the
 * portal is given and the actual rule the frame applies to it.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { isNodeControlTarget, nodePointerIntent } from '../src/utils/canvasNodeChrome.js'

const src = readFileSync(
  new URL('../src/components/canvas/ExternalLoraNodes.jsx', import.meta.url), 'utf8')
const canvas = readFileSync(
  new URL('../src/components/canvas/LineageCanvas.jsx', import.meta.url), 'utf8')

/** The body of `export function ExternalLoraAddFlow(` … end of file. */
const addFlow = (() => {
  const start = src.indexOf('export function ExternalLoraAddFlow(')
  assert.ok(start > 0, 'ExternalLoraAddFlow is still the popover component')
  return src.slice(start)
})()

/** The opening tag of the element `createPortal` is handed. */
const portalRoot = (() => {
  const at = addFlow.indexOf('createPortal(')
  assert.ok(at > 0, 'the popover is still portalled out of the board')
  const open = addFlow.indexOf('<div', at)
  return addFlow.slice(open, addFlow.indexOf('>', open))
})()

/* A stand-in for a node INSIDE the popover — the ✕, say. `closest` answers
   from the attributes the portal root actually carries in the source, so this
   runs the frame's real rule against the real markup rather than a hand-written
   copy of it that could quietly stop matching. */
const insidePopover = {
  closest: (sel) => sel.split(',').some((one) => {
    const s = one.trim()
    const attr = s.startsWith('[') ? s.slice(1, -1) : null
    if (attr) return portalRoot.includes(attr)
    if (s.startsWith('.')) return portalRoot.includes(s.slice(1))
    return false
  }) ? {} : null,
}

test('the popover opts out of the board gesture, so its ✕ can hear a click', () => {
  assert.ok(isNodeControlTarget(insidePopover),
    'no pointer capture ⇒ the click is not retargeted to the frame')
})

test('and it opts out for a finger too, not just a mouse', () => {
  assert.equal(nodePointerIntent(insidePopover, 'mouse'), 'control')
  assert.equal(nodePointerIntent(insidePopover, 'touch'), 'control')
})

test('the popover closes the three ways every other Canvas popover closes', () => {
  assert.match(addFlow, /addEventListener\('pointerdown', onDown, true\)/,
    'a press anywhere else closes it — capture phase, like CanvasFilterMenu')
  assert.match(addFlow, /addEventListener\('keydown', onKey, true\)/, 'Escape closes it')
  assert.match(addFlow, /aria-label="Close"/, 'and the ✕ is still there')
  assert.match(addFlow, /removeEventListener\('pointerdown', onDown, true\)/,
    'both listeners are torn down with the popover')
  assert.match(addFlow, /removeEventListener\('keydown', onKey, true\)/)
})

test('an open suggestion list keeps the first Escape', () => {
  assert.match(addFlow, /role="combobox"\]\[aria-expanded="true"/,
    'dismissing the dropdown must not throw the typed path away with the popover')
})

test('the button that opens it is exempt from the close-on-press-outside', () => {
  // Without the exemption the press closes the popover and the click that
  // follows toggles it straight back open: it could never be shut from here.
  assert.match(addFlow, /data-canvas-ext-lora-toggle/,
    'the popover knows which press not to treat as "away"')
  const toggle = canvas.slice(canvas.indexOf('setExtPickerOpen((v) => !v)'))
  assert.match(toggle.slice(0, 600), /data-canvas-ext-lora-toggle/,
    'and the toolbar button wears the marker the popover looks for')
})
