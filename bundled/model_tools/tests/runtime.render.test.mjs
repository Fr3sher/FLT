import assert from 'node:assert/strict';
import test from 'node:test';
import { createElement, renderToStaticMarkup } from '../../../frontend/tests/support/mountJsx.mjs';
const { ModelRuntimeState } = await import('../frontend/panels/ModelRuntimeCard.jsx');

const env = { ready: false, can_install: true, action: 'plugin_environment:model_tools' };
const render = (runtime, extra = {}) => {
  const previous = globalThis.window;
  globalThis.window = { lds: { api: 1, sdkVersion: '1.15.0', React: { createElement }, ui: {
    InstallRunner: ({ action, buttonLabel }) => createElement('button', { 'data-action': action }, buttonLabel),
  } } };
  try { return renderToStaticMarkup(createElement(ModelRuntimeState, { runtime, ...extra })); }
  finally { globalThis.window = previous; }
};

test('missing engine offers the owned install action without manual pip instructions', () => {
  const html = render({ ready: false, source: 'managed', environment: env, reason: 'Install the CPU engine' });
  assert.match(html, /Install CPU engine/);
  assert.match(html, /data-action="plugin_environment:model_tools"/);
  assert.match(html, /Check again/);
  assert.match(html, /No GPU or other plugin is required/);
  assert.doesNotMatch(html, /pip install|Score|ai-toolkit/);
  assert.match(html, /<details open=""/);
});

test('CPU readiness is explicit and a repair stays available', () => {
  const html = render({ ready: true, source: 'managed', torch_version: 'test-cpu', environment: { ...env, ready: true } });
  assert.match(html, /PyTorch test-cpu/);
  assert.match(html, /CPU checked/);
  assert.match(html, /Repair CPU engine/);
  assert.match(html, /Repair and installation logs/);
  assert.doesNotMatch(html, /<details open/);
});

test('running and failed installs keep logs visible even if previous readiness was true', () => {
  for (const installationState of ['queued', 'running', 'error']) {
    const html = render({ ready: true, environment: { ...env, ready: true, can_install: false } }, { installationState });
    assert.match(html, /<details open=""/);
    assert.match(html, /Repair CPU engine/);
  }
});

test('override and installation remain distinct and cannot silently change selection', () => {
  const html = render({ ready: false, source: 'override', environment: env });
  assert.match(html, /saved Python override stays selected/);
  assert.match(html, /clear the override below and save changes/);
});

test('unavailable state exposes the error and only the retry control', () => {
  const html = render(null, { error: 'Cannot contact the server' });
  assert.match(html, /role="alert"/);
  assert.match(html, /Cannot contact the server/);
  assert.doesNotMatch(html, /Install CPU engine/);
});
