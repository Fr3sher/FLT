import assert from 'node:assert/strict'
import test, { before, after } from 'node:test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../../../frontend/package.json', import.meta.url))
const { build } = require('esbuild')
const { chromium } = require('playwright-core')
const { findHeadlessShell } = await import('../../../frontend/scripts/responsiveProbe.mjs')
const executablePath = findHeadlessShell(fs, path)
const options = { skip: !executablePath && 'Headless Chromium is required for SeedVR2 preparation interactions' }
let browser, code

before(async () => {
  if (!executablePath) return
  const frontend = fileURLToPath(new URL('../../../frontend/', import.meta.url))
  const result = await build({
    stdin: { resolveDir: frontend, loader: 'jsx', contents: `
      import React from 'react';
      import { createRoot } from 'react-dom/client';
      import Card from '../bundled/seedvr2/frontend/panels/SeedVr2InstallCard.jsx';
      const proof = window.proof = { calls: [], done: 0, errors: [], polls: 0, initialRead: false };
      const schedule = window.setTimeout.bind(window);
      window.setTimeout = (fn, delay, ...args) => schedule(fn, delay === 1200 ? 15 : delay, ...args);
      proof.request = async (method, url, body) => {
        proof.calls.push({ method, url, body });
        if (method === 'POST') {
          if (proof.mode === 'refused') throw new Error('ComfyUI uses Python 3.11; this recipe requires Python >=3.12.');
          return proof.reply;
        }
        if (!proof.initialRead) { proof.initialRead = true; return { statuses: proof.resume || {} }; }
        proof.polls++;
        if (proof.mode === 'offline') throw new Error('Connection unavailable');
        if (proof.mode === 'idle') return { statuses: {} };
        return { statuses: Object.fromEntries(proof.reply.plan.map(action => [action, { state: 'success' }])) };
      };
      proof.mount = (reply, mode, overrides, resume) => {
        proof.reply = reply; proof.mode = mode; proof.resume = resume;
        const caps = { comfyui: { dir_valid: true, reachable: true, seedvr2_nodes_installed: false,
          seedvr2_nodes_missing: ['SeedVR2'], seedvr2_missing: ['seedvr2_model', 'seedvr2_vae'],
          seedvr2_ready: false, ...overrides } };
        const root = createRoot(document.getElementById('root'));
        const done = () => {
          proof.done++;
          if (proof.recheckedCaps) root.render(<Card caps={proof.recheckedCaps} onDone={done} />);
        };
        root.render(<Card caps={caps} onDone={done} />);
      };
    ` },
    bundle: true, write: false, platform: 'browser', format: 'iife', jsx: 'automatic',
    nodePaths: [path.join(frontend, 'node_modules')], define: { 'process.env.NODE_ENV': '"development"' },
    plugins: [{ name: 'controlled-seed-preparation', setup(builder) {
      builder.onResolve({ filter: /^@lds\/plugin-sdk(?:\/setup)?$/ }, args => ({ path: args.path, namespace: 'sdk' }))
      builder.onLoad({ filter: /.*/, namespace: 'sdk' }, () => ({ contents: `
        export const apiFetch = url => window.proof.request('GET', url);
        export const postJson = (url, body) => window.proof.request('POST', url, body);
        export const useToast = () => ({ error: message => window.proof.errors.push(message) });
        export const HelpBadge = () => null;
        export const brokenOrMissing = (missing = [], invalid = []) => [...missing, ...invalid.filter(x => x.blocking).map(x => x.asset)];
        export const fmtSize = bytes => bytes + ' B';
      ` }))
    } }],
  })
  code = result.outputFiles[0].text
  browser = await chromium.launch({ executablePath, headless: true })
})
after(async () => { await browser?.close() })

