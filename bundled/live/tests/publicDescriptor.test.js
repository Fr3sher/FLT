import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'
import descriptor from '../frontend/index.js'
import { catalog, labels } from '../frontend/setup.js'

const manifest = JSON.parse(fs.readFileSync(new URL('../plugin.json', import.meta.url), 'utf8'))
const lane = fs.readFileSync(new URL('../frontend/studio/live/LiveStudio.jsx', import.meta.url), 'utf8')

test('Live owns its screen and preparation without requiring another plugin', () => {
  assert.deepEqual(manifest.requires, [])
  assert.equal(descriptor.id, manifest.id)
  assert.deepEqual(descriptor.slots['studio.tab'].map(row => row.id), ['live'])
  assert.equal(descriptor.slots['setup.card'].length, 1)
  assert.equal((descriptor.slots['settings.group'] || []).length, 0)
  assert.deepEqual(Object.keys(labels), manifest.owns.install_actions)
  assert.match(lane, /<H3LoraPicker apiBase="\/api\/video-studio\/live" lockKey="live.lock.loraStrength"/)
  assert.match(lane, /const optionsUrl = \(\) => '\/api\/video-studio\/live\/render-options'/)
  for (const match of lane.matchAll(/from ['"]([^'"]+)['"]/g)) {
    assert.ok(['react', 'lucide-react', 'hls.js/dist/hls.worker.js?url&no-inline',
      '@lds/plugin-sdk', '@lds/plugin-sdk/ui', '@lds/plugin-sdk/h3', './liveStudioApi.js'].includes(match[1]), match[1])
  }
})

test('the descriptor claims precisely the included help, guide and news contributions', () => {
  assert.deepEqual(descriptor.help.map(topic => topic.id).sort(), [...manifest.owns.help_topics].sort())
  assert.deepEqual(descriptor.whatsNew.map(entry => entry.id), manifest.owns.whats_new_ids)
  assert.deepEqual(descriptor.guide.sections.map(section => `${section.chapter}#${section.anchor}`), manifest.guide_ownership.sections)
  assert.ok(descriptor.guide.sections.every(section => section.markdown.startsWith('## ')))
  assert.equal(descriptor.whatsNew.length, 1)
})

test('the public player still loads HLS on demand and cleans up native playback', () => {
  assert.match(lane, /await import\('hls\.js'\)/)
  assert.ok(lane.indexOf('Hls.isSupported()') < lane.indexOf("canPlayType('application/vnd.apple.mpegurl')"))
  assert.match(lane, /hlsRef\.current\.destroy\(\)/)
  assert.match(lane, /video\.removeAttribute\('src'\)/)
  assert.match(lane, /Hls\.Events\.ERROR/)
  for (const marker of ['live-take', 'live-rail', 'live-player']) assert.ok(lane.includes(`data-probe-panel="${marker}"`))
  assert.match(lane, /const streamReady = !!vlcUrl && \(status\?\.segments \|\| 0\) > 0/)
})

test('the setup catalogue distinguishes absent probes, installed files and missing files', () => {
  assert.ok(catalog({}).every(row => !row.present))
  const caps = { comfyui: { dir_valid: true }, live: { encoder: true, missing: [
    { action: 'live_h3_base', required: true }, { action: 'live_h3_turbo_lora', required: false },
  ] } }
  const rows = catalog(caps)
  assert.equal(rows.find(row => row.action === 'live_encoder').present, true)
  assert.equal(rows.find(row => row.action === 'live_h3_base').present, false)
  assert.equal(rows.find(row => row.action === 'live_h3_text_encoder').present, true)
  assert.equal(rows.find(row => row.action === 'live_h3_turbo_lora').present, false)
})
