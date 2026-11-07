/**
 * A plugin route's lazy component is created ONCE and kept — the invariant
 * behind the spinner that never ended on the first plugin route (#/video-bank,
 * 2026-09-05): a `lazy()` made inside a render that suspends is remade on the
 * retry, with a fresh import each time. Identity across calls is the whole
 * contract, so it is what these tests hold; the App's route host must reach
 * its component through this cache and never build one in render.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { lazyRoute, resetLazyRoutes } from './lazyRoute.js';

const importer = () => new Promise(() => {});   // a chunk that never arrives
const other = () => new Promise(() => {});

test('the same route key yields the SAME lazy component, call after call', () => {
  resetLazyRoutes();
  const first = lazyRoute('video:/video-bank', importer);
  assert.equal(lazyRoute('video:/video-bank', importer), first, 'a retry after a suspend must find the component it suspended on');
  assert.equal(lazyRoute('video:/video-bank', other), first, 'the key owns the component, not the importer identity');
});

test('a different route gets a component of its own', () => {
  resetLazyRoutes();
  assert.notEqual(lazyRoute('video:/video-bank', importer), lazyRoute('video:/video-dataset/:id', other));
});

test('what comes back is a React lazy component', () => {
  resetLazyRoutes();
  const Page = lazyRoute('x:/x', importer);
  assert.equal(Page.$$typeof, Symbol.for('react.lazy'));
});
