import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import test from 'node:test'
import { createElement, renderToStaticMarkup } from './support/mountJsx.mjs'

const { MemoryRouter } = await import('react-router')
const { ToastProvider, useToast } = await import('../src/components/common/Toast.jsx')
const { CapabilitiesProvider, useCapabilities } = await import('../src/context/CapabilitiesContext.jsx')
const { configureHostRuntime } = await import('../src/plugins/runtimeHost.jsx')
const { publishRuntime } = await import('../src/plugins/loadPlugins.js')
const { canvasServices } = await import('../src/plugins/canvasRuntime.js')
const { resetRegistry, registerDescriptor, setEnabled } = await import('../src/plugins/registry.js')
const ui = await import('../../sdk/frontend/ui.js')
const training = await import('../../sdk/frontend/training.js')
const canvas = await import('../../sdk/frontend/canvas.js')
const api = await import('../../sdk/frontend/runtime.js')
const inference = await import('../../sdk/frontend/inference.js')
const { localContinuationAvailability, localContinuationRequest, explicitRunContinuation } = await import('../src/components/runs/localContinuation.js')
const { waitForStorageMove } = await import('../src/components/shared/storageMoveCompletion.js')
const { pillSelectScale } = await import('../src/utils/canvasNodeChrome.js')
const { POPOVER_H } = await import('../src/components/dataset/checkpointPopover.js')
const { groupTrained } = await import('../src/components/shared/h3LoraGroups.js')
const { groupTrained: sdkGroupTrained } = await import('../../sdk/frontend/h3.js')

function mount(Component, props = {}) {
  return renderToStaticMarkup(createElement(MemoryRouter, null,
    createElement(ToastProvider, null, createElement(CapabilitiesProvider, null,
      createElement(Component, props)))))
}

test.beforeEach(t => {
  const saved = { window: globalThis.window, fetch: globalThis.fetch, document: globalThis.document }
  t.after(() => Object.assign(globalThis, saved))
  globalThis.window = {}
  globalThis.document = { cookie: 'csrf_token=fixture', querySelector: () => null }
  globalThis.fetch = () => { throw new Error('Unexpected request in a neutral host test') }
  resetRegistry()
  setEnabled([])
  configureHostRuntime()
  publishRuntime()
})

test('the real host graph resolves all services with the application context identities', () => {
  const host = window.lds
  assert.equal(host.useToast, useToast)
  assert.equal(host.useCapabilities, useCapabilities)
  assert.equal(host.canvas, canvasServices)
  assert.equal(host.canvas.pillSelectScale, pillSelectScale)
  for (const group of ['ui', 'training', 'links', 'inference', 'lineage', 'files', 'bank', 'canvas']) {
    for (const [name, value] of Object.entries(host[group])) assert.notEqual(value, undefined, `${group}.${name}`)
  }
  assert.match(mount(ui.Card, { title: 'Shared context', children: 'fixture' }), /Shared context/)
  assert.match(mount(training.RunStatusBadge, { status: 'error' }), /failed/)
})

test('SDK HTTP mutation and result-envelope helpers use real CSRF transport semantics', async () => {
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return new Response(JSON.stringify({ error: 'fixture refusal', detail: { blocked: true } }), {
      status: 409, headers: { 'content-type': 'application/json' },
    })
  }
  await assert.rejects(api.postJson('/api/fixture', { value: 1 }), /fixture refusal/)
  assert.deepEqual(await api.postJsonResult('/api/fixture', { value: 2 }), {
    ok: false, error: 'fixture refusal', detail: { blocked: true },
  })
  assert.equal(calls.length, 2)
  for (const call of calls) {
    assert.equal(call.options.method, 'POST')
    assert.equal(call.options.credentials, 'include')
    assert.equal(call.options.headers['X-CSRFToken'], 'fixture')
  }
})

test('plugin restoration availability follows active ownership, not historical core engines', () => {
  assert.equal(inference.improvementAvailable(), false)
  assert.deepEqual(inference.availableImproveEngines(), [])
  assert.equal(inference.improveEngine('seedvr2').label, 'SeedVR2')
  assert.equal(registerDescriptor({ id: 'fixture.restore', slots: {
    'improve.engine': [{ id: 'fixture', label: 'Fixture', ready: () => false }],
    'setup.step': [{ id: 'fixture-setup', labels: { fixture_prepare: 'Prepare fixture' } }],
  } }), true)
  setEnabled(['fixture.restore'])
  assert.equal(inference.availableImproveEngines()[0].plugin, 'fixture.restore')
  assert.equal(inference.availableImproveEngines()[0].ready({}), false)
  assert.equal(inference.improvementAvailable(), true)
  assert.equal(api.installActionLabel('fixture_prepare'), 'Prepare fixture')
  setEnabled([])
  assert.equal(inference.improvementAvailable(), false)
  assert.equal(api.installActionLabel('fixture_prepare'), 'fixture_prepare')
})

