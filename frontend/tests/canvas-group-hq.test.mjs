/**
 * 🖼🖼 HQ for a WHOLE strip — and what it does to the per-picture HQ.
 *
 * Every picture on the board is a WebP tile (utils/datasetThumbUrl); each one
 * already had its own HQ. That is the right control for one picture and the
 * wrong one for eight — comparing a face across a strip meant eight clicks on
 * eight buttons counter-scaled to a fingernail at ✦ Fit. So the group bar
 * carries a master toggle.
 *
 * The design decision this file HOLDS, because it is the one a future rewrite
 * would quietly get wrong: the group's HQ is an OVERRIDE, not a broadcast. It
 * never writes into the members' own state, so switching it off gives each
 * picture back the choice it had rather than wiping the two you had turned on by
 * hand. That is the difference between `forceHq || hq` and `setHq(true)` on
 * every member, and only the first one survives being switched off.
 *
 * Asserted on the RENDER (tests/support/mountJsx.mjs) rather than on the source
 * text: what matters is the `src` each <img> ends up with, not the expression
 * that produced it. ⚠️ No event ever fires there, so the toggling itself is
 * covered by rendering both states and by the wiring assertions at the bottom.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { layoutImageNodes } from '../src/utils/canvasImageGroups.js'
import { datasetThumbUrl } from '../src/utils/datasetThumbUrl.js'
import { render } from './support/mountJsx.mjs'

const { default: CanvasImageGroup } =
  await import('../src/components/canvas/CanvasImageGroup.jsx')
const { default: CanvasGroupBar } =
  await import('../src/components/canvas/CanvasGroupBar.jsx')
const { default: CanvasImageNode } =
  await import('../src/components/canvas/CanvasImageNode.jsx')

/* ⚠️ REAL dataset image URLs, not `/i/1.png`: datasetThumbUrl only rewrites
   `/api/dataset/<id>/img/<name>`, and with any other URL the tile and the
   original are the same string — an assertion that could never go red. */
const url = (id) => `/api/dataset/7/img/render_${id}.png`

const img = (id, x, y, w, h, extra = {}) => ({
  imageId: id, x, y, w, h, visible: true, groupId: null, groupPos: null,
  image: { url: url(id), record_id: id, step: 1000 * id }, ...extra,
})

const STRIP = [
  img(1, 100, 300, 200, 150, { groupId: 'g1', groupPos: 0 }),
  img(2, 300, 300, 200, 150, { groupId: 'g1', groupPos: 1 }),
  img(3, 500, 300, 200, 150, { groupId: 'g1', groupPos: 2 }),
]

const group = layoutImageNodes(STRIP).find((r) => r.kind === 'group')
const props = (extra) => ({
  group, datasetId: 7, laneName: 'a dataset', boardScale: 0.4, ...extra,
})
const srcs = (html) => [...html.matchAll(/<img\b[^>]*\bsrc="([^"]+)"/g)].map((m) => m[1])

/* --- the strip's own HQ ---------------------------------------------------- */

