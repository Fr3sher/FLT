import test from 'node:test'
import assert from 'node:assert/strict'
import { readImproveSettings, saveImproveSettings } from '../frontend/lib/settings.js'

const CORE = '/api/settings'
const OWN = '/api/settings?plugin=image_upscale'
function host(t, { failShared = false } = {}) {
  const prior = globalThis.window
  const calls = []
  const state = {
    [CORE]: { config: { klein: { unet: 'base.safetensors', generation_lora_presets: [{ name: 'One', loras: [] }] } } },
    [OWN]: { config: { identity_prompts: { klein_improve: 'original' }, klein: { improve_steps: 8 } } },
  }
  globalThis.window = { lds: { api: 1, sdkVersion: '1.15.0',
    apiFetch: async url => { calls.push(['GET', url]); assert.ok(state[url]); return structuredClone(state[url]) },
    putJson: async (url, body) => {
      calls.push(['PUT', url, body])
      if (failShared && url === CORE) throw new Error('disk full')
      for (const [section, values] of Object.entries(body.config)) {
        for (const key of Object.keys(values)) {
          const shared = section === 'klein' && ['unet', 'generation_lora_presets'].includes(key)
          assert.equal(url, shared ? CORE : OWN, 'each field must use its actual owner')
        }
        state[url].config[section] = { ...state[url].config[section], ...values }
      }
      return structuredClone(state[url])
    },
  } }
  t.after(() => { if (prior === undefined) delete globalThis.window; else globalThis.window = prior })
  return { calls, state }
}

test('read combines the shared model library with the owned instruction and dials', async t => {
  const { calls } = host(t)
  const payload = await readImproveSettings()
  assert.equal(payload.config.identity_prompts.klein_improve, 'original')
  assert.equal(payload.config.klein.unet, 'base.safetensors')
  assert.equal(payload.config.klein.improve_steps, 8)
  assert.equal(payload.config.klein.generation_lora_presets[0].name, 'One')
  assert.deepEqual(new Set(calls.map(call => call[1])), new Set([CORE, OWN]))
})

test('instruction save uses only the owner endpoint and returns the shared fields too', async t => {
  const { calls } = host(t)
  const payload = await saveImproveSettings({ config: { identity_prompts: { klein_improve: 'new' } } })
  assert.deepEqual(calls.filter(call => call[0] === 'PUT').map(call => call[1]), [OWN])
  assert.equal(payload.config.identity_prompts.klein_improve, 'new')
  assert.equal(payload.config.klein.unet, 'base.safetensors')
})

test('changing preset strengths writes the shared library without touching plugin dials', async t => {
  const { calls } = host(t)
  const payload = await saveImproveSettings({ config: { klein: { generation_lora_presets: [] } } })
  assert.deepEqual(calls.filter(call => call[0] === 'PUT').map(call => call[1]), [CORE])
  assert.deepEqual(payload.config.klein.generation_lora_presets, [])
  assert.equal(payload.config.klein.improve_steps, 8)
})

test('restoring a recorded profile sends its model pin and Improve dials to their respective owners', async t => {
  const { calls } = host(t)
  const payload = await saveImproveSettings({ config: { identity_prompts: { klein_improve: 'restored' }, klein: { unet: 'other.safetensors', improve_steps: 10 } } })
  assert.deepEqual(calls.filter(call => call[0] === 'PUT').map(call => call[1]), [OWN, CORE])
  assert.equal(payload.config.klein.unet, 'other.safetensors')
  assert.equal(payload.config.klein.improve_steps, 10)
})

test('a partial write failure states exactly which half was saved', async t => {
  const { state } = host(t, { failShared: true })
  await assert.rejects(saveImproveSettings({ config: { klein: { unet: 'other', improve_steps: 12 } } }), /Improve settings were saved, but the shared model or presets were not saved: disk full/)
  assert.equal(state[OWN].config.klein.improve_steps, 12)
  assert.equal(state[CORE].config.klein.unet, 'base.safetensors')
})

test('an unrelated field is rejected before any write', async t => {
  const { calls } = host(t)
  await assert.rejects(saveImproveSettings({ config: { klein: { improve_steps: 9 }, server: { port: 1 } } }), /outside Klein Improve/)
  assert.deepEqual(calls, [])
})
