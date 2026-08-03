/**
 * 🖼 A picture parked OUTSIDE its lane must render, and must render where it
 * was put.
 *
 * The board used to floor a pinned image's coordinates at zero, so its own
 * lane's top-left corner was a wall: a render could be dragged down and right
 * for ever and never up or left. Removing that wall is a one-line change in
 * `clampImageBox`, and one-line changes to geometry are exactly the kind that
 * pass a green suite and then draw nothing — a negative `left` swallowed by a
 * parent that clips, a NaN in a style, a member of a strip laid out from an
 * anchor that is now above the origin.
 *
 * So this file EXECUTES the components (tests/support/mountJsx.mjs) with the
 * coordinates free placement produces, instead of asserting on the arithmetic
 * that feeds them — the arithmetic is already covered next door in
 * src/utils/canvasImageNodes.test.js, and it was never the half that shipped
 * broken.
 */
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { clampImageBox, imageNodeExtent } from '../src/utils/canvasImageNodes.js'
import { layoutImageNodes } from '../src/utils/canvasImageGroups.js'
import { fitView, stackLanes } from '../src/utils/canvasLayout.js'
import { render } from './support/mountJsx.mjs'

/* ⚠️ Dynamic — the hooks that teach Node to read .jsx are installed while
   mountJsx.mjs is evaluated, and a static import would already be linked. */
const { default: CanvasImageNode } =
  await import('../src/components/canvas/CanvasImageNode.jsx')
const { default: CanvasImageGroup } =
  await import('../src/components/canvas/CanvasImageGroup.jsx')

const img = (id, x, y, extra = {}) => ({
  imageId: id, x, y, w: 200, h: 150, visible: true, groupId: null, groupPos: null,
  image: { url: `/i/${id}.png`, record_id: id, step: 1000 * id },
  ...extra,
})

const styleOf = (html) => /style="([^"]*)"/.exec(html)?.[1] ?? ''

test('a picture dragged above and left of its lane draws at those coordinates', () => {
  const node = img(1, -640, -320)
  const html = render(CanvasImageNode, {
    node, datasetId: 7, laneName: 'a dataset', boardScale: 0.4,
  })
  const style = styleOf(html)
  assert.match(style, /left:\s*-640px/, 'a negative left is what free placement IS')
  assert.match(style, /top:\s*-320px/)
  assert.doesNotMatch(html, /NaN/, 'no style may degrade to NaN on the way')
})

test('every zoom the board reaches draws it, not just 100 %', () => {
  // ✦ Fit lands around 10-45 % on a phone, which is where every chrome bug on
  // this board has been found. The node counter-scales its controls from this
  // number, so it is the one axis worth sweeping.
  for (const boardScale of [0.1, 0.24, 0.4, 1, 5]) {
    const html = render(CanvasImageNode, {
      node: img(2, -1800, -900), datasetId: 7, laneName: 'ds', boardScale,
    })
    assert.match(styleOf(html), /left:\s*-1800px/, `broken at ${boardScale}`)
    assert.doesNotMatch(html, /NaN/, `NaN in a style at ${boardScale}`)
  }
})

test('a whole STRIP parked above its lane still draws every member in order', () => {
  // A group's tiles are laid out FROM the anchor, so an anchor above the origin
  // is the case where a strip could quietly collapse onto itself.
  const strip = [
    img(1, -500, -400, { groupId: 'g1', groupPos: 0 }),
    img(2, -300, -400, { groupId: 'g1', groupPos: 1 }),
    img(3, -100, -400, { groupId: 'g1', groupPos: 2 }),
  ]
  const group = layoutImageNodes(strip).find((r) => r.kind === 'group')
  const html = render(CanvasImageGroup, {
    group, datasetId: 7, laneName: 'ds', boardScale: 0.4, dropHint: null,
  })
  assert.equal(html.match(/data-canvas-image=""/g).length, strip.length)
  // Edge to edge and strictly left to right, exactly as inside the lane: the
  // members' lefts are the anchor's x plus the widths before them.
  const lefts = [...html.matchAll(/left:\s*(-?[\d.]+)px/g)].map((m) => Number(m[1]))
  assert.equal(lefts[0], -500, 'the strip starts where its anchor was dropped')
  for (let i = 1; i < strip.length; i += 1) {
    assert.ok(lefts[i] > lefts[i - 1], 'members stay in order outside the lane too')
  }
  assert.doesNotMatch(html, /NaN/)
})

test('and the board FITS around it — the picture is reachable, not stranded', () => {
  // The half a rendering test cannot see: a picture that draws at -320 but is
  // outside the box ✦ Fit frames is a picture you cannot get back to.
  const nodes = [clampImageBox({ x: -640, y: -320, w: 200, h: 150 })]
  const ext = imageNodeExtent(nodes)
  const world = stackLanes([
    { datasetId: 7, width: 900, height: 400, minX: ext.minX, minY: ext.minY },
  ])
  const view = fitView(world, { width: 800, height: 600 }, { padding: 0 })
  // The picture's top-left, in screen units, has to land inside the frame.
  const sx = view.tx + (-640) * view.scale
  const sy = view.ty + (34 - 320) * view.scale   // 34 = the lane header above it
  assert.ok(sx >= -0.001 && sx <= 800, `x off the frame: ${sx}`)
  assert.ok(sy >= -0.001 && sy <= 600, `y off the frame: ${sy}`)
})

test('the board actually HANDS stackLanes the overhang it measured', () => {
  /* The load-bearing two lines, and the ones a refactor drops without noticing:
     `imageNodeExtent` reports how far a lane's pictures reach above and left of
     it, and `stackLanes` grows the board box by exactly that. Between them sits
     one object literal in LineageCanvas. Drop `minX`/`minY` from it and every
     test above still passes — the picture still draws at -640 — while ✦ Fit
     quietly goes back to framing the quadrant below the origin and the picture
     becomes unreachable. There is no unit to catch that; the seam is the
     object. */
  const canvas = readFileSync(
    new URL('../src/components/canvas/LineageCanvas.jsx', import.meta.url), 'utf8')
  const memo = /const world = useMemo\(\(\) => stackLanes\(([\s\S]*?)\)\), \[/.exec(canvas)
  assert.ok(memo, 'the world is still stacked from the lanes')
  assert.match(memo[1], /minX:\s*ext\.minX/)
  assert.match(memo[1], /minY:\s*ext\.minY/)
})
