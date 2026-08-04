import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { markdownHeadingId } from '../../utils/headingId.js';

/* Source-text contract on the 🏷️ Caption options row, in the house style used by
   curation-ui.test.js and pipeline-ui.test.js: the file is read and asserted against,
   because these are wiring and layout facts that no pure function can hold. */

const ws = fs.readFileSync(new URL('./BankWorkspace.jsx', import.meta.url), 'utf8');

test('only the model select is width-capped, and the other four are not truncated', () => {
  // A <select> sizes itself to its widest option and has min-width:auto, so it does not
  // shrink; the ① Analyze zone has no overflow-x container, so an unbounded one pushes
  // the whole page into a horizontal scroll on a phone. But the cap has a cost: at
  // 11rem the vocabulary and length selects render "Use default (Settings ▸ Cap⌄" and
  // "Standard — the prompt as⌄", and neither carried any bound before this row existed.
  // Only the MODEL select needs it — Ollama refs run long and it overflows on its own
  // (measured: 430 px asked at a 360 px width). The other four take max-w-full with a
  // 16rem ceiling from sm up: never wider than the column, readable everywhere else.
  const capped = { 'Caption vision model': /max-w-\[11rem\]/ };
  for (const label of ['Caption scope', 'Caption engine', 'Caption vision model',
    'Caption vocabulary register', 'Caption length']) {
    const i = ws.indexOf(`aria-label="${label}"`);
    assert.ok(i > 0, `${label} select is missing`);
    // The className sits within the same element; look at the tag around it.
    const tagStart = ws.lastIndexOf('<select', i);
    const tagEnd = ws.indexOf('>', ws.indexOf('className=', i));
    const tag = ws.slice(tagStart, tagEnd);
    if (capped[label]) {
      assert.match(tag, capped[label], `${label} select lost its width bound`);
    } else {
      assert.ok(!/max-w-\[11rem\]/.test(tag),
        `${label} select is capped at 11rem and truncates its own options`);
      assert.match(tag, /max-w-full sm:max-w-\[16rem\]/,
        `${label} select has no width bound at all`);
    }
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

/* 🔄 RE-CAPTION — the destructive twin. Wiring facts no pure function can hold. */

test('the normal caption pass never sends force', () => {
  // The whole safety story rests on this: 🏷️ Caption fills blanks and nothing else.
  // A stray `force` here would turn the everyday button into the destructive one.
  const call = ws.slice(ws.indexOf('const startCaption'),
    ws.indexOf('const cancelJob'));
  assert.ok(!/force/.test(call), '🏷️ Caption must never post force');
});

test('re-caption posts force, and asks before it does', () => {
  const call = ws.slice(ws.indexOf('const startRecaption'),
    ws.indexOf('const startRecaption') + 1400);
  // The confirmation comes FIRST — after the post there is nothing left to confirm.
  const confirmAt = call.indexOf('window.confirm(captionRecaptionConfirmation');
  const postAt = call.indexOf('postJson');
  assert.ok(confirmAt > 0, 're-caption does not confirm');
  assert.ok(postAt > confirmAt, 'the request is built before the question is asked');
  assert.match(call, /force: true/);
  // …and it re-checks the inert reason itself, so a stale click cannot slip through.
  assert.match(call, /if \(captionRecaptionDisabledReason\(/);
});

test('re-caption never carries a selection', () => {
  // A selection can span pages that were never loaded, so the overwrite count is
  // unknowable client-side. This button goes inert instead of quoting a guess —
  // sending image_ids would be exactly the number-that-differs-from-the-action bug.
  const call = ws.slice(ws.indexOf('const startRecaption'),
    ws.indexOf('const startRecaption') + 1400);
  assert.ok(!/image_ids/.test(call), 're-caption must not post image_ids');
  assert.match(ws, /const recaptionInert = captionRecaptionDisabledReason\(\s*selected\.size/);
});

test('re-caption carries the same per-run options as the normal pass', () => {
  // Making the engine and model reachable on a finished bank IS the feature; a
  // re-caption that dropped them would redo the captions with the old model.
  const call = ws.slice(ws.indexOf('const startRecaption'),
    ws.indexOf('const startRecaption') + 1400);
  for (const key of ['vocabulary: captionVocab', 'length: captionLength',
    'backend: captionEngine', 'ollama_model: captionModel',
    'statuses: captionScopeStatuses(captionScope)']) {
    assert.ok(call.includes(key), `re-caption drops ${key}`);
  }
});

test('the button and the amber warning both live on the options row', () => {
  const eyebrow = ws.indexOf('<GroupLabel>Caption options</GroupLabel>');
  const button = ws.indexOf('{captionRecaptionLabel(counts, captionScope, recaptionInert)}');
  assert.ok(button > eyebrow, 're-caption must sit on the options row');
  // The pass row above it must not have grown a ninth button.
  assert.ok(ws.indexOf('onClick={startRecaption}') > eyebrow);
  // The warning is rendered, and only when the helper has something to say.
  assert.match(ws, /\{recaptionNote && \(/);
  assert.match(ws, /text-amber-400\/90">\{recaptionNote\}/);
  // The label is handed the inert reason, so a button that cannot run stops quoting
  // a number — the tooltip carries the reason instead.
  assert.match(ws, /captionRecaptionLabel\(counts, captionScope, recaptionInert\)/);
  assert.match(ws, /title=\{recaptionInert \|\| recaptionNote\}/);
});

test('re-caption has a help topic pointing at a real guide anchor', () => {
  const registry = fs.readFileSync(
    new URL('../../help/helpRegistry.js', import.meta.url), 'utf8');
  const i = registry.indexOf("action('bank-recaption'");
  assert.ok(i > 0, 'bank-recaption has no help topic');
  const entry = registry.slice(i, i + 1200);
  const anchor = /'using-the-app', '([a-z0-9-]+)'\)/.exec(entry);
  assert.ok(anchor, 'the topic has no guide anchor');
  const guide = fs.readFileSync(
    new URL('../../../../docs/guide/using-the-app.md', import.meta.url), 'utf8');
  // Slugified with the SHARED function the Guide itself uses, not a look-alike:
  // a private copy is exactly how an anchor comes to pass its own test and 404 in
  // the app.
  const headings = [...guide.matchAll(/^## (.+)$/gm)].map((m) => markdownHeadingId(m[1]));
  assert.ok(headings.includes(anchor[1]),
    `no guide heading resolves to #${anchor[1]}`);
});
