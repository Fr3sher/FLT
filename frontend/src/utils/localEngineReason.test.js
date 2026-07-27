import test from 'node:test';
import assert from 'node:assert/strict';
import {
  kleinUnavailableReason, localEngineUnavailableReason, hasComfyui,
} from './localEngineReason.js';

/* One gap, one sentence. Both the generation panel and the ✦ Edit-reference modal
   read this module, so "why can't I pick Klein" cannot be answered two different
   ways two clicks apart. Each branch answers ONE question: what do I do next? */

test('the reasons are ordered by what has to be fixed FIRST', () => {
  assert.match(kleinUnavailableReason({ enabledInSettings: false }), /disabled in Settings/);
  // A disabled engine wins over everything: the asset list is meaningless until
  // the engine is on at all.
  assert.match(kleinUnavailableReason({
    enabledInSettings: false, comfyuiReachable: false, missingAssets: ['klein_model'],
  }), /disabled in Settings/);
  assert.match(kleinUnavailableReason({ comfyuiReachable: false }), /Configure ComfyUI/);
});

test('an enum gap is named BEFORE the weights — it is a different fix', () => {
  // Reachable ComfyUI, every file in place, but a widget VALUE the graph pins is
  // not offered. Blaming a weight here sends the user to re-check a green step.
  const reason = kleinUnavailableReason({
    unsupportedEnums: [{ node_id: '31', class_type: 'KSampler', input: 'scheduler',
      value: 'beta57', pack: 'RES4LYF', url: 'https://example.invalid/pack' }],
  });
  assert.doesNotMatch(reason, /missing — download/);
  assert.match(reason, /RES4LYF|scheduler|beta57/);
});

test('the missing Klein weights are NAMED, not collapsed into "the model"', () => {
  // The old text always blamed the UNET, sending people to models/unet/klein/
  // even when the real gap was the text encoder.
  const reason = kleinUnavailableReason({ missingAssets: ['klein_text_encoder', 'klein_vae'] });
  assert.match(reason, /text encoder/);
  assert.match(reason, /VAE/);
});

test('an available engine has no reason at all', () => {
  const caps = { engines: { klein: true, krea: true }, comfyui: { reachable: true } };
  assert.equal(localEngineUnavailableReason('klein', caps), null);
  assert.equal(localEngineUnavailableReason('krea', caps), null);
});

test('an API engine is never explained here — nothing local can predict its failures', () => {
  const caps = { engines: {}, comfyui: { reachable: false } };
  for (const e of ['nanobanana', 'chatgpt', 'openrouter']) {
    assert.equal(localEngineUnavailableReason(e, caps), null, e);
  }
});

test('Krea reports its own extra failure mode: the custom-node pack', () => {
  const caps = {
    engines: { krea: false },
    comfyui: { reachable: true, krea_nodes_missing: ['Krea2EditModelPatch'],
      krea_nodes_installed: false },
  };
  assert.match(localEngineUnavailableReason('krea', caps), /node pack/);
});

test('a node pack ON DISK but not loaded says "restart", not "install"', () => {
  // The app installs the pack itself now; telling someone to install what they
  // just watched install is a working feature reading as broken.
  const caps = {
    engines: { krea: false },
    comfyui: { reachable: true, krea_nodes_missing: ['Krea2EditModelPatch'],
      krea_nodes_installed: true },
  };
  assert.match(localEngineUnavailableReason('krea', caps), /restart ComfyUI/);
});

test('the Settings gate is honoured when the list is passed, skipped when it is not', () => {
  const caps = { engines: { krea: false }, comfyui: { reachable: true } };
  assert.match(localEngineUnavailableReason('krea', caps, ['klein']), /disabled in Settings/);
  // FOLLOW-UP, deliberately left visible: the ✦ Edit modal passes no list (it does
  // not fetch /api/settings), so an engine disabled there still appears in that
  // modal — gated only by live readiness. Passing null is that state, not an
  // accident: the gate is opt-in until the modal has the list to give it.
  assert.doesNotMatch(localEngineUnavailableReason('krea', caps, null) || '',
    /disabled in Settings/);
});

test('hasComfyui is the line between "a fixable gap" and "a product you have not got"', () => {
  assert.equal(hasComfyui(null), false);
  assert.equal(hasComfyui({ comfyui: {} }), false);
  // Configured but currently down still counts: that is fixable, and hiding the
  // engines while the user restarts ComfyUI would look like a lost feature.
  assert.equal(hasComfyui({ comfyui: { dir_configured: true, reachable: false } }), true);
  assert.equal(hasComfyui({ comfyui: { reachable: true } }), true);
});
