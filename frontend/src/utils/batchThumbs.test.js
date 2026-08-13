import test from 'node:test';
import assert from 'node:assert/strict';
import { decodeBatchThumbs } from './batchThumbs.js';

function encode(entries) {
  // entries: [[position, bytes], ...] in wire order
  const parts = [];
  for (const [pos, bytes] of entries) {
    const b = new Uint8Array(bytes);
    const head = new Uint8Array(8);
    new DataView(head.buffer).setUint32(0, pos);
    new DataView(head.buffer).setUint32(4, b.length);
    parts.push(head, b);
  }
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) { out.set(p, off); off += p.length; }
  return out.buffer;
}

test('decodeBatchThumbs returns one Blob per position in the container', () => {
  const wire = encode([[0, [1, 2, 3]], [2, [9, 9]]]);
  const got = decodeBatchThumbs(wire);
  assert.deepEqual(Object.keys(got).sort(), ['0', '2']);
  assert.ok(got['0'] instanceof Blob);
  assert.equal(got['0'].type, 'image/webp');
  assert.equal(got['0'].size, 3);
  assert.equal(got['2'].size, 2);
});

test('decodeBatchThumbs stops at a truncated trailing entry instead of crashing', () => {
  const wire = encode([[0, [1, 2, 3]]]);
  // chop the last 2 bytes so length promises more than exists
  const chopped = wire.slice(0, wire.byteLength - 2);
  const got = decodeBatchThumbs(chopped);
  // the 0 entry's length (3) now exceeds remaining bytes -> dropped
  assert.deepEqual(Object.keys(got), []);
});

test('decodeBatchThumbs tolerates an empty body', () => {
  assert.deepEqual(decodeBatchThumbs(new ArrayBuffer(0)), {});
});
