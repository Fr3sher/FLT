import test from 'node:test';
import assert from 'node:assert/strict';
import { pendingLabel, pluginActive, pluginDesired, waitForPluginBoot } from './lifecycle.js';

test('pending choices do not change the running features', () => {
  const off = { enabled: false, desired_enabled: false, active: true, state: 'loaded', pending_action: 'disable' };
  assert.equal(pluginActive(off), true);
  assert.equal(pluginDesired(off), false);
  assert.match(pendingLabel(off), /turn off after restart/);
  const on = { enabled: true, desired_enabled: true, active: false, state: 'disabled', pending_action: 'enable' };
  assert.equal(pluginActive(on), false);
  assert.equal(pluginDesired(on), true);
  assert.match(pendingLabel(on), /turn on after restart/);
  assert.equal(pluginActive({ enabled: false, state: 'loaded' }), false, 'old servers retain their existing contract');
});

test('a responsive old process is not evidence of a restart', async () => {
  let time = 0;
  let calls = 0;
  const result = await waitForPluginBoot('old', {
    now: () => time, sleep: async (ms) => { time += ms; }, intervalMs: 1,
    fetchImpl: async () => {
      calls += 1;
      if (calls === 2) throw new Error('connection reset');
      return { ok: true, json: async () => ({ boot_id: calls < 4 ? 'old' : 'new' }) };
    },
  });
  assert.equal(calls, 4);
  assert.equal(result.boot_id, 'new');
});

test('an unsuccessful restart times out without claiming success', async () => {
  let time = 0;
  await assert.rejects(waitForPluginBoot('old', {
    now: () => time, sleep: async (ms) => { time += ms; }, timeoutMs: 3, intervalMs: 1,
    fetchImpl: async () => ({ ok: true, json: async () => ({ boot_id: 'old' }) }),
  }), /not restarted yet/);
});

test('an HTTP error never confirms a boot and a cancelled page stops polling', async () => {
  const controller = new AbortController();
  let calls = 0;
  await assert.rejects(waitForPluginBoot('old', {
    signal: controller.signal,
    fetchImpl: async () => { calls += 1; return { ok: false, json: async () => ({ boot_id: 'new' }) }; },
    sleep: async () => controller.abort(),
  }), { name: 'AbortError' });
  assert.equal(calls, 1);
});

test('a missing boot identity cannot be mistaken for a successful restart', async () => {
  await assert.rejects(waitForPluginBoot(null), /Refresh the plugin list/);
});
