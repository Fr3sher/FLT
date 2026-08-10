import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { DATASET_TINTS, tintIndexFor, tintFor } from './datasetTint.js';

const src = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), 'utf8');

/* Hue (0-360) and HSL saturation of a #rrggbb. A neutral has no hue worth
   comparing, so it is exempted from the spacing rules below. */
function hs(hex) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  const max = Math.max(r, g, b); const min = Math.min(r, g, b); const d = max - min;
  const l = (max + min) / 2;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (!d) return { hue: null, sat: 0 };
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { hue: ((h * 60) % 360 + 360) % 360, sat: s };
}
const gap = (a, b) => Math.min(Math.abs(a - b), 360 - Math.abs(a - b));
const SATURATED = 0.35;

test('every tint is a distinct hex colour', () => {
  assert.ok(DATASET_TINTS.length >= 6);
  assert.equal(new Set(DATASET_TINTS).size, DATASET_TINTS.length);
  for (const c of DATASET_TINTS) assert.match(c, /^#[0-9a-f]{6}$/);
});

test('no two saturated tints are within 25° of hue', () => {
  // "Different colour per dataset" is worth nothing if two of them read alike.
  const hues = DATASET_TINTS.map(hs).filter((x) => x.hue !== null && x.sat >= SATURATED);
  for (let i = 0; i < hues.length; i += 1) {
    for (let j = i + 1; j < hues.length; j += 1) {
      assert.ok(gap(hues[i].hue, hues[j].hue) >= 25,
        `${Math.round(hues[i].hue)}° and ${Math.round(hues[j].hue)}° are too close`);
    }
  }
});

test('a dataset keeps the same tint across calls — the association is learnable', () => {
  for (const id of [1, 42, 'char-alpha', 'b7f1']) {
    assert.equal(tintIndexFor(id), tintIndexFor(id));
    assert.equal(tintFor(id), DATASET_TINTS[tintIndexFor(id)]);
  }
});

test('consecutive numeric ids never share a tint', () => {
  // The whole board is usually datasets created one after another. `id % N`
  // (not a hash) is what makes a full palette's worth of them all different.
  const n = DATASET_TINTS.length;
  for (const start of [0, 1, 7, 103]) {
    const seen = new Set();
    for (let i = 0; i < n; i += 1) seen.add(tintIndexFor(start + i));
    assert.equal(seen.size, n);
  }
});

test('a string id still lands in range, and a missing one does not crash', () => {
  for (const id of ['dataset-zz', '', null, undefined, 'x'.repeat(200)]) {
    const i = tintIndexFor(id);
    assert.ok(Number.isInteger(i) && i >= 0 && i < DATASET_TINTS.length, String(id));
  }
});

test('the palette avoids the three hues that already MEAN something', () => {
  // amber = superseded, cyan = external LoRA, violet = blend provenance. A tint
  // sitting on one of those would turn "whose edge is this" into "what kind of
  // edge is this", which is a worse board than the grey one.
  const reserved = {
    amber: hs('#fbbf24').hue, external: hs('#22d3ee').hue, blend: hs('#a855f7').hue,
  };
  for (const c of DATASET_TINTS) {
    const { hue, sat } = hs(c);
    if (hue === null || sat < SATURATED) continue; // a grey claims no meaning
    for (const [name, r] of Object.entries(reserved)) {
      assert.ok(gap(hue, r) >= 25,
        `${c} (${Math.round(hue)}°) collides with ${name} (${Math.round(r)}°)`);
    }
  }
});

test('edges take the tint, but the three meaningful colours still win', () => {
  const edges = src('components/dataset/lineageEdges.jsx');
  assert.match(edges, /export function LineageEdges\(\{ edges, isLit, tintIndex = null \}\)/);
  // external → blend → superseded are all tested BEFORE the tinted spine/normal.
  const pick = edges.slice(edges.indexOf('const grad ='), edges.indexOf('const grad =') + 260);
  assert.match(pick, /e\.external[\s\S]*e\.blend[\s\S]*e\.superseded[\s\S]*spineGrad[\s\S]*normalGrad/);
  // The gradient ids the tints resolve to are actually defined.
  assert.match(edges, /id=\{`lds-edge-tint-\$\{i\}`\}/);
  assert.match(edges, /id=\{`lds-edge-tintspine-\$\{i\}`\}/);
});

test('the canvas passes each lane its own tint, the in-card graph passes none', () => {
  const canvas = src('components/canvas/LineageCanvas.jsx');
  const inCard = src('components/dataset/RunLineageGraph.jsx');
  assert.equal((canvas.match(/tintIndex=\{tintIndexFor\(lane\.datasetId\)\}/g) || []).length, 2);
  assert.doesNotMatch(inCard, /tintIndex/);
});
