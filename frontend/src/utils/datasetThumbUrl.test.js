import test from 'node:test';
import assert from 'node:assert/strict';

import { datasetThumbUrl, THUMB_SIDES } from './datasetThumbUrl.js';

/* The rewrite that stops the app decoding 1-4 megapixel PNGs to paint 96 px
   tiles. Two halves matter equally: it must hit every dataset image URL the
   backend stamps, and it must not touch anything else — a tile that 404s
   because a helper "improved" a URL it did not understand is worse than a
   heavy tile. */

test('an /img/ URL becomes a /thumb/ URL carrying the requested side', () => {
  assert.equal(datasetThumbUrl('/api/dataset/12/img/shot.png', 320),
    '/api/dataset/12/thumb/shot.png?s=320');
});

test('the default side is 512 — the biggest tile any surface draws', () => {
  assert.equal(datasetThumbUrl('/api/dataset/3/img/a.webp'),
    '/api/dataset/3/thumb/a.webp?s=512');
});

test('every side this app asks for is a rung the server materialises', () => {
  // A rung that does not exist would be snapped UP server-side: the tile would
  // still work, just heavier than the caller believes. Catch it here instead.
  for (const side of [256, 320, 384, 512]) {
    assert.ok(THUMB_SIDES.includes(side), `${side} is not on the ladder`);
  }
});

test('an in-place crop keeps its ?v= cache-buster', () => {
  // Without it the BROWSER keeps painting the pre-crop tile it already holds —
  // the server-side mtime key cannot help with a cache that never asks.
  const out = datasetThumbUrl('/api/dataset/12/img/shot.png?v=7', 256);
  const params = new URLSearchParams(out.split('?')[1]);
  assert.equal(out.split('?')[0], '/api/dataset/12/thumb/shot.png');
  assert.equal(params.get('v'), '7');
  assert.equal(params.get('s'), '256');
});

test('a percent-encoded filename survives the rewrite untouched', () => {
  assert.equal(datasetThumbUrl('/api/dataset/9/img/a%20b%2Bc.png', 256),
    '/api/dataset/9/thumb/a%20b%2Bc.png?s=256');
});

test('an explicit ?s= in the source URL is replaced, not duplicated', () => {
  const out = datasetThumbUrl('/api/dataset/1/img/x.png?s=128', 512);
  assert.equal(out, '/api/dataset/1/thumb/x.png?s=512');
});

test('anything that is not a dataset image URL comes back verbatim', () => {
  for (const url of ['/api/bank/4/file/9', '/api/dataset/12/thumb/shot.png?s=320',
    'blob:http://localhost/abc', 'data:image/png;base64,AAAA',
    'https://example.test/x.png', '/api/datasets/12/img/shot.png',
    '/api/dataset/abc/img/shot.png']) {
    assert.equal(datasetThumbUrl(url, 320), url, url);
  }
});

test('a missing url stays missing instead of becoming a broken request', () => {
  assert.equal(datasetThumbUrl(null, 320), null);
  assert.equal(datasetThumbUrl(undefined, 320), undefined);
  assert.equal(datasetThumbUrl('', 320), '');
});
