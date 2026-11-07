/**
 * Every Studio modal must use a PORTAL to avoid stacking limits and clipping. On 2026-09-02,
 * result votes painted ABOVE Civitai prompts despite modal z-[9999]. StudioRunSetup lives inside
 * ComparisonStudio's sticky, scrollable aside: sticky creates a parent stacking context below the
 * later sibling results grid, while overflow-auto clips children. Raising child z-index cannot
 * escape; createPortal to document.body can. This SOURCE test guards a rendering rule, not visual
 * output. Source tests inspect classes, SSR has no layout, and responsive overlap probes
 * intentionally exclude data-probe-layer from pairs, so none can detect this stacking defect.
 * Screenshots verify it visually; this contract prevents future modals from repeating it.
 * Automatically enumerate every JSX component here rendering fixed inset-0 and require a portal
 * without manual registration.
 */
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import test from 'node:test';

const HERE = new URL('./', import.meta.url);

/**
 * Return {file, source} for full-screen components in this directory AND SUBDIRECTORIES. Recursion
 * is essential: the original flat scan missed video/MotionModelDialog.jsx in Video Test Studio. A
 * depth-limited guard can be bypassed accidentally by later directory organization.
 */
function fullScreenOverlays(dir = HERE, prefix = '') {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const at = new URL(entry.name + (entry.isDirectory() ? '/' : ''), dir);
    if (entry.isDirectory()) {
      out.push(...fullScreenOverlays(at, `${prefix}${entry.name}/`));
    } else if (entry.name.endsWith('.jsx')) {
      const source = readFileSync(at, 'utf8').replace(/\r\n/g, '\n');
      if (/className="fixed inset-0/.test(source)) {
        out.push({ file: prefix + entry.name, source });
      }
    }
  }
  return out;
}

// The relocated Video subtree stays in the inventory: removing the folder
// from core must not remove its modal obligations.
function studioFullScreenOverlays() {
  return [...fullScreenOverlays(),
    ...fullScreenOverlays(new URL('../../../../../bundled/video/frontend/studio/', HERE))];
}

test('the Studio modal inventory is nonempty so the guard actually checks something', () => {
  const found = studioFullScreenOverlays();
  assert.ok(found.length >= 2,
    `expected at least 2 full-screen overlays in this directory, found ${found.length} `
    + '— the detection pattern may have changed, leaving the guard ineffective');
});

test('the inventory actually DESCENDS into subdirectories', () => {
  /*
   * Pin recursive coverage itself. The original flat scan missed video/MotionModelDialog.jsx. Once
   * that file was portaled, removing recursion would still pass by checking fewer
   * already-compliant files, leaving future subdirectories unguarded. Require at least one
   * enumerated file from a subdirectory: coverage counts prove something only when exercised.
   */
  const found = studioFullScreenOverlays();
  const nested = found.filter(({ file }) => file.includes('/'));
  assert.ok(nested.length >= 1,
    'no full-screen overlays found in subdirectories: recursion is broken, '
    + `and ${found.length} top-level file(s) prove nothing about nested coverage`);
  assert.ok(nested.some(({ file }) => file.endsWith('MotionModelDialog.jsx')),
    'video/MotionModelDialog.jsx is no longer included in the inventory — '
    + `found: ${nested.map((f) => f.file).join(', ') || 'none'}`);
});

test('EVERY full-screen Studio modal is portaled to document.body', () => {
  const offenders = studioFullScreenOverlays()
    .filter(({ source }) => !(/from 'react-dom'/.test(source)
      && /createPortal\(/.test(source)
      && /document\.body/.test(source)));
  assert.deepEqual(offenders.map((o) => o.file), [],
    'These Studio modals are not portaled. Mounted under ComparisonStudio’s '
    + '`<aside lg:sticky lg:overflow-auto>`, their z-index is capped by the '
    + 'sticky stacking context and their boxes are clipped by overflow, '
    + 'allowing the page to paint over them. '
    + 'Fix: `return createPortal(<div …>, document.body)`, as in '
    + 'CaptionEditorDialog. No inner z-index can escape the parent context.');
});

test('the aside causing the stacking trap still matches the description above', () => {
  /*
   * If the panel loses sticky/overflow, the portal's rationale changes and deserves review instead
   * of leaving a stale CSS comment. Pin the cause as well as the remedy.
   */
  const owner = readFileSync(new URL('./ComparisonStudio.jsx', HERE), 'utf8').replace(/\r\n/g, '\n');
  assert.match(owner, /<aside className="[^"]*lg:sticky[^"]*lg:overflow-auto/);
});
