import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

import { THUMB_SIDES } from '../../../utils/datasetThumbUrl.js';

const strip = readFileSync(new URL('./RecentPrompts.jsx', import.meta.url), 'utf8');
const modal = readFileSync(new URL('./SavedPromptsModal.jsx', import.meta.url), 'utf8');
const civitai = readFileSync(new URL('./CivitaiBrowserModal.jsx', import.meta.url), 'utf8');
const promptField = readFileSync(new URL('./PromptField.jsx', import.meta.url), 'utf8');
const canvasSetup = readFileSync(new URL('./StudioRunSetup.jsx', import.meta.url), 'utf8');
const legacyStudio = readFileSync(new URL('./LegacyDatasetStudio.jsx', import.meta.url), 'utf8');
const topics = readFileSync(new URL('../../../help/topics/pages.js', import.meta.url), 'utf8');

/** Read the numeric value of a const declaration in source text. */
const constant = (source, name) => {
  const m = new RegExp(`const ${name} = (\\d+);`).exec(source);
  assert.ok(m, `${name} must stay a named constant — a magic number is not testable`);
  return Number(m[1]);
};

test('both launch surfaces reach the browser through the same component', () => {
  // Generation-surface parity: Dataset Test Studio and Generate from the board both mount
  // RecentPrompts, which mounts the browser. Adding it on one surface only creates the silent
  // divergence users report as a bug.
  assert.match(promptField, /<RecentPrompts items=\{recentPrompts\}/);
  assert.match(canvasSetup, /<RecentPrompts items=\{recentPrompts\}/);
  assert.match(strip, /import SavedPromptsModal from '\.\/SavedPromptsModal'/);
  assert.match(strip, /<SavedPromptsModal\b/);
});

test('the browser gets the WHOLE history, the strip only its head', () => {
  // Browse all 167 must open 167 entries. Passing only the visible slice would contradict the
  // button's count.
  assert.match(strip, /<SavedPromptsModal[\s\S]*?items=\{items\}/);
  assert.match(strip, /items\.slice\(0, INLINE\)/);
  assert.ok(constant(strip, 'INLINE') > 0 && constant(strip, 'INLINE') <= 12,
    'the strip is a handful, not a wall — that is the whole point of the split');
});

test('the picture is drawn at a size a person can recognise', () => {
  // Original defect: w-8 h-10 made thumbnails 32x40 even though images are the ONLY way to
  // distinguish similar 500-character prompts. Prevent shrinking them unnoticed again.
  assert.doesNotMatch(strip, /className="w-8 h-10/,
    'the 32x40 thumbnail is the bug this browser exists to fix');
  assert.match(strip, /h-32 w-24 object-cover/);
  // This dialog and Civitai browser perform the SAME action, choosing prompts by their images, so
  // use the same image size.
  const rung = 'w-28 sm:w-36 h-40 sm:h-48';
  assert.ok(civitai.includes(rung), 'the Civitai browser is the published reference size');
  assert.ok(modal.includes(rung), 'same job as the Civitai browser, same picture size');
});

test('both thumbnail rungs are ones the server actually materialises', () => {
  // Use dataset_thumbs.THUMB_SIDES: requesting a nonexistent size does not improve sharpness; the
  // server serves another supported size instead.
  for (const [name, source] of [['strip', strip], ['modal', modal]]) {
    const side = constant(source, 'THUMB_SIDE');
    assert.ok(THUMB_SIDES.includes(side), `${name}: ${side} is not a served thumbnail rung`);
    assert.ok(side >= 192, `${name}: ${side} is below what a 96 px tile needs on a 2x screen`);
  }
});

test('every verb the strip offers has a destination in the browser', () => {
  // Porting to another surface must expose EVERY action: reuse, batch selection and deletion. An
  // action limited to the recent strip becomes unreachable beyond the sixth prompt.
  for (const verb of [/onPick\(/, /onToggleBatch\(/, /onDelete\(/]) {
    assert.match(strip, verb);
    assert.match(modal, verb);
  }
  // Offer batch selection on both views only when the host supplies it. Generate from the board
  // without that handler must not show checkboxes.
  for (const source of [strip, modal]) {
    assert.match(source, /const batchable = typeof onToggleBatch === 'function';/);
  }
});

test('ticking for the batch never writes into the prompt field', () => {
  // Batch contract: checking DESCRIBES the next launch's replay selection. Only Use prompt or
  // clicking a card fills the field.
  assert.match(modal, /onClick=\{\(\) => onToggleBatch\(p\.prompt\)\}/);
  assert.match(modal, /const use = \(p\) => \{ onPick\(p\); onClose\(\); \};/);
});

test('the browser can be searched and says what it is showing', () => {
  // At roughly 170 entries, search is essential. Use type=search consistently with Bank, Canvas
  // and Caption Lab.
  assert.match(modal, /type="search"/);
  assert.match(modal, /filterSavedPrompts\(items, query\)/);
  assert.match(modal, /\$\{shown\.length\} of \$\{total\}/);
  // An empty filtered result must explain itself; otherwise the dialog looks broken.
  assert.match(modal, /No saved prompt contains every word of/);
});

test('the browser is a real dialog', () => {
  assert.match(modal, /role="dialog" aria-modal="true"/);
  assert.match(modal, /useFocusTrap\(ref, open\)/);
  assert.match(modal, /e\.key === 'Escape'/);
  // Background click closes the dialog, but ONLY the background, never a card.
  assert.match(modal, /if \(e\.target === e\.currentTarget\) onClose\(\)/);
});

test('the browser is portalled out of the launch panel, and the reason still holds', () => {
  // Browser measurements showed the header and page fragments ABOVE the unportaled dialog, with
  // aside scrolling clipping it beyond lg. Sticky creates a stacking context that no descendant
  // z-index can escape.
  assert.match(modal, /createPortal\(<SavedPromptsPanel \{\.\.\.props\} \/>, document\.body\)/);
  // Pin the premise: if the aside stops being sticky/scrollable, reconsider the portal
  // deliberately rather than removing it incidentally.
  assert.match(legacyStudio, /<aside className="[^"]*lg:sticky[^"]*lg:overflow-auto/,
    'the launch panel still lives in a sticky, scrollable aside');
  // Mark for the responsive probe; unmarked dialogs are unmeasured.
  assert.match(modal, /data-probe-chrome="saved-prompts" data-probe-layer/);
});

test('the help topic the browser badges actually exists', () => {
  assert.match(modal, /<HelpBadge topic="studio-saved-prompts"/);
  assert.match(topics, /action\('studio-saved-prompts',/);
  // Search terms a user experiencing the original symptom would type.
  for (const kw of ['search prompts', 'find a prompt', 'preview too small', 'browse all prompts']) {
    assert.ok(topics.includes(`'${kw}'`), `help keywords must carry “${kw}”`);
  }
});
