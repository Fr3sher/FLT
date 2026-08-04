import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

/* Source-text contract on the 🏷️ Caption options row, in the house style used by
   curation-ui.test.js and pipeline-ui.test.js: the file is read and asserted against,
   because these are wiring and layout facts that no pure function can hold. */

const ws = fs.readFileSync(new URL('./BankWorkspace.jsx', import.meta.url), 'utf8');

test('the four caption selects are all bounded for a 400 px toolbar', () => {
  // A <select> sizes itself to its widest option and has min-width:auto, so it does
  // not shrink; the ① Analyze zone has no overflow-x container, so an unbounded one
  // pushes the whole page into a horizontal scroll on a phone. max-w-[11rem] is the
  // bound the grid Sort select already carries (grid-sort-contract.test.mjs).
  for (const label of ['Caption scope', 'Caption engine', 'Caption vision model',
    'Caption vocabulary register', 'Caption length']) {
    const i = ws.indexOf(`aria-label="${label}"`);
    assert.ok(i > 0, `${label} select is missing`);
    // The className sits within the same element; look at the tag around it.
    const tagStart = ws.lastIndexOf('<select', i);
    const tagEnd = ws.indexOf('>', ws.indexOf('className=', i));
    assert.match(ws.slice(tagStart, tagEnd), /max-w-\[11rem\]/,
      `${label} select has no width bound`);
  }
});

test('the caption options live on their own row, not on the pass-button row', () => {
  const eyebrow = ws.indexOf('<GroupLabel>Caption options</GroupLabel>');
  assert.ok(eyebrow > 0, 'the Caption options group label is missing');
  const passes = ws.indexOf('<GroupLabel>Analysis passes</GroupLabel>');
  assert.ok(passes > 0 && passes < eyebrow, 'the options row must follow the pass row');
  // …and the caption button must NOT be inside it.
  assert.ok(ws.indexOf('captionButtonLabel(selected.size') < eyebrow);
});

test('every new option is spread-if-set, so an untouched run posts the old body', () => {
  const call = ws.slice(ws.indexOf('const startCaption'),
    ws.indexOf('const cancelJob'));
  assert.match(call, /\.\.\.\(captionEngine \? \{ backend: captionEngine \} : \{\}\)/);
  assert.match(call, /\.\.\.\(captionModel \? \{ ollama_model: captionModel \} : \{\}\)/);
  assert.match(call, /captionScopeStatuses\(captionScope\)/);
  // The scope key is omitted while a selection is live — the server intersects the
  // two, so sending both could caption fewer images than the button promises.
  assert.match(call, /!selected\.size && captionScopeStatuses\(captionScope\)/);
});

test('the engine picker never offers "none" — captioning with nothing is not a pass', () => {
  const i = ws.indexOf('aria-label="Caption engine"');
  const block = ws.slice(i, i + 600);
  assert.match(block, /ENGINE_OPTIONS\.filter\(\(o\) => o\.id !== 'none'\)/);
});

test('the model picker is inert unless the engine can reach Ollama, and keeps an unknown model', () => {
  assert.match(ws, /const ollamaPicksApply = OLLAMA_RELEVANT\.has\(captionEngine\)/);
  const i = ws.indexOf('aria-label="Caption vision model"');
  assert.match(ws.slice(i - 400, i + 400), /disabled=\{live \|\| !ollamaPicksApply\}/);
  // A model pulled elsewhere must stay selectable rather than be dropped in silence.
  assert.match(ws, /captionModelChoices = captionModel && !ollamaModels\.includes\(captionModel\)/);
});

test('the model list comes from its own always-200 endpoint, not from capabilities', () => {
  // caps.ollama carries the CONFIGURED model, never the installed list.
  assert.match(ws, /apiFetch\('\/api\/ollama\/models'\)\.catch\(\(\) => \(\{ models: \[\] \}\)\)/);
});

test('the explicit warning judges the model that will RUN, and points at a real place', () => {
  // Warning about the configured model while the run uses an override is worse than
  // not warning at all.
  assert.match(ws, /const visionModel = captionModel \|\| caps\.ollama\?\.vision_model \|\| ''/);
  // The old sentence sent people to Settings ▸ Captioning & quality, which holds the
  // ENGINE selector; the vision model field lives in Local tools.
  const warn = ws.slice(ws.indexOf("captionVocab === 'explicit'"),
    ws.indexOf("captionVocab === 'explicit'") + 1200);
  assert.ok(!/Captioning &amp; quality/.test(warn),
    'the explicit warning still points at the wrong Settings section');
  assert.match(warn, /section="local-tools" focus="ollama-vision-model"/);
});

test('no surface in the bank sends people to the wrong tab for the vision model', () => {
  const wm = fs.readFileSync(new URL('./bankWatermark.js', import.meta.url), 'utf8');
  for (const [name, src] of [['BankWorkspace.jsx', ws], ['bankWatermark.js', wm]]) {
    for (const m of src.matchAll(/[^\n]*vision model[^\n]*/gi)) {
      assert.ok(!/Settings ▸ Captioning/.test(m[0]),
        `${name}: "${m[0].trim()}" points at the engine section, not Local tools`);
    }
  }
});
