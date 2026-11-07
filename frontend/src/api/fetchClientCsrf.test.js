import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { fetchWithCsrfRetry, postJson, postForm, CSRF_EXPIRED_MESSAGE } from './fetchClient.js';

const originalFetch = globalThis.fetch;
const originalDocument = globalThis.document;
afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.document = originalDocument;
});

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json' },
});
const rejected = () => new Response('The CSRF tokens do not match.', {
  status: 400, headers: { 'Content-Type': 'text/html' },
});

for (const multipart of [false, true]) {
  test(`CSRF recovery uses the server token despite another app's cookie (${multipart ? 'form' : 'JSON'})`, async () => {
    globalThis.document = { cookie: 'csrf_token=other-app', querySelector: () => null };
    const calls = [];
    globalThis.fetch = async (url, options) => {
      calls.push({ url, options });
      if (url === '/api/csrf-token') {
        assert.equal(options.cache, 'no-store');
        // Another local tab overwrites the shared cookie before the retry.
        globalThis.document.cookie = 'csrf_token=other-app-again';
        return json({ csrf_token: 'this-app' });
      }
      if (calls.length === 1) return rejected();
      assert.equal(options.headers['X-CSRFToken'], 'this-app');
      assert.equal(options.headers['x-lds-plugin-admin'], 'fixture-admin');
      if (multipart) {
        assert.deepEqual(options.body.getAll('csrf_token'), ['this-app']);
        assert.equal(options.body.get('file'), 'fixture');
      } else {
        assert.deepEqual(JSON.parse(options.body), { apply: true });
      }
      return json({ ok: true, restarting: true });
    };
    const options = { headers: { 'X-LDS-Plugin-Admin': 'fixture-admin' } };
    const form = new FormData();
    form.set('file', 'fixture');
    const result = multipart
      ? await postForm('/api/plugins/install', form, options)
      : await postJson('/api/plugins/apply', { apply: true }, options);
    assert.equal(result.ok, true);
    assert.equal(calls.length, 3);
    assert.ok(calls.every(({ options }) => options.credentials === 'include'));
  });
}

test('a repeated CSRF rejection stops after one retry', async () => {
  globalThis.document = { cookie: 'csrf_token=stale', querySelector: () => null };
  let mutations = 0;
  globalThis.fetch = async url => {
    if (url === '/api/csrf-token') return json({ csrf_token: 'fresh' });
    mutations += 1;
    return rejected();
  };
  await assert.rejects(postJson('/api/plugins/apply', {}), { message: CSRF_EXPIRED_MESSAGE });
  assert.equal(mutations, 2);
});

test('application refusals and network failures never replay the restart', async () => {
  globalThis.document = { cookie: 'csrf_token=fixture', querySelector: () => null };
  for (const status of [400, 403, 409, 500]) {
    let calls = 0;
    globalThis.fetch = async () => { calls += 1; return json({ error: 'refused' }, status); };
    await assert.rejects(postJson('/api/plugins/apply', {}), /refused/);
    assert.equal(calls, 1);
  }
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error('disconnected'); };
  await assert.rejects(fetchWithCsrfRetry('/api/plugins/apply', {
    method: 'POST', headers: { 'X-CSRFToken': 'fixture' },
  }), /disconnected/);
  assert.equal(calls, 1);
});
