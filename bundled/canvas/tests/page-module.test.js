import '../../../frontend/tests/plugin-sdk-host.mjs';
import test from 'node:test';
import assert from 'node:assert/strict';

test('the independently owned Canvas page resolves every public SDK import', async () => {
  const page = await import('../frontend/pages/CanvasPage.jsx');
  assert.equal(typeof page.default, 'function');
});
