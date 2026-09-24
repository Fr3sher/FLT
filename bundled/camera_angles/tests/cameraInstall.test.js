import { registerBundledDescriptor } from '../../../frontend/tests/support/bundledDescriptors.mjs'
/* 📷 Camera angles — the one-click install, front-end side, through the
   plugin's `setup.step` and `setup.card` contributions.

   The gap this pins shut is the one the Krea rows already document: an engine
   whose weights install through the 409 but appear NOWHERE on the screen where
   the user decides they are done. Every surface below — the plan, the catalog
   rows, the labels, the counted capability — is the plugin's, and reaches the
   Setup screen only through the core's slots, so this registers the descriptor
   the way the app does and reads the core's own functions. */
import test from 'node:test';
import assert from 'node:assert/strict';

import descriptor from '../frontend/index.js';
import {
  CAMERA_ACTION_LABELS, CAMERA_INSTALL_ORDER, cameraInstallPlan,
} from '../frontend/lib/cameraInstall.js';
import {
  INSTALL_ALL_ACTION_LABELS, deriveCapabilitySummary, installAllPlan, installCatalog,
} from '../../../frontend/src/hooks/useSetupSteps.js';
import { resetRegistry, setEnabled } from '../../../frontend/src/plugins/registry.js';

const caps = (comfyui) => ({ comfyui });

function withPlugin(enabled = true) {
  resetRegistry();
  registerBundledDescriptor(descriptor, { external: false });
  setEnabled(enabled ? ['camera_angles'] : []);
}

test('the camera button queues only the missing weights, in the backend order', () => {
  assert.deepEqual(
    cameraInstallPlan(caps({ dir_valid: true,
      camera_missing: ['camera_lora', 'krea_vae'] })),
    ['camera_lora', 'krea_vae'],
  );
  // Someone who placed everything by hand sees an empty plan, not a 20 GB
  // re-download.
  assert.deepEqual(
    cameraInstallPlan(caps({ dir_valid: true, camera_missing: [] })), []);
  // No validated ComfyUI folder → no plan, never a guessed path.
  assert.deepEqual(
    cameraInstallPlan(caps({ dir_valid: false, camera_missing: ['camera_model'] })), []);
});

test('the VAE rides the Krea action — one file, one button', () => {
  // camera_missing reports the Qwen VAE under `krea_vae` (the lane shares the
  // file), and the plan passes that through rather than inventing a camera_vae.
  assert.ok(CAMERA_INSTALL_ORDER.includes('krea_vae'));
  assert.ok(!CAMERA_INSTALL_ORDER.includes('camera_vae'));
});

test('every queued action has a human label — the plugin\'s or the core\'s', () => {
  for (const a of CAMERA_INSTALL_ORDER) {
    assert.ok(CAMERA_ACTION_LABELS[a] || INSTALL_ALL_ACTION_LABELS[a], `no label for ${a}`);
  }
});

test('"Install everything" never silently pulls the camera engine', () => {
  // ~21.6 GB for a verb nobody pressed would be hostile on a metered link —
  // same rule as Krea and SeedVR2.
  withPlugin();
  const plan = installAllPlan({ comfyui: {
    dir_valid: true,
    klein_missing: [], camera_missing: ['camera_model', 'camera_lora'],
  } });
  assert.ok(!plan.some((a) => a.startsWith('camera_')), plan.join(','));
});

test('the install menu lists every camera weight with its live state — while the plugin is enabled', () => {
  withPlugin();
  const rows = installCatalog(caps({
    dir_valid: true, camera_missing: ['camera_lora'], klein_missing: [], krea_missing: [],
  }));
  const byAction = Object.fromEntries(rows.map((r) => [r.action, r]));
  for (const a of ['camera_model', 'camera_lora', 'camera_speed_lora', 'camera_text_encoder']) {
    assert.ok(byAction[a], `no install row for ${a}`);
    assert.ok(byAction[a].available, `${a} not installable with a valid dir`);
    assert.ok(byAction[a].label, `${a} has no label`);
  }
  assert.equal(byAction.camera_lora.present, false, 'a missing weight must read ✗');
  assert.equal(byAction.camera_model.present, true);
  // And exactly ONE row owns the shared VAE.
  assert.equal(rows.filter((r) => r.action === 'krea_vae').length, 1);
  // Without a ComfyUI folder the rows say where to go instead of offering a button.
  const noDir = installCatalog(caps({ dir_valid: false })).find((r) => r.action === 'camera_model');
  assert.equal(noDir.available, false);
  assert.match(noDir.hint, /ComfyUI folder/);
  // Disabled plugin: the rows are gone, not greyed.
  withPlugin(false);
  assert.ok(!installCatalog(caps({ dir_valid: true })).some((r) => r.action === 'camera_model'));
});

test('camera angles is a counted capability, never dropped from the total', () => {
  // The certification bug, third verse: "N of N ready" on a machine missing a
  // whole lane is worse than a red row.
  withPlugin();
  const summary = deriveCapabilitySummary({
    comfyui: { dir_valid: true, camera_ready: false, camera_missing: ['camera_model'] },
  });
  const row = summary.find((r) => r.label.includes('Camera angles'));
  assert.ok(row, 'camera angles missing from the readiness list');
  assert.equal(row.ok, false);
  assert.equal(row.topic, 'setup-camera-install');
  const ready = deriveCapabilitySummary({
    comfyui: { dir_valid: true, camera_ready: true, camera_missing: [] },
  }).find((r) => r.label.includes('Camera angles'));
  assert.equal(ready.ok, true);
  // ComfyUI down with the weights in place: pending, with its own wording.
  const pending = deriveCapabilitySummary({
    comfyui: { dir_valid: true, reachable: false, camera_ready: false, camera_missing: [] },
  }).find((r) => r.label.includes('Camera angles'));
  assert.equal(pending.pending, true);
  assert.ok(pending.note);
  // Plugin off: the row is gone — the lane does not exist on this install.
  withPlugin(false);
  assert.ok(!deriveCapabilitySummary({ comfyui: { dir_valid: true } })
    .some((r) => r.label.includes('Camera angles')));
});
