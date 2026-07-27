/* The two drawers the lineage graph opens must be readable on a 400-px phone.
   Both are BOTTOM SHEETS below `sm` and side drawers from `sm` up. The detail
   panel used to be `w-80` at every width, which on a 400-px screen covered 80%
   of the very board it annotates — you could read a run's settings but no
   longer see the run. Pinned here because it is invisible to every other test:
   a rewrite of the panel would silently drop the fix (a class is not behaviour,
   nothing throws), and this is the panel opened most often on a phone. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const detail = fs.readFileSync(new URL('./LineageDetailPanel.jsx', import.meta.url), 'utf8');
const gallery = fs.readFileSync(
  new URL('../shared/CheckpointGalleryPanel.jsx', import.meta.url), 'utf8');

for (const [name, src] of [['LineageDetailPanel', detail],
  ['CheckpointGalleryPanel', gallery]]) {
  test(`${name} is a bottom sheet on a phone and a side drawer from sm up`, () => {
    // Phone: full width, anchored to the bottom, never taller than 70vh so the
    // graph it describes stays on screen above it.
    assert.match(src, /fixed inset-x-0 bottom-0/);
    assert.match(src, /max-h-\[70vh\]/);
    // From `sm`: back to the original side drawer, fixed width, full height.
    assert.match(src, /sm:inset-x-auto/);
    assert.match(src, /sm:h-full/);
    assert.match(src, /sm:max-h-none/);
    assert.match(src, /sm:w-(80|\[22rem\])/);
    // No unconditional width — that is exactly the bug.
    assert.doesNotMatch(src, /className="fixed[^"]*\sw-80/);
  });
}

test('the checkpoint gallery lives in shared/, where both surfaces import it from', () => {
  // It is opened by the canvas board AND by the in-card run graph; sitting in
  // components/canvas/ made the dataset panel import a "canvas" component.
  const canvas = fs.readFileSync(
    new URL('../canvas/LineageCanvas.jsx', import.meta.url), 'utf8');
  const graph = fs.readFileSync(new URL('./RunLineageGraph.jsx', import.meta.url), 'utf8');
  assert.match(canvas, /from '\.\.\/shared\/CheckpointGalleryPanel'/);
  assert.match(graph, /from '\.\.\/shared\/CheckpointGalleryPanel'/);
  assert.ok(!fs.existsSync(new URL('../canvas/CheckpointGalleryPanel.jsx', import.meta.url)));
});
