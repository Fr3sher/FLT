import '../../../frontend/tests/plugin-sdk-host.mjs'
/**
 * The ◉ LoRA Canvas "Datasets" panel has been replaced with a BAR.
 *
 * History explains the compatibility helpers retained here. The panel opened
 * expanded on wide screens; its dataset, model, status and search controls
 * pushed the board below the fold. It was first changed to start collapsed.
 * However, an expanded panel with fourteen datasets still occupied 389 px
 * (54% of a 1280×720 screen) for anyone who had left it open. On 2026-08-08,
 * it was replaced with a roughly 40 px row of chips and popover controls.
 *
 * The `lds.canvasFilterOpen` helpers must remain exported and correct.
 * The component no longer reads them, since a bar cannot collapse, but real
 * browsers have stored this key. Repository policy requires an alias path
 * before renaming or deleting a stored identifier. A future collapsible
 * control can reuse this key instead of inventing another.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  CANVAS_FILTER_OPEN_KEY, readCanvasFilterOpen, writeCanvasFilterOpen,
} from '../frontend/utils/canvasFamilyFilter.js'

const SOURCE = readFileSync(
  new URL('../frontend/components/canvas/CanvasDatasetFilter.jsx', import.meta.url), 'utf8')

/** Injectable test localStorage, following the other canvas helpers. */
const store = (initial = {}) => {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, String(v)),
    dump: () => Object.fromEntries(map),
  }
}

test('the stored fold key keeps its name and its meaning', () => {
  assert.equal(CANVAS_FILTER_OPEN_KEY, 'lds.canvasFilterOpen')
  assert.equal(readCanvasFilterOpen(store()), false)
})

test('an explicit unfold survives the reload, an explicit fold too', () => {
  const s = store()
  writeCanvasFilterOpen(s, true)
  assert.equal(s.dump()[CANVAS_FILTER_OPEN_KEY], '1')
  assert.equal(readCanvasFilterOpen(s), true)
  writeCanvasFilterOpen(s, false)
  assert.equal(readCanvasFilterOpen(s), false)
})

test('a junk or absent store never throws and reads as folded', () => {
  assert.equal(readCanvasFilterOpen(null), false)
  assert.equal(readCanvasFilterOpen(undefined), false)
  assert.equal(readCanvasFilterOpen(store({ [CANVAS_FILTER_OPEN_KEY]: 'yes' })), false)
  const hostile = { getItem() { throw new Error('private mode') } }
  assert.equal(readCanvasFilterOpen(hostile), false)
  // A storage write failure must not break the click.
  assert.equal(writeCanvasFilterOpen({ setItem() { throw new Error('quota') } }, true), false)
})

test('the filter is a bar: no fold, and no viewport-width logic either', () => {
  // The collapsed state is no longer read: there is no panel body to hide.
  assert.doesNotMatch(SOURCE, /readCanvasFilterOpen\(/)
  assert.doesNotMatch(SOURCE, /writeCanvasFilterOpen\(/)
  // Viewport width must not determine this state: resizing the window used
  // to reopen the panel.
  assert.doesNotMatch(SOURCE, /matchMedia/)
  assert.doesNotMatch(SOURCE, /min-width: 640px/)
  // Each control lives in a menu chip rather than an expanded panel body.
  assert.match(SOURCE, /<CanvasFilterMenu label="Datasets"/)
  assert.match(SOURCE, /<CanvasFilterMenu label="Models"/)
  assert.match(SOURCE, /<CanvasFilterMenu label="Status"/)
})
