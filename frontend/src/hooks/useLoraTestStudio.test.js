import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

function loadHook({ family, response, postJson = async () => ({ ok: true, created: 1, seed: 1 }) }) {
  const states = [];
  const reads = [];
  const source = readFileSync(new URL('./useLoraTestStudio.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '')
    .replace('export function useLoraTestStudio', 'function useLoraTestStudio');
  const context = vm.createContext({
    useCallback: (fn) => fn, useEffect: () => {}, useRef: (value) => ({ current: value }),
    useState: (value) => {
      const index = states.push(value) - 1;
      return [value, (next) => { states[index] = next; }];
    },
    useToast: () => ({ error: () => {}, success: () => {} }),
    postJson,
    fetch: async (url) => { reads.push(url); return response; },
  });
  vm.runInContext(source, context);
  return { hook: context.useLoraTestStudio('dataset', family), states, reads };
}

test('an unsupported requested family exposes the API error without loading another pipeline', async () => {
  const h = loadHook({ family: 'anima', response: {
    ok: false, json: async () => ({ error: 'Anima is unavailable on this server.' }),
  } });
  await h.hook.refresh();
  assert.equal(h.states[0], null);
  assert.equal(h.states[2], 'Anima is unavailable on this server.');
  assert.match(h.reads[0], /family=anima$/);
});

test('a server fallback to another family is rejected', async () => {
  const h = loadHook({ family: 'qwenimage21', response: {
    ok: true, json: async () => ({ family: 'zimage', checkpoints: [{}] }),
  } });
  await h.hook.refresh();
  assert.equal(h.states[0], null);
  assert.match(h.states[2], /different model family/);
});

test('launch preserves the chosen family, model, axes and supported negative prompt', async () => {
  let body;
  const h = loadHook({ family: 'qwenimage21', response: {
    ok: true, json: async () => ({ family: 'qwenimage21' }),
  }, postJson: async (_url, payload) => { body = payload; return { ok: true, created: 1, seed: 42 }; } });
  await h.hook.launch(['trained.safetensors'], [0.85], 42, 'A quiet garden',
    ['qwen-base.safetensors'], ['1:1'], [4], [30], [], 1, { negative: 'blurry' });
  assert.equal(body.family, 'qwenimage21');
  assert.equal(body.negative, 'blurry');
  assert.deepEqual(body.z_models, ['qwen-base.safetensors']);
  assert.deepEqual(body.steps, [30]);
  assert.equal(h.states[0].family, 'qwenimage21');
});
