/* 🖼🗑 Deleting from a checkpoint's gallery — the parts a screenshot cannot show.
 *
 * The picking itself is trivial; what is not is (a) a selection that outlives
 * the images it points at, (b) a confirmation that forgets to say the images
 * also leave the Test Studio, and (c) a toast that claims a success the backend
 * did not report. Each of those is a silent wrong, so each is pinned here.
 *
 * The panel's own guarantees that live in the JSX (deletion unreachable without
 * Select mode, the phone layout) are pinned in lineagePanelsResponsive.test.js,
 * which reads the file as text — node --test cannot parse JSX.
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  allGalleryImageIds, galleryDeleteConfirmation, galleryDeleteSummary,
  pruneGallerySelection, toggleGalleryImage,
} from './gallerySelection.js';

const IMAGES = [{ id: 3 }, { id: 7 }, { id: 11 }];

test('picking toggles without mutating the previous set', () => {
  const a = new Set([3]);
  const b = toggleGalleryImage(a, 7);
  assert.deepEqual([...a], [3]);           // React state is never mutated
  assert.deepEqual([...b].sort(), [3, 7]);
  assert.deepEqual([...toggleGalleryImage(b, 3)], [7]);
});

test('select all / clear all cover exactly what is listed', () => {
  assert.deepEqual([...allGalleryImageIds(IMAGES)].sort((x, y) => x - y), [3, 7, 11]);
  assert.deepEqual([...allGalleryImageIds(null)], []);
  // A row with no id (never happens today, but a payload change is cheap) is not
  // turned into an `undefined` in the delete request.
  assert.deepEqual([...allGalleryImageIds([{ id: 5 }, {}])], [5]);
});

test('a refresh drops ids the gallery no longer lists', () => {
  // Deleted from the Test Studio while the panel was open: the id must not stay
  // armed, or the next 🗑 click deletes something invisible.
  const kept = pruneGallerySelection(new Set([3, 999]), IMAGES);
  assert.deepEqual([...kept], [3]);
  assert.deepEqual([...pruneGallerySelection(new Set([3]), [])], []);
});

test('the confirmation says the Test Studio loses them too', () => {
  const one = galleryDeleteConfirmation(1, 'trash');
  assert.match(one.title, /Delete this image\?/);
  assert.ok(one.lines.some((l) => /Test Studio/.test(l)),
    'the shared-row consequence must be stated before the click');
  const many = galleryDeleteConfirmation(4, 'trash');
  assert.match(many.title, /Delete these 4 images\?/);
});

test('the confirmation names WHICH of the three destinations, before arming', () => {
  const os = galleryDeleteConfirmation(2, 'trash');
  assert.ok(os.lines.some((l) => /Recycle Bin/.test(l)));
  assert.equal(os.destructive, false);

  const app = galleryDeleteConfirmation(2, 'app_trash');
  assert.ok(app.lines.some((l) => /app's Trash/.test(l)));
  assert.equal(app.destructive, false);

  // Unknown / missing mode fails LOUD, not silently reassuring: an answer that
  // never arrived must not read as "recoverable".
  const gone = galleryDeleteConfirmation(2, undefined);
  assert.ok(gone.lines.some((l) => /deleted for good/.test(l)));
  assert.equal(gone.destructive, true);
});

test('the summary reports what the backend did, not what was asked', () => {
  assert.match(galleryDeleteSummary({ rows_removed: 3, mode: 'app_trash', skipped: [] }),
    /3 images deleted · moved to the app's Trash/);
  assert.match(galleryDeleteSummary({ rows_removed: 1, mode: 'trash', skipped: [] }),
    /^1 image deleted/);
  // A locked file keeps its row: the toast has to admit it rather than claim a
  // clean sweep.
  assert.match(
    galleryDeleteSummary({ rows_removed: 1, mode: 'trash', skipped: [{ id: 9 }] }),
    /1 skipped/);
  assert.match(galleryDeleteSummary({ rows_removed: 0, skipped: [{ id: 9 }] }),
    /^Nothing was deleted · 1 skipped$/);
  assert.match(galleryDeleteSummary(null), /Nothing was deleted/);
});
