import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// Same convention as ConceptSourcesPanel.pagination.test.js: this component has
// no rendering harness in this repo (no testing-library/jsdom), so the contract
// is pinned on the wiring code itself (state set from the backend field, reset
// on `resetScan`) rather than on phrasing.
const source = readFileSync(
  new URL('./ConceptSourcesPanel.jsx', import.meta.url), 'utf8');

test('the truncation flag is read from the scan response, not invented client-side', () => {
  assert.match(source, /setPartial\(!!body\.partial\);/);
});

test('resetting the scan also clears the truncation flag', () => {
  assert.match(source, /setPartial\(false\)/);
});

test('the truncation notice is gated on the partial flag, independently of pagination', () => {
  // Must NOT be folded into the `paginated &&` block: a truncated album dive
  // clears `paginated` (from_albums), so the notice has to render on its own
  // condition or it silently disappears exactly when it matters most.
  assert.match(source, /\{partial &&/);
  assert.doesNotMatch(source, /paginated && partial/);
});

test('the truncation cause is read from the response and reset with the scan', () => {
  assert.match(source, /setPartialReason\(body\.partialReason \|\| null\);/);
  assert.match(source, /setPartialReason\(null\)/);
});

test('a hard-cap truncation shows the calm message, distinct from the generic one', () => {
  assert.match(source, /partialReason === 'capped'/);
  // Both phrasings still live under the single `partial &&` gate.
  assert.match(source, /\{partial &&/);
  assert.match(source, /Stopped at the built-in scan limit/);
  assert.match(source, /some images may be missing/);
});

test('face-filter matches are re-keyed to the page URL so they light up for review', () => {
  // The backend keys results by the candidate URL we sent (thumbnail || page),
  // but grid selection and import read `selected` by the item's page URL. If we
  // add the candidate key directly, nothing shows as selected and import is empty.
  assert.match(source, /const key = it\.thumbnail \|\| it\.url;/);
  assert.match(source, /if \(d\.results\[key\]\?\.match\) keep\.add\(it\.url\);/);
  // the pre-fix behaviour (adding the candidate key straight to `selected`)
  assert.doesNotMatch(source,
    /for \(const \[u, r\] of Object\.entries\(d\.results\)\) if \(r\.match\) keep\.add\(u\);/);
});

test('suggesting refs drops the user into picking mode so they can adjust', () => {
  // After "Suggest best refs", the user must be able to immediately click tiles
  // to add/remove references (pickingRef stays true) instead of being stranded.
  assert.match(source, /setFaceRefs\(good\);\n\s*setPickingRef\(true\);/);
});

test('there is a clear way to finish picking references', () => {
  // A "Done picking refs" affordance must exist so picking mode isn't a trap.
  assert.match(source, /Done picking refs/);
  assert.match(source, /onClick=\{\(\) => setPickingRef\(false\)\}/);
});

test('Keep matches leaves picking mode so review clicks toggle selection', () => {
  // After the filter runs, clicking a tile should select/deselect for import
  // review, not keep adding references.
  assert.match(source, /setPickingRef\(false\);\n\s*setFaceFilterBusy\(true\);/);
});