test('popover height follows active contribution count on the actual surface', () => {
  registerDescriptor({ id: 'fixture.actions', slots: { 'checkpoint.action': [
    { id: 'one', surfaces: ['canvas'] }, { id: 'two', surfaces: ['graph'] },
  ] } })
  setEnabled(['fixture.actions'])
  assert.equal(canvas.popoverHeight('canvas'), POPOVER_H + 31)
  assert.equal(canvas.popoverHeight('video'), POPOVER_H)
  setEnabled([])
  assert.equal(canvas.popoverHeight('canvas'), POPOVER_H)
  assert.equal(canvas.pillSelectScale(0.25, 150), pillSelectScale(0.25, 150))
})

test('shared H3 picker mounts with a Live endpoint and no Video plugin', () => {
  const html = mount(ui.H3LoraPicker, { apiBase: '/api/video-studio/live', lockKey: 'fixture.lora',
    value: null, onChange: () => {}, strength: 1, onStrength: () => {} })
  assert.match(html, /LoRA under test/)
  assert.match(html, /No LoRA/)
  const records = [{ run_id: 4, filename: 'lds4_video_sample_000001000.safetensors' }]
  assert.deepEqual(groupTrained(records), sdkGroupTrained(records))
})

test('a new engine reuses the main checkbox control without assuming a core engine id', () => {
  registerDescriptor({ id: 'fixture.engine', slots: { 'engine.spec': [{ id: 'custom', label: 'Custom engine' }] } })
  setEnabled(['fixture.engine'])
  const html = mount(ui.EngineCard, { id: 'custom', checked: true, available: true,
    onToggle: () => {}, title: 'Custom engine', tags: 'local' })
  assert.match(html, /role="checkbox"/)
  assert.match(html, /aria-label="Custom engine"/)
  assert.match(html, /aria-checked="true"/)
})

test('the shared bank switch does not hardcode a Video route while plugins are off', () => {
  const html = mount(window.lds.ui.BankLaneTabs)
  assert.match(html, /href="\/bank"/)
  assert.doesNotMatch(html, /href="\/video-bank"/)
})

function historyHost(recent = []) {
  return { data: { actives: [], recent }, groupsCollapsed: {}, historyLimit: 15,
    brokenThumbs: {}, lineageOpen: {}, lineageData: {}, retrying: {}, continuing: {},
    toggleGroup: () => {}, openDataset: () => {}, openTestStudio: () => {}, setRecentCollapsed: () => {},
    setGroupsCollapsed: () => {}, setBrokenThumbs: () => {}, setHistoryLimit: () => {},
    retry: () => {}, shareConfig: () => {}, continueRun: () => {}, canContinueRun: run => run.source === 'local' }
}

test('stored cloud history stays readable with no launch, cleanup or continue capability', () => {
  const host = historyHost([{ source: 'cloud', run_id: 5, record_id: 8, dataset_id: 1,
    dataset_name: 'Fixture cloud run', status: 'error', checkpoint_ready: true, share_key: 'fixture' }])
  const html = mount(training.RunsHubContent, { host })
  assert.match(html, /Fixture cloud run/)
  assert.match(html, /run-cloud-5/)
  assert.doesNotMatch(html, /↻ Retry|▶ Continue|Clean finished|fresh pod/)
  assert.match(html, /Share config/)
})

test('cloud controls appear only from the supplied execution capability', () => {
  const host = historyHost([{ source: 'cloud', run_id: 5, record_id: 8, dataset_id: 1, status: 'error' }])
  const html = mount(training.RunsHubContent, { host, cloud: { retry: () => {},
    headerExtra: createElement('span', null, 'Cloud controls supplied'), historyAction: 'Cleanup supplied' } })
  assert.match(html, /↻ Retry/)
  assert.match(html, /Cloud controls supplied/)
  assert.match(html, /Cleanup supplied/)
})

test('local history keeps record identity, retry and the explicit checkpoint URL', () => {
  const run = { source: 'local', record_id: 12, dataset_id: 1, dataset_name: 'Fixture local run',
    status: 'error', checkpoint_ready: true, checkpoint_url: '/api/fixture/checkpoint', resume_steps: [100] }
  assert.equal(training.checkpointHref(run), '/api/fixture/checkpoint')
  const html = mount(training.RunsHubContent, { host: historyHost([run]) })
  assert.match(html, /run-local-12/)
  assert.match(html, /↻ Retry/)
  assert.match(html, /href="\/api\/fixture\/checkpoint"/)
})

