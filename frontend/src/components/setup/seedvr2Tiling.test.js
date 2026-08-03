import assert from 'node:assert/strict'
import test from 'node:test'

import { ceilingLine, tilingStatus, TTP_PACK, TTP_URL } from './seedvr2Tiling.js'

const caps = (comfyui) => ({ comfyui: { reachable: true, ...comfyui } })

test('an absent pack reads as OPTIONAL, never as something broken', () => {
  const s = tilingStatus(caps({ seedvr2_tiling_ready: false,
    seedvr2_tiling_nodes_missing: ['TTP_Image_Tile_Batch', 'TTP_Image_Assy'] }))
  assert.equal(s.state, 'absent')
  assert.match(s.text, /^Optional\./)
  // ...and it says what still works, because it does.
  assert.match(s.text, /upscales still run/)
  assert.match(s.text, new RegExp(TTP_PACK))
})

test('half the classes present means UPDATE and restart, not install', () => {
  // An old build of the pack is a different problem from a missing one, and
  // telling someone to install what they already have is the failure mode this
  // whole detection style exists to avoid.
  const s = tilingStatus(caps({ seedvr2_tiling_ready: false,
    seedvr2_tiling_nodes_missing: ['TTP_Image_Assy'] }))
  assert.equal(s.state, 'restart')
  assert.match(s.text, /update it/i)
  assert.match(s.text, /TTP_Image_Assy/)
})

test('a ready pack says what it changes, in the user’s terms', () => {
  const s = tilingStatus(caps({ seedvr2_tiling_ready: true }))
  assert.equal(s.state, 'ready')
  assert.match(s.text, /tiles/)
})

test('an unreachable ComfyUI is "cannot tell", not "missing"', () => {
  // This lane's probe fails CLOSED, so silence here is honest ignorance.
  const s = tilingStatus({ comfyui: { reachable: false } })
  assert.equal(s.state, 'unknown')
  assert.doesNotMatch(s.text, /Optional/)
  assert.match(s.text, /Start ComfyUI/)
})

test('junk capabilities never throw — the Setup page must render', () => {
  for (const c of [undefined, null, {}, { comfyui: null }]) {
    assert.ok(tilingStatus(c).state)
    assert.doesNotThrow(() => ceilingLine(c))
  }
})

test('an unknown card gets SILENCE, never an invented ceiling', () => {
  for (const mp of [undefined, null, 0, -3, 'lots']) {
    assert.equal(ceilingLine(caps({ seedvr2_ceiling_mp: mp })), null)
  }
})

test('the ceiling sentence changes with the lane that is actually available', () => {
  const without = ceilingLine(caps({ seedvr2_ceiling_mp: 6.4, seedvr2_tiling_ready: false }))
  assert.match(without, /6\.4 MP/)
  assert.match(without, /run out of memory/)
  const with_ = ceilingLine(caps({ seedvr2_ceiling_mp: 6.4, seedvr2_tiling_ready: true }))
  assert.match(with_, /anything larger is tiled/)
  // With tiling available the warning is gone: keeping it would scare people
  // away from a limit that no longer applies to them.
  assert.doesNotMatch(with_, /run out of memory/)
})

test('the pack is named and linkable', () => {
  assert.equal(TTP_PACK, 'Comfyui_TTP_Toolset')
  assert.match(TTP_URL, /^https:\/\/github\.com\/TTPlanetPig\/Comfyui_TTP_Toolset$/)
})
