/* Wiring contract for the ✨ Score interpreter picker.
 *
 * The logic is unit-tested in scoringPython.test.js; what a rewrite of the
 * workspace silently loses is the WIRING — the entry point, the refresh after a
 * change, the read-only promise in the dialog. Those are one-line facts with no
 * runtime assertion anywhere, exactly the kind that dies unnoticed.
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const ws = fs.readFileSync(new URL('./BankWorkspace.jsx', import.meta.url), 'utf8');
const dialog = fs.readFileSync(new URL('./ScoringPythonDialog.jsx', import.meta.url), 'utf8');
const device = fs.readFileSync(new URL('./bankScoreDevice.js', import.meta.url), 'utf8');

test('the picker is reachable from BOTH dead ends: a CPU pass, and no extra at all', () => {
  assert.match(ws, /scoreNote\?\.tone === 'warn' \|\| !caps\.bank_scoring/);
  // …but never before the capabilities have loaded: EMPTY_CAPS has no
  // bank_scoring, so an ungated check flashes "Score needs its own packages" on
  // every open of a bank that is perfectly set up.
  assert.match(ws, /!capsLoading && \(scoreNote\?\.tone === 'warn'/);
  assert.match(ws, /const \{ caps, loading: capsLoading, refresh: refreshCaps \}/);
  assert.match(ws, /Use a GPU Python I already have/);
  assert.match(ws, /<ScoringPythonDialog/);
});

test('a machine with no NVIDIA card is never sent hunting for interpreters', () => {
  // scoreDeviceNote only returns tone 'warn' when gpu_present — the condition
  // above therefore cannot fire on a card-less machine while the extra is set up.
  assert.match(device, /if \(!info\.gpu_present\)/);
  assert.match(device, /tone: 'info'/);
});

test('changing the interpreter re-probes the capabilities, not just the payload', () => {
  // bank_scoring / score_device are both server-side probes with their own
  // caches: refreshing one and not the other leaves the panel contradicting
  // itself (Score enabled, still warning about the CPU).
  assert.match(ws, /refreshCaps\(true\)/);
  assert.match(ws, /refresh: refreshCaps \} = useCapabilities\(\)/);
});

test('the dialog promises — and shows — that nothing is installed for the user', () => {
  assert.match(dialog, /never changed/);
  assert.match(dialog, /will not install into an environment we did not create/);
  assert.match(dialog, /install_command/);
});

test('the dialog can re-probe after a manual install, and can be undone', () => {
  assert.match(dialog, /force: true/);
  assert.match(dialog, /Check again/);
  assert.match(dialog, /Back to the app default/);
  assert.match(dialog, /choose\(''\)/);
});

test('the CPU warning offers the reuse route before the 2.5 GB download', () => {
  const warn = device.slice(device.indexOf("tone: 'warn'"));
  assert.ok(warn.indexOf('already has a working CUDA PyTorch') < warn.indexOf('CUDA_TORCH_DOWNLOAD'),
    'borrowing an existing interpreter is named first — the download is the fallback');
});