test('run history errors render a diagnostic rather than indefinite initial loading', () => {
  const host = { ...historyHost(), data: null, loadError: 'Fixture history unavailable' }
  const html = mount(training.RunsHubContent, { host })
  assert.match(html, /role="alert"/)
  assert.match(html, /Fixture history unavailable/)
  assert.doesNotMatch(html, /Loading…/)
  assert.match(mount(training.RunsHub), /Loading…/)
})

test('full-model metadata does not imply verified delivery or install an execution lane', () => {
  const html = mount(training.FullArtifactStatus, { run: { source: 'cloud', run_id: 5,
    training_mode: 'full_transformer', local_artifact_status: 'missing', artifact_status: 'missing' } })
  assert.doesNotMatch(html, /<button/)
})

test('continuation resolves the actual listed save and local record owner', () => {
  const run = { source: 'local', record_id: 11, dataset_id: 3, train_type: 'zimage',
    resume_steps: [900, 100], masked: false }
  assert.deepEqual(explicitRunContinuation(run, { extraSteps: 250, lane: 'local' }), {
    extraSteps: 250, lane: 'local', fromStep: 900, expectedRecordId: 11,
  })
  const request = localContinuationRequest(run, { extraSteps: 250, fromStep: 100 })
  assert.equal(request.url, '/api/dataset/3/train/continue')
  assert.equal(request.body.from_step, 100)
  assert.equal(request.body.expected_record_id, 11)
  assert.equal(request.body.masked, false)
  assert.equal(localContinuationRequest(run, null), null)
})

test('unknown, unlisted and cloud-to-local checkpoint continuations are refused', () => {
  for (const run of [{ source: 'local', resume_steps: [100] }, { source: 'cloud', run_id: 4, resume_steps: [100] },
    { source: 'invalid', record_id: 2, resume_steps: [100] }]) {
    assert.equal(explicitRunContinuation(run, { lane: 'local', fromStep: 100 }), null)
  }
  const run = { source: 'local', record_id: 8, resume_steps: [100] }
  assert.equal(explicitRunContinuation(run, { fromStep: 999 }), null)
  assert.equal(explicitRunContinuation({ ...run, resume_checkpoints: [{ step: 200 }] }, { fromStep: 100 }), null)
  assert.equal(localContinuationAvailability({ ...run, dataset_id: 1 }).available, false)
  assert.equal(localContinuationAvailability({ ...run, dataset_id: 1 }, { aitoolkitValid: true }).available, true)
})

test('storage move completion requires a done receipt; transient failures do not save a folder', async () => {
  const steps = [new Error('transient'), { phase: 'scanning' }, { phase: 'copying' }, { phase: 'done' }]
  const seen = []
  const result = await waitForStorageMove(async () => {
    const next = steps.shift(); if (next instanceof Error) throw next; return next
  }, state => seen.push(state.phase), { wait: async () => {}, attempts: 4 })
  assert.deepEqual(seen, ['scanning', 'copying', 'done'])
  assert.equal(result.phase, 'done')
  await assert.rejects(waitForStorageMove(async () => ({ phase: 'copying' }), () => {}, {
    wait: async () => {}, attempts: 2,
  }), /not confirmed completion/)
})

test('storage errors, empty status and repeated network failures stop without completion', async () => {
  for (const state of [null, {}, { phase: 'unknown' }, { phase: 'error', error: 'fixture error' }]) {
    await assert.rejects(waitForStorageMove(async () => state, () => {}, { wait: async () => {}, attempts: 2 }))
  }
  let calls = 0
  await assert.rejects(waitForStorageMove(async () => { calls += 1; throw new Error('offline') }, () => {}, {
    wait: async () => {}, maxFailures: 2, attempts: 20,
  }), /progress is unavailable/)
  assert.equal(calls, 2)
})

test('the host imports neither plugin products nor private attention installers', async () => {
  for (const name of ['runtimeHost.jsx', 'canvasRuntime.js']) {
    const source = await fs.readFile(new URL('../src/plugins/' + name, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /@bundled|bundled\/|H3AttentionInstallRow|SGLang|sglang|battle|director/i)
  }
  const picker = await fs.readFile(new URL('../src/components/shared/H3LoraPicker.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(picker, /from ['"].*video|videoStudioApi|@lds\/plugin-sdk/)
})