async function mount(t, reply, mode = '', overrides = {}, resume = {}) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  page.setDefaultTimeout(4000)
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/*', route => route.fulfill({ contentType: 'text/html', body: '<div id="root"></div>' }))
  await page.goto('http://seed-preparation.invalid/')
  await page.addScriptTag({ content: code })
  await page.evaluate(args => window.proof.mount(...args), [reply, mode, overrides, resume])
  await page.waitForFunction(() => window.proof.initialRead)
  t.after(async () => { await page.close(); assert.deepEqual(errors, []) })
  return page
}

test('one button posts the group and follows its authoritative plan, without claiming readiness', options, async t => {
  const page = await mount(t, { plan: ['seedvr2_nodes', 'seedvr2_vae'], statuses: {
    seedvr2_nodes: { state: 'running' }, seedvr2_vae: { state: 'queued' } } })
  await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).click()
  await page.waitForFunction(() => window.proof.done === 1)
  const proof = await page.evaluate(() => window.proof)
  assert.deepEqual(proof.calls.filter(call => call.method === 'POST'), [{ method: 'POST', url: '/api/setup/install-group/seedvr2', body: {} }])
  assert.ok(proof.calls.slice(2).every(call => decodeURIComponent(call.url).endsWith('actions=seedvr2_nodes,seedvr2_vae')))
  assert.equal(await page.locator('ul li').count(), 2)
  assert.match(await page.locator('body').innerText(), /Selected steps prepared.*Restart ComfyUI/s)
  assert.doesNotMatch(await page.locator('body').innerText(), /✓ SeedVR2 is ready/)
  assert.equal(await page.locator('details').getAttribute('open'), null)
})

test('empty plans and immediate errors stop without polling', options, async t => {
  for (const reply of [{ plan: [], statuses: {} }, { plan: ['seedvr2_nodes', 'seedvr2_vae'], statuses: {
    seedvr2_nodes: { state: 'error', log: ['Python 3.12 is required.'] }, seedvr2_vae: { state: 'queued' } } }]) {
    const page = await mount(t, reply)
    await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).click()
    if (reply.plan.length) await page.getByRole('alert').waitFor()
    else await page.waitForFunction(() => window.proof.done === 1)
    assert.equal(await page.evaluate(() => window.proof.polls), 0)
    assert.doesNotMatch(await page.locator('body').innerText(), /✓ SeedVR2 is ready/)
  }
})

test('backend compatibility refusal stays visible and offers no manual pip command', options, async t => {
  const page = await mount(t, { plan: [], statuses: {} }, 'refused')
  await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).click()
  await page.getByRole('alert').waitFor()
  assert.match(await page.getByRole('alert').innerText(), /Python 3.11.*Python >=3.12/)
  assert.doesNotMatch(await page.locator('body').innerText(), /pip install|thirteen Python/)
  assert.equal(await page.evaluate(() => window.proof.polls), 0)
})

for (const mode of ['offline', 'idle']) {
  test(mode + ': unavailable progress stops with a bounded retry', options, async t => {
    const page = await mount(t, { plan: ['seedvr2_nodes'], statuses: { seedvr2_nodes: { state: 'running' } } }, mode)
    await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).click()
    await page.getByRole('alert').waitFor()
    assert.equal(await page.evaluate(() => window.proof.polls), mode === 'offline' ? 5 : 1)
    assert.equal(await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).isEnabled(), true)
  })
}

test('returning to an active preparation resumes progress without another POST', options, async t => {
  const page = await mount(t, { plan: ['seedvr2_vae'] }, '', {}, { seedvr2_vae: { state: 'running' } })
  await page.waitForFunction(() => window.proof.done === 1)
  assert.equal(await page.evaluate(() => window.proof.calls.filter(call => call.method === 'POST').length), 0)
  assert.equal(await page.locator('ul li').count(), 1)
})

test('a completed partial resume keeps missing components actionable after recheck', options, async t => {
  const page = await mount(t, { plan: ['seedvr2_nodes'] }, '', {}, {
    seedvr2_nodes: { state: 'running' }, seedvr2_model: { state: 'error' }, seedvr2_vae: { state: 'success' },
  })
  await page.waitForFunction(() => window.proof.done === 1)
  assert.match(await page.locator('body').innerText(), /Selected steps prepared.*Other components/s)
  await page.getByRole('button', { name: 'Re-check ComfyUI' }).click()
  assert.equal(await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).isEnabled(), true)
  assert.equal(await page.evaluate(() => window.proof.calls.filter(call => call.method === 'POST').length), 0)
})

test('pack on disk but unloaded offers restart and recheck, without reinstall', options, async t => {
  const page = await mount(t, { plan: [] }, '', { seedvr2_nodes_installed: true, seedvr2_missing: [] })
  assert.equal(await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).count(), 0)
  assert.match(await page.locator('body').innerText(), /Restart ComfyUI, then re-check/)
  await page.getByRole('button', { name: 'Re-check ComfyUI' }).click()
  assert.equal(await page.evaluate(() => window.proof.done), 1)
  assert.equal(await page.evaluate(() => window.proof.calls.filter(call => call.method === 'POST').length), 0)
})

test('ready comes only from the actual capability probe', options, async t => {
  const page = await mount(t, { plan: [] }, '', { seedvr2_ready: true, seedvr2_nodes_installed: true, seedvr2_nodes_missing: [], seedvr2_missing: [] })
  assert.match(await page.locator('body').innerText(), /✓ SeedVR2 is ready/)
  assert.equal(await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).count(), 0)
})

test('a successful readiness recheck supersedes stale polling errors and steps', options, async t => {
  const page = await mount(t, { plan: ['seedvr2_nodes'], statuses: { seedvr2_nodes: { state: 'running' } } }, 'offline')
  await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).click()
  await page.getByRole('alert').waitFor()
  await page.evaluate(() => { window.proof.recheckedCaps = { comfyui: { dir_valid: true, reachable: true,
    seedvr2_nodes_installed: true, seedvr2_nodes_missing: [], seedvr2_missing: [], seedvr2_ready: true } } })
  await page.getByRole('button', { name: 'Re-check ComfyUI' }).click()
  await page.getByText('✓ SeedVR2 is ready — ComfyUI reports the required nodes and models.', { exact: true }).waitFor()
  assert.equal(await page.getByRole('alert').count(), 0)
  assert.equal(await page.locator('ul li').count(), 0)
  assert.equal(await page.getByRole('button', { name: 'Prepare SeedVR2', exact: true }).count(), 0)
})