test('at rest every member draws its TILE, not the original file', () => {
  const found = srcs(render(CanvasImageGroup, props({ hq: false })))
  assert.equal(found.length, STRIP.length)
  for (const src of found) {
    assert.match(src, /\/thumb\//, 'a resting board must stay cheap')
    assert.doesNotMatch(src, /\/img\//)
  }
})

test('HQ on the group puts EVERY member on the original file', () => {
  const found = srcs(render(CanvasImageGroup, props({ hq: true })))
  assert.equal(found.length, STRIP.length)
  // The exact URLs, in order — "no /thumb/ anywhere" would also pass on a strip
  // that dropped its pictures.
  assert.deepEqual(found, STRIP.map((n) => n.image.url))
})

test('…and every member SAYS it is in HQ, for the eye and for a screen reader', () => {
  const html = render(CanvasImageGroup, props({ hq: true }))
  const pressed = [...html.matchAll(/data-testid="canvas-image-hq"[^>]*/g)].map((m) => m[0])
  assert.equal(pressed.length, STRIP.length)
  for (const btn of pressed) {
    assert.match(btn, /data-hq="true"/)
    assert.match(btn, /aria-pressed="true"/)
    // The override is visible in the DOM too: that is what tells a member's own
    // HQ apart from one it inherited from the strip.
    assert.match(btn, /data-hq-forced="true"/)
  }
})

test('the members are handed the strip\'s state, not a copy of it', () => {
  // The single most important property of the chosen design: OFF gives each
  // picture back its own (untouched, still false here) choice, so the strip can
  // be switched off and the board is cheap again.
  assert.deepEqual(
    srcs(render(CanvasImageGroup, props({ hq: true, key: 'on' }))).map((s) => s.includes('/thumb/')),
    [false, false, false],
  )
  assert.deepEqual(
    srcs(render(CanvasImageGroup, props({ hq: false }))).map((s) => s.includes('/thumb/')),
    [true, true, true],
  )
})

/* --- forceHq vs the picture's own HQ -------------------------------------- */

test('a picture with no HQ of its own follows forceHq, both ways', () => {
  const node = img(1, 0, 0, 200, 150)
  const off = render(CanvasImageNode, { node, datasetId: 7, laneName: 'l', forceHq: false })
  const on = render(CanvasImageNode, { node, datasetId: 7, laneName: 'l', forceHq: true })
  // Not "contains /thumb/": the rung is the node's own ratchet, so the tile URL
  // is asserted against the helper that builds it rather than half-matched.
  assert.equal(srcs(off)[0], datasetThumbUrl(node.image.url, 256))
  assert.equal(srcs(on)[0], node.image.url)
})

test('forceHq is an override, so the per-picture button stays honest about it', () => {
  // While the strip forces HQ the member's button reads pressed — and its title
  // says WHERE that came from, because a lit button whose click changes nothing
  // on screen is the one confusing corner of this design and it must not be
  // silent about itself.
  const node = img(1, 0, 0, 200, 150)
  const on = render(CanvasImageNode, { node, datasetId: 7, laneName: 'l', forceHq: true })
  assert.match(on, /HQ is on for the whole strip/)
  const off = render(CanvasImageNode, { node, datasetId: 7, laneName: 'l', forceHq: false })
  assert.doesNotMatch(off, /HQ is on for the whole strip/)
  assert.match(off, /HQ — show this picture at full quality/)
})

/* --- the button, in the bar ------------------------------------------------ */

test('the bar carries HQ beside Export grid, with the state on it', () => {
  const off = render(CanvasGroupBar, { group, datasetId: 7, boardScale: 0.4, hq: false })
  assert.match(off, /data-testid="canvas-group-hq"/)
  assert.match(off, /aria-pressed="false"/)
  assert.match(off, /HQ — show every picture in this strip at full quality/)
  // Beside Export grid and after it: the two "do it to all of them" actions of
  // a group read as a pair, and ✕ stays last.
  assert.ok(off.indexOf('canvas-group-export-grid') < off.indexOf('canvas-group-hq'))
  assert.ok(off.indexOf('canvas-group-hq') < off.indexOf('canvas-group-close'))

  const on = render(CanvasGroupBar, { group, datasetId: 7, boardScale: 0.4, hq: true })
  assert.match(on, /data-testid="canvas-group-hq"[^>]*data-hq="true"/)
  assert.match(on, /aria-pressed="true"/)
  assert.match(on, /HQ is on for this strip/)
})

test('the HQ button is sized by the bar, so it survives ✦ Fit like the rest', () => {
  // The bar is counter-scaled (groupBarHeight); a button given a fixed font
  // would be unreadable at 24 % on a phone, which is where every chrome bug on
  // this board has been found.
  for (const boardScale of [0.1, 0.24, 0.4, 1, 2.5]) {
    const html = render(CanvasGroupBar, { group, datasetId: 7, boardScale, hq: true })
    const btn = /data-testid="canvas-group-hq"[^>]*style="([^"]*)"/.exec(html)
      || /style="([^"]*)"[^>]*data-testid="canvas-group-hq"/.exec(html)
    assert.ok(btn, `the HQ button must be styled at ${boardScale}`)
    const px = Number(/font-size:\s*([\d.]+)px/.exec(btn[1])[1])
    assert.ok(px >= 9, `HQ must stay legible at ${boardScale} (got ${px})`)
  }
})

/* --- the wiring the render cannot reach ----------------------------------- */

test('the board owns the strips\' HQ, and hands the SAME value to both halves', () => {
  // The bar is drawn in a layer of its own, so it is a SIBLING of the strip and
  // not a child: the nearest node owning both is LaneImages. If the two ever
  // read different sources the button and the pictures would disagree.
  const CANVAS = readFileSync(
    new URL('../src/components/canvas/LineageCanvas.jsx', import.meta.url), 'utf8')
  assert.match(CANVAS, /hq=\{hqGroups\.has\(r\.groupId\)\}[\s\S]*<CanvasGroupBar/,
    'the strip must be given its HQ before the bar layer is drawn')
  assert.match(CANVAS, /onToggleHq=\{toggleGroupHq\}/)
  // Not persisted, on purpose and like the per-picture HQ: nothing here may
  // reach the geometry writer.
  assert.doesNotMatch(CANVAS, /hqGroups[^\n]*onGeometry/)
})
