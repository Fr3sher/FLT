import assert from 'node:assert/strict'
import test from 'node:test'
import { previewRequest } from '../frontend/videobank/videoPreviewSelection.js'
import { videoTrainingControls } from '../frontend/videobank/videoTrainingSettings.js'

test('checkpoint comparison submits the complete selection past eight saves', () => {
  const choices = Array.from({ length: 12 }, (_, i) => ({
    key: `save-${i}`, eligible: true,
    selector: { run_id: null, step: (i + 1) * 100, final: false },
  }))
  const args = { choices, selected: choices.map(c => c.key), prompt: 'A person walks.',
    mode: 't2v', strength: 1, opts: { seed: 123, frames: 56 } }
  assert.deepEqual(previewRequest(args).checkpoints, choices.map(c => c.selector))
  assert.throws(() => previewRequest({ ...args, selected: [] }), /at least one/)
  assert.throws(() => previewRequest({ ...args, selected: [...args.selected, 'missing'] }), /available/)
})

test('local and cloud video training preserve every nonblank sample prompt', () => {
  const prompts = Array.from({ length: 6 }, (_, i) => `Scene ${i} in motion`)
  for (const lane of ['local', 'cloud']) {
    const result = videoTrainingControls({ prompts: [' ', ...prompts, ''].join('\n') }, lane)
    assert.deepEqual(result.sample_prompts, prompts)
    assert.throws(() => videoTrainingControls({ prompts: 'x'.repeat(2001) }, lane), /2000/)
  }
})
