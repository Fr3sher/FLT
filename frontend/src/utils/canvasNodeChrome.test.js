import test from 'node:test';
import assert from 'node:assert/strict';
import {
  CLUSTER_UNITS, CONTROL_UNITS, chromeScale, chromeScreenSize, clusterUnits,
  groupBarHeight, groupCornerScale, groupCornerUnits, hasOwnResizeCorner,
  hasResizeCornerOver, isNodeControlTarget, nodePointerIntent, pillSelectScale,
  pillSelectScreenSize,
} from './canvasNodeChrome.js';

/* The ✕ that "did not work" on a phone.

   The first test is the bug, in one number: at the zoom the report came from,
   the close button measured about ten screen pixels. Nothing was broken —
   nothing was reachable. */

// A stand-in for a DOM node: `closest` answers from a list of selectors the
// element is inside of. Enough to pin the rules without a DOM.
const el = (...inside) => ({
  closest: (sel) => (inside.includes(sel) ? { sel } : null),
});

const CLOSE_BUTTON = el('[data-canvas-image] button', '[data-canvas-image]');
const RESIZE_CORNER = el('[data-canvas-image-resize]', '[data-canvas-image]');
const PICTURE = el('[data-canvas-image]');

// ---- THE bug --------------------------------------------------------------

test('the ✕ is a real touch target at the zoom the board is actually read at', () => {
  // 65 % — the zoom on the report. Untouched, the 28-unit button lands at 18 px.
  assert.ok(28 * 0.65 < 24, 'the raw control is under any touch guideline');
  // Counter-scaled, it is back to its nominal size under the finger.
  assert.ok(chromeScreenSize(0.65, 320) >= 24,
    `got ${chromeScreenSize(0.65, 320)} px at 65 %`);
  // And at the far end of the range — a board fitted to twenty runs. Here the
  // row's cap bites before the ideal does (a 320-unit pin is only 77 px on
  // screen at that zoom, and four 28-px buttons would be twice as wide as the
  // whole tile), so the honest claim is "about three times bigger than the
  // bug", not "28 px".
  // (~13 px, not the ~16 it was: the row gained HQ. See the row-budget test
  // below, which is where that trade is stated and re-agreed.)
  assert.ok(chromeScreenSize(0.24, 320) >= 13,
    `got ${chromeScreenSize(0.24, 320)} px at 24 %`);
  assert.ok(chromeScreenSize(0.24, 320) > 3 * (14 * 0.24),
    'and far bigger than the glyph it replaces');
});

test('zooming IN does not blow the control up', () => {
  assert.equal(chromeScale(1, 320), 1);
  assert.equal(chromeScale(2.5, 320), 1, 'never smaller than its board size');
});

test('the control CLUSTER never eats the picture it decorates', () => {
  // A contact-sheet thumbnail on a board fitted very far out: a constant-size
  // pair of buttons would cover the whole tile. The cap wins, and the fact that
  // the target is then below the touch guideline is a consequence of the tile
  // being 45 px wide — there is no honest way around that, and it is stated
  // here rather than hidden. Zooming in is the answer, and it works.
  const tiny = chromeScale(0.28, 160);
  assert.ok(tiny * CLUSTER_UNITS <= 160 * 0.94 + 1e-9,
    'the 🔍 ✕ ⬇ HQ 🗑 row stays inside the tile');
  assert.ok(tiny < 1 / 0.28, 'the cap, not the ideal, is what applies');
  // A full-size pin at the same zoom has room for more, and gets it.
  assert.ok(chromeScreenSize(0.28, 320) > chromeScreenSize(0.28, 160));
});

