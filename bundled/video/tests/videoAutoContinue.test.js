import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { autoLimit, autoIsBusy, autoPhaseLabel, canAutoContinue } from '../frontend/studio/video/videoAutoContinue.js';

test('Auto continuation cannot replace a reference clip or reference dials with FL2V', () => {
  assert.equal(canAutoContinue({ status: 'done', mode: 'ref2va' }), false);
  assert.equal(canAutoContinue({ status: 'done', mode: 'i2v' }, 'ref2va'), false);
  assert.equal(canAutoContinue({ status: 'generating', mode: 'i2v' }), false);
  assert.equal(canAutoContinue({ status: 'done', mode: 'i2v' }), true);
  assert.equal(canAutoContinue({ status: 'done', mode: 't2v' }, 't2v'), true);
});

test('unlimited is explicit zero; a cleared or malformed limit does not become unlimited', () => {
  for (const value of ['', ' ', null, undefined, 'three', -1, '1.5', Infinity, 10001]) {
    assert.equal(autoLimit(value), null);
  }
  assert.equal(autoLimit('0'), 0);
  assert.equal(autoLimit('3'), 3);
});

test('turning off Auto still blocks a new loop while the current clip drains', () => {
  const session = { phase: 'generating', enabled: false, draining: true, completed: 2 };
  assert.equal(autoIsBusy(session), true);
  assert.match(autoPhaseLabel(session), /no next clip/);
  assert.equal(autoIsBusy({ ...session, draining: false, phase: 'stopped' }), false);
});

test('a paused take can be ended: Stop Auto is offered beside Resume', async () => {
  const { readFileSync } = await import('node:fs');
  const { fileURLToPath } = await import('node:url');
  const { dirname, join } = await import('node:path');
  const here = dirname(fileURLToPath(import.meta.url));
  const panel = readFileSync(join(here, '../frontend/studio/video/AutoContinuePanel.jsx'), 'utf8');
  // An app restart leaves the loop paused; without this the only way out of a
  // paused session was to start another one from a clip.
  assert.match(panel, /\(active \|\| session\?\.phase === 'paused'\) && <button type="button" onClick=\{onStop\}/);
  assert.match(panel, /session\.phase !== 'paused'\)\}/, 'the button is live while paused');
  assert.match(autoPhaseLabel({ phase: 'paused', completed: 2 }), /Stop Auto to end this take/);
  assert.equal(autoIsBusy({ phase: 'paused', enabled: false, draining: false }), false, 'paused is not busy');
});


test('the panel names the LoRA the take kept and the clip it came from (2026-09-06)', () => {
  // ⏭ A take keeps its chain's LoRA whatever the panel shows; the panel says
  // which one and from which part, so a take that changed character is read
  // off the panel, not guessed from the render.
  const src = readFileSync(new URL('../frontend/studio/video/AutoContinuePanel.jsx', import.meta.url), 'utf8');
  assert.match(src, /\{session\?\.lora && \(/);
  assert.match(src, /data-testid="auto-continue-lora"/);
  assert.match(src, /Character LoRA \{String\(session\.lora\)\.split\('\/'\)\.pop\(\)\}/);
  assert.match(src, /session\.lora_from_clip_id \? ` · kept from clip #\$\{session\.lora_from_clip_id\}` : ''/);
  // …and says when the panel's own choice was set aside, with the way out.
  assert.match(src, /data-testid="auto-continue-panel-lora"/);
  assert.match(src, /was not used: a take keeps its chain’s LoRA\./);
  assert.match(src, /render one part by hand with the other LoRA/);
});
