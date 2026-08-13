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
