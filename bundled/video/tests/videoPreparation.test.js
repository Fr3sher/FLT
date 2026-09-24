import test from 'node:test'
import assert from 'node:assert/strict'
import { admittedVideoPlan, videoBatchProgress } from '../frontend/lib/videoPreparation.js'
import { videoStudioInstallPlan, VIDEO_STUDIO_INSTALL_ORDER } from '../frontend/lib/videoSetup.js'

test('Video selects only public missing model actions, never another product', () => {
  assert.deepEqual(videoStudioInstallPlan({}), [])
  assert.deepEqual(videoStudioInstallPlan({ comfyui: { dir_valid: true, video_studio_missing: [
    {action:'h3_base'}, {action:'face_scoring'}, {action:'h3_base_light'}, {action:'h3_base'}, {name:'manual file'},
  ] }}), ['h3_base'])
  assert.ok(VIDEO_STUDIO_INSTALL_ORDER.includes('h3_clip_projection'))
  assert.ok(VIDEO_STUDIO_INSTALL_ORDER.includes('h3_clipproj_nodes'))
})
test('the admitted plan is copied from the server, preserving its order', () => {
  const r={plan:['h3_audio_vae','h3_base']}
  assert.deepEqual(admittedVideoPlan(['h3_base','h3_audio_vae'],r), r.plan)
  assert.notEqual(admittedVideoPlan(r.plan,r),r.plan)
})
test('the 4B replacement prepares encoder, projection and nodes together', () => {
  const actions = ['h3_text_encoder', 'h3_clip_projection', 'h3_clipproj_nodes']
  const caps = { comfyui: { dir_valid: true, video_studio_missing: actions.map(action => ({ action })) } }
  assert.deepEqual(videoStudioInstallPlan(caps), actions)
})
for (const plan of [undefined, [], 'h3_base', ['face_scoring'], ['h3_base','h3_base']]) {
  test(`malformed or out-of-scope admission refuses ${JSON.stringify(plan)}`, () => {
    assert.throws(() => admittedVideoPlan(['h3_base'], {plan}))
  })
}
test('an immediate backend error stops the batch even when another item is queued', () => {
  assert.deepEqual(videoBatchProgress(['a','b'], {a:{state:'error'},b:{state:'queued'}}),
    {failed:true,done:0,terminal:true})
})
test('success requires every admitted item; partial success stays running', () => {
  assert.equal(videoBatchProgress(['a','b'], {a:{state:'success'},b:{state:'running'}}).terminal,false)
  assert.deepEqual(videoBatchProgress(['a','b'], {a:{state:'success'},b:{state:'success'}}),
    {failed:false,done:2,terminal:true})
})
test('empty, missing and unknown status snapshots are errors, never completion', () => {
  for(const statuses of [undefined,{}, {a:{state:'mystery'}}, {b:{state:'success'}}])
    assert.throws(() => videoBatchProgress(['a'],statuses))
  assert.throws(() => videoBatchProgress([],{}))
})
