import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// Exercise the real hook with synchronous React hooks and controlled HTTP.
function loadHook(postJson) {
  const errors = [];
  const successes = [];
  const reads = [];
  const source = fs.readFileSync(new URL('./useStudioRun.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '')
    .replace('export function useStudioRun', 'function useStudioRun');
  const context = vm.createContext({
    useCallback: fn => fn,
    useEffect: () => {},
    useState: value => [value, () => {}],
    useToast: () => ({ error: msg => errors.push(msg), success: msg => successes.push(msg) }),
    postJson,
    fetch: async url => { reads.push(url); return { ok: true, json: async () => ({ resumable: 1 }) }; },
  });
  vm.runInContext(source, context);
  return { run: context.useStudioRun('saved-run'), errors, successes, reads };
}

test('Resume rejection is shown and status refreshed without an unhandled promise', async () => {
  const h = loadHook(async () => { throw new Error('ComfyUI is answering too slowly'); });
  const result = await h.run.resume();
  assert.equal(result.ok, false);
  assert.deepEqual(h.errors, ['ComfyUI is answering too slowly']);
  assert.deepEqual(h.successes, []);
  assert.deepEqual(h.reads, ['/api/studio/run/saved-run/status']);
});

test('Resume success reports the restored cells and refreshes status', async () => {
  const h = loadHook(async url => {
    assert.equal(url, '/api/studio/run/saved-run/resume');
    return { ok: true, resumed: 2 };
  });
  assert.equal((await h.run.resume()).resumed, 2);
  assert.deepEqual(h.errors, []);
  assert.deepEqual(h.successes, ['2 cell(s) restarted with their settings']);
  assert.equal(h.reads.length, 1);
});
