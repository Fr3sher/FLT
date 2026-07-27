import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const ws = fs.readFileSync(new URL('./BankWorkspace.jsx', import.meta.url), 'utf8');

// Regression guard for the reported symptom "🎨 Pick diverse and 🎯 Similar to
// selected show EXACTLY the same thing, whatever the reference". The backend
// selectors were always distinct and reference-sensitive; the bug was that the
// grid kept showing its default facet page and only scattered invisible
// checkmarks across a 24k-image bank, so BOTH buttons looked identical. The fix
// is that each selector feeds ITS OWN returned ids into a "show selected"
// (?ids=…) grid view. These assertions lock that wiring so a refactor can't
// collapse the two buttons back into the same, ref-insensitive view.

test('each curation button feeds its OWN returned ids into the selection view', () => {
  // Diverse posts to its endpoint and shows exactly what it got back …
  assert.match(ws, /\/api\/bank\/\$\{bankId\}\/select-diverse/);
  assert.match(ws, /showCuratedSelection\(d\.image_ids\)/);
  // … and Similar posts to a DIFFERENT endpoint, keyed on the selected image as
  // the reference, and shows ITS ranked ids — not the diverse ones.
  assert.match(ws, /\/api\/bank\/\$\{bankId\}\/select-similar/);
  assert.match(ws, /const ref = \[\.\.\.selected\]\[0\]/);
  assert.match(ws, /ref_id: ref/);
  // … and 🔤 Find by text is the third of the same family: its own endpoint, its
  // own ranked ids, the same view. (Its wording/limits contract lives in
  // bankTextSearch.test.js; here we only pin that it joins the family.)
  assert.match(ws, /\/api\/bank\/\$\{bankId\}\/search-text/);
  // Every handler must route through the same "show what you selected" helper —
  // one call per selector. Bump this WITH the count when a fourth one lands; the
  // guard is that no two of them share a code path, not that there are exactly N.
  const feeds = ws.match(/showCuratedSelection\(d\.image_ids\)/g) || [];
  assert.equal(feeds.length, 3, 'each selector feeds its own result into the view');
});

test('the curated selection actually switches the grid to a ?ids= view (not scattered checkmarks)', () => {
  // showCuratedSelection flips the grid into the selection view, seeded with the
  // ids in the order the backend ranked them, and drives the fetch immediately.
  assert.match(ws, /const showCuratedSelection = \(order\) => \{/);
  assert.match(ws, /setShowSelected\(true\)/);
  assert.match(ws, /refreshImages\(filter, 0, \{ on: true, order \}\)/);
  // refreshImages builds an id-scoped request from that order when the view is
  // on — this is what makes the selection VISIBLE instead of invisible ticks.
  assert.match(ws, /ids: \(order \|\| \[\]\)\.join\(','\)/);
});