test('the controls are ONE line, and each one is paid for in width', () => {
  // The bug this pins is the WRAP, not the size. Four controls (🔍 ✕ ⬇ 🗑) laid
  // out in two columns is a 2×2 block, and a block capped at a share of the
  // tile's width is a block sitting mid-picture: reported on a group of five,
  // it covered the picture AND the "step N · strength X" label beside it.
  // A row's budget therefore GROWS with the number of controls — that is the
  // honest cost, and it is a number rather than a wrap.
  // FIVE now: HQ (show the original file instead of the fast WebP tile) joined
  // the row. This assertion is the bill for it, and it is meant to be re-read
  // and re-agreed every time — a control added without looking here is a
  // control every other target silently pays for.
  assert.equal(CLUSTER_UNITS, clusterUnits(5));
  assert.equal(clusterUnits(5), 5 * CONTROL_UNITS + 4 * 2 + 2,
    'five targets, four gaps, one padding — one line');
  assert.ok(clusterUnits(5) > clusterUnits(4), 'a fifth control widens the row');
  assert.ok(clusterUnits(4) > clusterUnits(3), 'a fourth control widens the row');
  assert.ok(clusterUnits(3) > clusterUnits(2));
  // What the row still guarantees at the zooms the board is actually read at.
  assert.ok(chromeScreenSize(0.45, 320) >= 24,
    `got ${chromeScreenSize(0.45, 320)} px at 45 %`);
  // …and what it costs at the far end, stated instead of hidden. A 320-unit pin
  // at 24 % is a 77-px tile; five 28-px targets are nearly TWICE that, so the
  // cap divides what there is. The number was ~16 px with four controls and is
  // ~13 with five: that is what HQ cost, at the one zoom where the row is
  // already against the wall. Every zoom the board is read at to actually
  // compare pictures (≥45 %) still gets a full-size target.
  const far = chromeScreenSize(0.24, 320);
  assert.ok(far >= 13 && far < 16, `got ${far} px at 24 %`);
});

test('the row leaves the resize corner alone', () => {
  // The corner is drawn on the same edge, at the same counter-scale. Reserved,
  // row + corner still fit the tile; unreserved, the row would grow into it
  // exactly when the cap starts to bite (i.e. on the smallest tiles).
  const w = 260;
  const k = chromeScale(0.3, w, clusterUnits(4), CONTROL_UNITS);
  assert.ok(k * (clusterUnits(4) + CONTROL_UNITS) <= w * 0.94 + 1e-9,
    'the row stops where the resize handle starts');
  assert.ok(k < chromeScale(0.3, w, clusterUnits(4)),
    'reserving the corner is what costs that width — a member pays nothing');
  // A member has no corner to reserve, and asking for fewer controls (no 🗑
  // wired) must not make the remaining ones smaller.
  assert.ok(chromeScale(0.3, w, clusterUnits(3)) >= chromeScale(0.3, w, clusterUnits(4)));
});

/* ◢ …and the corner the row did NOT know about.

   The reservation above was written as "a node of its own has a corner, a
   member has none", which is what each component RENDERS. What is over the
   tile is a different question: a group's resize corner is drawn at the
   strip's bottom-right, and that is the last member's bottom-right. Reported
   with a screenshot — on a group of five, the armed (red) 🗑 was laid exactly
   on the ◢ that resizes the group, so the strip's only size grip was a delete
   button. Both questions now come from the helpers below, so the render
   condition and the reservation cannot answer differently again. */

test('a group MEMBER draws no corner, and the last one still has one over it', () => {
  assert.ok(hasOwnResizeCorner('node'), 'a node of its own draws its handle');
  assert.equal(hasOwnResizeCorner('member'), false, 'a member draws none…');
  // …but the strip's handle lands on exactly one of them.
  assert.ok(hasResizeCornerOver('member', true), 'the LAST tile is under the strip’s ◢');
  assert.equal(hasResizeCornerOver('member', false), false, 'no other member is');
  assert.ok(hasResizeCornerOver('node'), 'and a node of its own, group or not');
});

