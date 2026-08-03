/* ✨ Upscale & improve on the ◉ Canvas board — the decision, and the wiring that
   carries it to exactly one of the shared lightbox's three hosts.

   The expensive bug this file guards is not visual. The board's pictures are
   `lora_test_image` rows and the dataset improve route resolves a
   `face_dataset_image`: two tables, two independent id spaces. Wiring the board
   to the dataset route does not throw, does not 404, and improves a real but
   UNRELATED picture. So the route is asserted here character by character. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import {
  CANVAS_IMAGE_IMPROVE, canImproveCanvasImage, canvasImproveLaunchMessage,
  canvasImproveRefusal, isCanvasImproveRow,
} from './canvasImprove.js';

const lightbox = fs.readFileSync(
  new URL('../components/shared/GeneratedImageLightbox.jsx', import.meta.url), 'utf8');
const canvas = fs.readFileSync(
  new URL('../components/canvas/LineageCanvas.jsx', import.meta.url), 'utf8');
const gallery = fs.readFileSync(
  new URL('../components/shared/CheckpointGalleryPanel.jsx', import.meta.url), 'utf8');
const preview = fs.readFileSync(
  new URL('../components/dataset/PreviewLightbox.jsx', import.meta.url), 'utf8');

// --- the decision -----------------------------------------------------------

test('a picture with a library row can be improved', () => {
  assert.equal(canvasImproveRefusal({ id: 12, dataset_id: 3 }), null);
  assert.equal(canImproveCanvasImage({ id: 12, dataset_id: 3 }), true);
});

test('a picture the board holds only as a URL is refused, with a reason', () => {
  // The lane's reference face and a pill's preview: no row, no id to send.
  // Without this guard the ✨ group would light up on a preview whose only
  // number is a STEP, and post it as if it were an image id.
  for (const img of [null, undefined, {}, { url: '/x.png', step: 900 }]) {
    assert.match(canvasImproveRefusal(img), /no library entry/);
    assert.equal(canImproveCanvasImage(img), false);
  }
});

test('an improvement cannot be improved again, and says why', () => {
  const derived = { id: 9, derivation_kind: CANVAS_IMAGE_IMPROVE };
  assert.equal(isCanvasImproveRow(derived), true);
  assert.match(canvasImproveRefusal(derived), /already an upscale/i);
  assert.equal(canImproveCanvasImage(derived), false);
  // An ordinary render is NOT one, whatever else it carries.
  assert.equal(isCanvasImproveRow({ id: 9, derivation_kind: null }), false);
});

test('the stored derivation kind matches the backend, byte for byte', () => {
  // Written into user databases: renaming it strands every existing row, so it
  // is pinned here as a value, not as a variable.
  assert.equal(CANVAS_IMAGE_IMPROVE, 'canvas_image_improve');
});

test('the launch message says WHERE the result will appear', () => {
  // Nothing on the board changes when the pass is queued, so a bare "started"
  // reads as a dead click. The message names the gallery and promises the
  // original is untouched.
  const msg = canvasImproveLaunchMessage('SeedVR2');
  assert.match(msg, /^SeedVR2 started/);
  assert.match(msg, /gallery/);
  assert.match(msg, /untouched/);
});

// --- the shared lightbox: opt-in, never inferred -----------------------------

test('the improve group renders ONLY when the host passes onImprove', () => {
  assert.match(lightbox, /\{onImprove && \(\s*<ImproveActions/);
  // Default null → the two other hosts render exactly what they always did.
  assert.match(lightbox, /onImprove = null/);
});

test('the improve group is its own component, so useCapabilities never runs for the other hosts', () => {
  // useCapabilities() THROWS outside its provider. Calling it in the lightbox
  // body would make every host pay for a feature only one of them opted into.
  assert.match(lightbox, /function ImproveActions\(\{/);
  const improveBody = lightbox.slice(lightbox.indexOf('function ImproveActions'),
    lightbox.indexOf('export default function GeneratedImageLightbox'));
  assert.match(improveBody, /const \{ caps \} = useCapabilities\(\)/);
  // The shared component's own body must never call it — that is what keeps the
  // gallery and the pill preview working with nothing added.
  const shared = lightbox.slice(
    lightbox.indexOf('export default function GeneratedImageLightbox'));
  assert.doesNotMatch(shared, /useCapabilities\(/);
});

test('the engines, their labels and the Klein note are REUSED, not restated', () => {
  assert.match(lightbox, /lightboxImproveButtons\(\{/);
  assert.match(lightbox, /import KleinImproveNote from '\.\.\/dataset\/KleinImproveNote'/);
  // The pressed engine travels to the handler, exactly like the dataset lightbox.
  assert.match(lightbox, /onImprove\(img\.id, engineId\)/);
  // Klein's amber note follows the group and only when Klein is in it — the
  // rule lives in improveEngines.js and is read from the button, never retyped.
  assert.match(lightbox, /buttons\.some\(\(b\) => b\.showKleinNote\)/);
  // No second copy of the engine names in this file.
  assert.doesNotMatch(lightbox, /SeedVR2/);
});

test('the improve buttons sit beside Download and go full width on a phone', () => {
  const footer = lightbox.slice(lightbox.indexOf('lightbox-download'));
  assert.match(footer, /lightbox-download[^]{0,1000}<ImproveActions/);
  assert.match(lightbox, /min-h-9 w-full rounded-lg border border-indigo-400\/50/);
  assert.match(lightbox, /sm:w-auto/);
});

// --- the three hosts --------------------------------------------------------

test('the CANVAS passes the handler and the dataset the Klein note needs', () => {
  assert.match(canvas, /onImprove=\{canImproveCanvasImage\(pinnedZoom\) \? handleImproveCanvasImage : undefined\}/);
  assert.match(canvas, /datasetId=\{pinnedZoom\?\.dataset_id \?\? null\}/);
});

test('the canvas posts to its OWN route, never the dataset one', () => {
  // THE assertion of this file. `/api/dataset/image/<id>/improve` resolves a
  // face_dataset_image; a board id there hits an unrelated picture and improves
  // it silently.
  assert.match(canvas, /`\/api\/canvas\/image\/\$\{imageId\}\/improve`/);
  assert.doesNotMatch(canvas, /\/api\/dataset\/image\/\$\{imageId\}\/improve/);
  assert.match(canvas, /engineId \? \{ engine: engineId \} : \{\}/);
  // The engine the SERVER echoes names the toast, so a stale tab cannot claim
  // the wrong pass ran.
  assert.match(canvas, /improveEngine\(d\.engine\)\.label/);
});

test('a failure is said out loud, never swallowed', () => {
  assert.match(canvas, /toast\.error\(d\?\.error \|\| 'Could not start the improvement'\)/);
  assert.match(canvas, /catch \(err\)[^]{0,120}toast\.error/);
});

test('the reference-face lightbox is NOT given the action', () => {
  // Same component, same file, one line apart — and a reference face has no
  // library row at all. `facts={false}` marks it; no onImprove must reach it.
  const refMount = canvas.slice(canvas.indexOf('img={refZoom'));
  const refBlock = refMount.slice(0, refMount.indexOf('/>') + 2);
  assert.doesNotMatch(refBlock, /onImprove/);
});

test('the checkpoint gallery and the pill preview are untouched', () => {
  // Zero regression: neither host passes the prop, so neither grows a button.
  // If either ever should, it is one prop — not a second implementation.
  assert.doesNotMatch(gallery, /onImprove/);
  assert.doesNotMatch(preview, /onImprove/);
});
