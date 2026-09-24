// ⚡ The Render panel's acceleration choice — the contract, read as text.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const read = (p) => readFileSync(join(here, p), 'utf8').replace(/\r\n/g, '\n');
const panel = read("../../../../../../bundled/video/frontend/studio/video/VideoOptionsPanel.jsx");
const studio = read("../../../../../../bundled/video/frontend/studio/video/VideoTestStudio.jsx");
import { VIDEO_INSTALL_LABELS } from '../../../../../../bundled/video/frontend/lib/videoInstallLabels.js';
import { VIDEO_STUDIO_INSTALL_ORDER, videoStudioInstallPlan } from '../../../../../../bundled/video/frontend/lib/videoSetup.js';

test('the Turbo checkbox became a select over the arena podium, resolved by the server', () => {
  assert.doesNotMatch(panel, /set\(\{ turbo: v \}\)/, 'no checkbox posts a bare turbo flag any more');
  assert.match(panel, /data-testid="video-accel"/);
  assert.match(panel, /options\.accelerations : ACCELERATIONS/, 'the server list first, the static shape before it arrives');
  assert.match(panel, /disabled=\{a\.available === false\}/, 'a choice this machine cannot run is greyed');
  assert.match(panel, /Setup downloads it/, 'and says how to get it');
  assert.match(panel, /min-h-10 lg:min-h-0/, 'finger-sized on a phone');
});

test('the studio defaults to larryvrh, follows availability, reuses and reads back the name', () => {
  assert.match(studio, /accel: 'turbo', eros: false/);
  assert.match(studio, /pickAvailableAccel\(o\.accel, d\.accelerations\)/);
  assert.match(studio, /accel: clipAccel\(clip\)/, 'reuse restores the acceleration that made the clip');
  assert.doesNotMatch(studio, /turbo: !!clip\.turbo/);
});

test('Setup offers the two new weights beside larryvrh’s, in the Video Test Studio plan', () => {
  for (const id of ['h3_turbo_lora', 'h3_parasyte_lora', 'h3_dareties_lora']) {
    assert.match(VIDEO_INSTALL_LABELS[id], /^Video acceleration:/, `${id} has a label`);
    assert.ok(VIDEO_STUDIO_INSTALL_ORDER.includes(id), `${id} is in the install plan`);
    assert.deepEqual(videoStudioInstallPlan({ comfyui: { dir_valid: true, video_studio_missing: [{ action: id }] } }), [id]);
  }
});