test('the strip’s corner is counter-scaled uncapped — so it is BOARD units', () => {
  // Why the member cannot reserve it the way a node of its own does: that
  // corner is not drawn at the row's scale, it is drawn at the raw zoom's
  // (CanvasImageGroup). A strip is as wide as it has members, so the cap that
  // protects one tile's picture has nothing to protect there.
  assert.equal(groupCornerScale(1), 1, 'never smaller than its board size');
  assert.equal(groupCornerScale(2), 1);
  assert.ok(Math.abs(groupCornerScale(0.28) - 1 / 0.28) < 1e-9);
  assert.ok(Math.abs(groupCornerUnits(0.28) - CONTROL_UNITS / 0.28) < 1e-9);
  assert.equal(groupCornerScale(0), 100, 'a nonsense zoom is clamped, not infinite');
  assert.equal(groupCornerScale(NaN), 1);
});

test('the last member’s row stops where the group’s ◢ starts, at both zooms', () => {
  // The two zooms the original placement fix was checked at, on the tile size
  // a pin actually has (320 board units square).
  const row = CLUSTER_UNITS;                    // the row as actually drawn
  for (const s of [0.55, 0.28]) {
    const reserve = groupCornerUnits(s);
    const k = chromeScale(s, 320, row, 0, reserve);
    assert.ok(row * k + reserve <= 320 * 0.94 + 1e-9,
      `at ${s * 100} % the row ends ${(320 * 0.94 - row * k - reserve).toFixed(1)} units short`);
    // The bug, restated as geometry: with nothing reserved the row is drawn at
    // offset ZERO from the right edge, so its first ~200 units swallow the
    // handle's ~100 whole — the 🗑 ends up ON the ◢, which is the screenshot.
    assert.ok(row * chromeScale(s, 320, row, 0) > reserve,
      'unreserved, the row covers the handle entirely');
  }
});

test('what reserving the group’s ◢ costs the last tile, in numbers', () => {
  const row = CLUSTER_UNITS;
  // 55 % — a near-full target, and the ◢ is clear: ~25 px against the 28 an
  // unreserved row would have had. That is the price of the fix at the zoom a
  // board is read at, and it is small.
  const mid = chromeScreenSize(0.55, 320, row, 0, groupCornerUnits(0.55));
  assert.ok(mid >= 24 && mid < 28, `got ${mid.toFixed(1)} px at 55 %`);
  // 28 % — here it is properly paid for: ~10 px per target instead of ~15. The
  // strip's corner alone takes a third of a 320-unit tile at that zoom, and no
  // layout gives both. The alternative was a 15-px armed 🗑 sitting ON the
  // group's only size grip, at every zoom, for good.
  const far = chromeScreenSize(0.28, 320, row, 0, groupCornerUnits(0.28));
  assert.ok(far >= 9 && far < 12, `got ${far.toFixed(1)} px at 28 %`);
  assert.ok(far < chromeScreenSize(0.28, 320, row), 'and it IS a cost, not free');
  // Only the last tile pays it — every other member of the strip is unchanged.
  assert.equal(chromeScreenSize(0.28, 320, row, 0), chromeScreenSize(0.28, 320, row));
});

