/* Contract for the "🧬 Krea 2 Edit tuning" panel of Generate variations.

   node --test parses .js, not .jsx, so the behaviour lives in utils/kreaDials.js
   (unit-tested next to it) and this file pins the WIRING in the component source
   — the same source-text approach settingDefaults.test.js uses.

   What must not silently come back:
   - the two dials disappearing again (they had no control anywhere in the app);
   - a slider writing on every change event instead of through the debounced
     saver — a drag would then be forty PUTs to /api/settings;
   - a default typed into the JSX. These sliders offer "Reset to default", and a
     copied literal makes that button restore a value that stopped being the
     default the day it moved server-side;
   - the design comment still claiming the panel is a read-out "not a second set
     of sliders", which is what it said while these sliders sat below it. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const SRC = readFileSync(new URL('./VariationCatalog.jsx', import.meta.url), 'utf8');
const helpRegistry = readFileSync(new URL('../../help/helpRegistry.js', import.meta.url), 'utf8');

test('both dials are rendered, with the bounds the server clamps to', () => {
  assert.match(SRC, /id="krea-ref-boost"/);
  assert.match(SRC, /id="krea-identity-lora-strength"/);
  // Bounds come from the shared module, never retyped here.
  assert.match(SRC, /min=\{KREA_REF_BOOST_MIN\}[\s\S]{0,80}max=\{KREA_REF_BOOST_MAX\}/);
  assert.match(SRC,
    /min=\{KREA_IDENTITY_STRENGTH_MIN\}[\s\S]{0,110}max=\{KREA_IDENTITY_STRENGTH_MAX\}/);
});

test('every slider change goes through the debounced saver', () => {
  // Both onChange handlers call setKreaDial, which schedules; the panel must own
  // no putJson of its own for these keys.
  assert.match(SRC, /setKreaDial\('ref_boost',/);
  assert.match(SRC, /setKreaDial\('identity_lora_strength',/);
  assert.match(SRC, /kreaDialSaver\.current\.schedule\(field, value\)/);
  assert.match(SRC, /createDialSaver\(/);
  // ...and it is flushed on unmount, so leaving mid-drag still saves.
  assert.match(SRC, /kreaDialSaver\.current\?\.flush\(\)/);
});

test('the defaults are read from the server payload, never typed here', () => {
  assert.match(SRC, /defaultValueAt\(configDefaults, 'krea', 'ref_boost'\)/);
  assert.match(SRC, /defaultValueAt\(configDefaults, 'krea', 'identity_lora_strength'\)/);
  assert.match(SRC, /setConfigDefaults\(d\.config_defaults \|\| \{\}\)/);
  // The literal shipped values must not appear as a useState seed or a `?? 0.25`.
  assert.doesNotMatch(SRC, /setKreaRefBoost\]\s*=\s*useState\(\s*0?\.\d/);
  assert.doesNotMatch(SRC, /setKreaIdentityStrength\]\s*=\s*useState\(\s*[\d.]/);
});

test('the panel admits the sliders change EVERY future run', () => {
  // A control that quietly rewrites a global setting from a per-batch screen is
  // only acceptable while it says so. Keep the warning, whatever its wording.
  const panel = SRC.slice(SRC.indexOf('🧬 Krea 2 Edit tuning'));
  assert.match(panel, /apply to <b>every<\/b> Krea\s*\n?\s*run/);
});

test('the design comment no longer contradicts the code', () => {
  assert.doesNotMatch(SRC, /not a second set of sliders/);
  // The rule that DID survive is still written down: no per-run copy.
  assert.match(SRC, /PER-RUN copy would be a second truth/);
});

test('grounding_px stays a read-out with its link to Settings', () => {
  assert.match(SRC, /focus="krea-grounding"/);
  assert.doesNotMatch(SRC, /'grounding_px',\s*Number\(e\.target\.value\)/);
});

test('both dials have a help topic, and the registry carries it', () => {
  // Built by concatenation on purpose: help-registry-contract.test.mjs scans
  // every .js under src/ for help-topic attributes, so writing one literally
  // HERE would make this test file look like an instrumented component to it.
  const ref = `topic=${JSON.stringify('krea.ref_boost')}`;
  const identity = `topic=${JSON.stringify('krea.identity_lora_strength')}`;
  assert.ok(SRC.includes(ref), 'the reference-pull slider has no help topic');
  assert.ok(SRC.includes(identity), 'the identity-strength slider has no help topic');
  assert.ok(helpRegistry.includes("id: 'krea.ref_boost'"));
  assert.ok(helpRegistry.includes("id: 'krea.identity_lora_strength'"));
});
