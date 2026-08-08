/* 📱 The ◉ LoRA Canvas on a small screen.

   The board is used from a phone daily — over Tailscale, at 400 to 1060 px —
   and it had never had a responsive pass: the drawers switched to fixed-width
   side panels at 640 px, the toolbar's targets were 36 px, the gesture list was
   `hidden` below a laptop, and the page blurb pushed the board's bottom edge
   past the fold on every load.

   Pinned as TEXT because `node --test` cannot parse JSX and because none of it
   is behaviour: a class is not a function, nothing throws when it goes, and the
   symptom only appears on a device the test suite never renders on. Every
   assertion below is a measurement that was taken headless at 400/768/1060 px,
   not a preference. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const canvas = fs.readFileSync(new URL('./LineageCanvas.jsx', import.meta.url), 'utf8');
const page = fs.readFileSync(new URL('../../pages/CanvasPage.jsx', import.meta.url), 'utf8');
const filter = fs.readFileSync(new URL('./CanvasDatasetFilter.jsx', import.meta.url), 'utf8');

/* The zoom/Fit/Tidy/Generate row is the ONLY way to zoom without a wheel. At
   36 px its buttons sat under the ~40 px a finger lands on, and a miss lands on
   the board and pans it — which reads as "the zoom buttons are unreliable". */
test('the board toolbar carries 40-px targets on a phone and 36 on a desktop', () => {
  const bar = canvas.slice(canvas.indexOf('aria-label="Zoom out"') - 400,
    canvas.indexOf('data-testid="canvas-deploy-legend"'));
  // − and + are square; Fit, Tidy up and 🎨 Generate are tall only.
  assert.equal((bar.match(/h-10 w-10 [^"']*lg:h-9 lg:w-9/g) || []).length, 2);
  assert.ok((bar.match(/h-10 [^"'+]*lg:h-9/g) || []).length >= 3);
  // No 36-px target left in the row at phone width.
  assert.doesNotMatch(bar, /className="flex h-9 /);
  // …and it still WRAPS rather than overflowing: 400 px cannot hold this row.
  // The wrap moved UP one level when the row became a floating bar ON the board
  // instead of chrome stacked above it: the pill is the flex container now, and
  // the old inner div is `contents` so its buttons stay direct flex items. What
  // is pinned is the PROPERTY (it wraps, it does not overflow), not the element
  // that happens to own it — pinning the old class string would have made the
  // move look like a regression while 400 px still worked perfectly.
  assert.match(canvas, /pointer-events-auto inline-flex max-w-full flex-wrap items-center gap-1\.5/);
  assert.match(canvas, /className="contents"/);
});

/* The gesture list is the board's entire documentation. It was `lg:inline` with
   no small-screen counterpart, so on the one device with no wheel, no hover
   title and no shift key it did not exist at all. */
test('the board gestures are reachable below lg, from a single source', () => {
  assert.match(canvas, /const BOARD_GESTURES = \(/);
  // Inline from lg up…
  assert.match(canvas, /ml-auto hidden [^"]*lg:inline[^]{0,80}\{BOARD_GESTURES\}/);
  // …and behind a one-tap disclosure below it.
  // …one more chip in a row that already wraps, never a row of its own: every
  // pixel above the frame is a pixel of board pushed under the fold.
  assert.match(canvas, /<details className="lg:hidden">/);
  assert.match(canvas, /<summary[^>]*>[^]{0,200}Gestures/);
  // Written ONCE: two copies would drift the first time a gesture is added.
  assert.equal((canvas.match(/\{BOARD_GESTURES\}/g) || []).length, 2);
  // Touch is named: a phone has no wheel and cannot shift-click.
  assert.match(canvas, /wheel or pinch to zoom/);
  assert.match(canvas, /on touch, hold it first/);
});

/* 400 px × 800: the page chrome above the board measured 304 px, the frame is
   65vh = 520, and 304 + 520 > 800 — the board's bottom edge never fit. The
   blurb is 72 of those pixels and it explains the page exactly once. */
test('the canvas page drops its blurb on a phone, never its help', () => {
  assert.match(page, /className="mt-1 hidden text-content-muted text-\[0\.75rem\] sm:block"/);
  // The ? badge stays at every width, so the explanation is still one tap away.
  assert.match(page, /<HelpBadge topic="page-canvas" \/>/);
});

/* …and the frame itself gives back the last 5vh, so the WHOLE board — bottom
   edge included — is on screen at 400×800 rather than hanging under the fold.
   A board whose bottom you have to scroll the page to reach is a board whose
   pan gesture competes with the page's scroll. */
test('the board frame fits the fold on a phone and is unchanged from sm up', () => {
  // 60vh was the height left AFTER ~290 px of chrome — the zoom row, the colour
  // key, the gestures sheet, the run tracker and the dataset filter, all stacked
  // above the frame at 400 px. Every one of them now floats ON the board, so the
  // frame takes that space back: the number went up because the reason it was
  // small went away. Still short of the fold, which is the actual contract —
  // a board whose bottom edge you have to scroll to is a board whose pan gesture
  // fights the page's, and it is what makes ✦ Fit mean anything.
  assert.match(canvas, /h-\[72vh\] min-h-\[380px\][^"]*sm:h-\[76vh\]/);
  // The overlays must stay SIBLINGS of the frame, never children: the frame owns
  // the pointer handlers and `touch-none`, so a control nested inside it would
  // hand every tap to the board underneath.
  assert.match(canvas, /pointer-events-none absolute inset-x-0 top-0 z-20/);
  assert.match(canvas, /pointer-events-none absolute inset-x-0 bottom-0 z-20/);
});

/* The 🎨 Generate chip carries the pick count, which is what makes closing the
   sheet a cheap gesture: the picks are still visible from the board. */
test('the Generate chip keeps showing the pick count with the panel closed', () => {
  assert.match(canvas, /aria-pressed=\{panelOpen\}/);
  assert.match(canvas, /\{picks\.length > 0 && \([^]{0,200}\{picks\.length\}/);
});

/* Regression guard on a fix that was won once already: the dataset filter opens
   FOLDED at every width. Unfolded it costs a row plus a wrapping checkbox per
   dataset, which on a phone buries the board under the thing that filters it. */
test('the dataset filter still opens folded', () => {
  assert.match(filter, /useState\(\s*\(\) => readCanvasFilterOpen\(/);
  assert.doesNotMatch(filter, /innerWidth/);
});