test('a NARROW tile at low zoom: the row slides left rather than onto the ◢', () => {
  /* The honest limit, pinned rather than hidden. A portrait picture in a strip
     is half as wide as it is tall — 160 board units at the default pin size —
     and at 28 % the group's corner alone is 100 of them. The row is already at
     its floor (it may never be drawn SMALLER than its board size, or zooming in
     would shrink the chrome into a speck), so it cannot shrink to fit what is
     left: it slides left of the handle and overhangs the neighbouring tile by
     ~62 units.
     That is the arbitrage, deliberately: a member's row is revealed on hover of
     THAT member only, so the overhang lies over a neighbour's picture for as
     long as a pointer rests there — where covering the ◢ made the group
     unresizable at every zoom, permanently.
     ⚠️ And it is NOT purely a zoom artefact, which is the part worth being
     blunt about: five 28-unit targets plus a 28-unit handle are 180 board units
     and a 160-unit tile is 160, so a portrait member overhangs its neighbour a
     little even at 100 %. Only a wider tile removes it entirely. */
  const row = CLUSTER_UNITS;
  const reserve = groupCornerUnits(0.28);
  const k = chromeScale(0.28, 160, row, 0, reserve);
  assert.equal(k, 1, 'the floor, not the cap, is what applies on a tile this narrow');
  assert.ok(row * k + reserve > 160, 'so the row does overhang — this is the known cost');
  // What it must NOT do, at any width or zoom: start before the handle ends.
  assert.ok(reserve >= CONTROL_UNITS,
    'the reserved offset is never less than the handle’s own size');
  // The overhang shrinks as the board is read closer…
  assert.ok(row * chromeScale(0.55, 160, row, 0, groupCornerUnits(0.55))
      + groupCornerUnits(0.55)
    < row * k + reserve, 'zooming in gives the neighbour its picture back');
  // …and on a tile of the default pin's width there is none at all at 100 %.
  assert.ok(row * chromeScale(1, 320, row, 0, groupCornerUnits(1))
    + groupCornerUnits(1) <= 320, 'a full-width tile fits row and handle side by side');
});

test('a nonsense zoom is not allowed to produce a nonsense control', () => {
  assert.equal(chromeScale(0, 320), 1);
  assert.equal(chromeScale(-3, 320), 1);
  assert.equal(chromeScale(NaN, 320), 1);
  assert.equal(chromeScale(0.5, NaN), 2, 'no node width ⇒ no cap, just the ideal');
});

// ---- the guard: a control is never a gesture ------------------------------

test('a press on the ✕ is a control, never a drag and never a long press', () => {
  assert.equal(nodePointerIntent(CLOSE_BUTTON, 'touch'), 'control');
  assert.equal(nodePointerIntent(CLOSE_BUTTON, 'mouse'), 'control');
  assert.ok(isNodeControlTarget(CLOSE_BUTTON));
});

test('the resize corner answers at once, finger or mouse', () => {
  assert.equal(nodePointerIntent(RESIZE_CORNER, 'touch'), 'resize');
  assert.equal(nodePointerIntent(RESIZE_CORNER, 'mouse'), 'resize');
  assert.equal(isNodeControlTarget(RESIZE_CORNER), false,
    'the corner is a GESTURE, not a button: it wants the pointer capture');
});

test('the picture itself still moves — the fix must not cost the drag', () => {
  assert.equal(nodePointerIntent(PICTURE, 'mouse'), 'move');
  assert.equal(nodePointerIntent(PICTURE, 'pen'), 'move');
  assert.equal(nodePointerIntent(PICTURE, 'touch'), 'press',
    'touch pans until the long press picks the node up');
  assert.ok(!isNodeControlTarget(PICTURE));
});

test('something with no closest() at all does not throw', () => {
  assert.equal(isNodeControlTarget(null), false);
  assert.equal(isNodeControlTarget({}), false);
  assert.equal(nodePointerIntent(null, 'touch'), 'press');
});

// ---- 🖼🖼 the grip of a GROUP of pinned images ----------------------------

const GROUP_BAR = el('[data-canvas-group-bar]', '[data-canvas-group]');
const GROUP_CLOSE = el('[data-canvas-group-bar] button', '[data-canvas-group-bar]',
  '[data-canvas-group]');

test('a group’s title bar moves the whole strip, on any pointer type', () => {
  assert.equal(nodePointerIntent(GROUP_BAR, 'mouse'), 'group-move');
  assert.equal(nodePointerIntent(GROUP_BAR, 'touch'), 'group-move',
    'the bar is the only grip a group has — a finger must not have to wait');
  assert.equal(isNodeControlTarget(GROUP_BAR), false, 'it is a gesture: it wants the capture');
});

test('a group’s own ✕ is a button, exactly like a picture’s', () => {
  assert.equal(nodePointerIntent(GROUP_CLOSE, 'touch'), 'control');
  assert.ok(isNodeControlTarget(GROUP_CLOSE),
    'without this the frame captures the pointer and the ✕ never hears the click');
});

test('the group bar stays a finger-sized grip at the zoom the board is read at', () => {
  // 400 board units tall, read at 24 % — the far end of "zoomed out".
  const h = groupBarHeight(0.24, 400);
  assert.ok(h * 0.24 >= 24, `the bar measured ${(h * 0.24).toFixed(1)} px on screen`);
  // Zoomed IN it must not balloon: a constant screen size, never smaller.
  assert.equal(groupBarHeight(2, 400), 26);
});

test('the group bar never eats the strip it labels', () => {
  // A tiny strip at a tiny zoom: the counter-scale is capped by the strip.
  assert.ok(groupBarHeight(0.05, 100) <= Math.max(26, 100 * 0.35) + 1e-9);
});

test('groupBarHeight survives nonsense', () => {
  assert.equal(groupBarHeight(0, 400), 26);
  assert.equal(groupBarHeight(NaN, 400), 26);
  assert.ok(Number.isFinite(groupBarHeight(1, NaN)));
});

/* 🪪 A control that lives in the zoomed world WITHOUT belonging to a pinned
   node — the lane header's reference thumbnail is the first one. Caught in the
   browser, not by a test: the button was correct, its handler was correct, and
   clicking it did nothing, because the frame captured the pointer and the click
   that followed was retargeted away from it. The generic marker exists so the
   next thing added to the world opts out instead of rediscovering this. */
const LANE_CONTROL = el('[data-canvas-control]');

test('a control in the world opts out of the board gesture by marker alone', () => {
  assert.ok(isNodeControlTarget(LANE_CONTROL),
    'no capture ⇒ the click reaches the button');
  assert.equal(nodePointerIntent(LANE_CONTROL, 'mouse'), 'control');
  assert.equal(nodePointerIntent(LANE_CONTROL, 'touch'), 'control',
    'and it never arms the long press either');
});

/* ✓ The pick box on a checkpoint pill — the same disease, on the control the
   board's whole generate flow runs through. Measured headless at 400 px: the
   board opens on Fit, Fit landed at 45 %, and the box reported 5 × 5 CSS px
   while the toolbar told the user to tick it. */

test('the ✓ pick box stops shrinking with the board', () => {
  // The bug, in one number.
  assert.ok(12 * 0.45 < 6, 'raw, the box is a five-pixel square at Fit zoom');
  // Counter-scaled it holds its nominal size on screen instead.
  assert.ok(pillSelectScreenSize(0.45, 60) > 10,
    'more than twice the size it had, at the zoom a phone opens on');
  assert.ok(Math.abs(pillSelectScreenSize(0.45, 200) - 12) < 1e-9,
    'on a wide pill nothing caps it: exactly its nominal 12 px');
});

test('the ✓ box never grows over the pill it sits on', () => {
  // A 60-unit pill shows a four-digit step. The box may take 55 % of it and no
  // more — larger and the leading digit goes, which is a fix already paid for.
  assert.ok(12 * pillSelectScale(0.1, 60) <= 60 * 0.55 + 1e-9);
  assert.ok(12 * pillSelectScale(0.01, 40) <= 40 * 0.55 + 1e-9);
});

test('the ✓ box is untouched at 100 % and above — and without a board at all', () => {
  // The in-card lineage graph passes no scale; a desktop board reads at 100 %+.
  assert.equal(pillSelectScale(1, 60), 1);
  assert.equal(pillSelectScale(2.5, 60), 1);
  assert.equal(pillSelectScale(0, 60), 1);
  assert.equal(pillSelectScale(NaN, 60), 1);
  assert.ok(Number.isFinite(pillSelectScale(0.4, NaN)));
});
