import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import { runsHubContinueLanes } from '../../../bundled/cloud_training/frontend/lib/continueLanes.js';

const read = rel => fs.readFileSync(new URL(rel, import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const cloud = read('../../../bundled/cloud_training/frontend/CloudRunsHub.jsx');
const controller = read('../components/runs/useRunsHubContinue.js');
const local = read('../components/runs/localContinuation.js');
const canvasRequest = read('./canvasContinue.js');
const page = fs.readFileSync(new URL('../components/runs/RunsHub.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');

const RUN = { run_id: 7, dataset_id: 3, train_type: 'zimage', variant: 'turbo' };
const OK = { aitoolkitValid: true, configured: true, limit: 2, actives: [] };

test('both lanes are open when nothing is running and both are set up', () => {
  const lanes = runsHubContinueLanes(RUN, OK);
  assert.equal(lanes.local.available, true);
  assert.equal(lanes.cloud.available, true);
});

test('a blocked lane keeps its slot and states its reason — it never disappears', () => {
  const lanes = runsHubContinueLanes(RUN, { ...OK, aitoolkitValid: false });
  assert.equal(lanes.local.available, false);
  assert.match(lanes.local.reason, /ai-toolkit/);
  assert.equal(lanes.cloud.available, true);
  // the cloud key missing closes the OTHER lane the same way
  const noKey = runsHubContinueLanes(RUN, { ...OK, configured: false });
  assert.equal(noKey.cloud.available, false);
  assert.match(noKey.cloud.reason, /vast\.ai API key/);
});

test('local is single-flight for the WHOLE machine — a run on another dataset closes it', () => {
  // The hub lists runs of many datasets: unlike the per-dataset cloud guard,
  // the local one must not care WHICH dataset is currently training.
  const lanes = runsHubContinueLanes(RUN, {
    ...OK, localActive: { current: { dataset_id: 999 } },
  });
  assert.equal(lanes.local.available, false);
  assert.match(lanes.local.reason, /already running on this machine/);
  assert.equal(lanes.cloud.available, true);
});

test('an active run on the dataset no longer closes the cloud lane — the server confirm asks instead', () => {
  const otherDataset = runsHubContinueLanes(RUN, {
    ...OK, actives: [{ dataset_id: 42, train_type: 'zimage' }],
  });
  assert.equal(otherDataset.cloud.available, true, 'another dataset training must not block this run');

  const otherFamily = runsHubContinueLanes(RUN, {
    ...OK, actives: [{ dataset_id: 3, train_type: 'sdxl' }],
  });
  assert.equal(otherFamily.cloud.available, true, 'another family on the same dataset is allowed');

  // A same-family sibling used to hard-close the lane here, which made the
  // server's PARALLEL_RUN: confirm unreachable — the guard lives server-side
  // now, as a question ("second pod, billed separately — launch anyway?").
  const sameBoth = runsHubContinueLanes(RUN, {
    ...OK, actives: [{ dataset_id: 3, train_type: 'zimage' }],
    familyLabel: () => 'Z-Image',
  });
  assert.equal(sameBoth.cloud.available, true);
});

test('the hub cloud lane goes through the confirm loop, so PARALLEL_RUN: can be answered', () => {
  assert.match(cloud, /return postWithConfirmations\(/);
  assert.match(cloud, /\(next\) => postJson\(url, next\)/);
  assert.match(cloud, /'\/api\/dataset\/train\/cloud\/continue'/);
});

test('the concurrency limit closes the cloud lane and names the count', () => {
  const lanes = runsHubContinueLanes(RUN, {
    ...OK, limit: 1, actives: [{ dataset_id: 42, train_type: 'sdxl' }],
  });
  assert.equal(lanes.cloud.available, false);
  assert.match(lanes.cloud.reason, /limit reached \(1\/1\)/);
});

test('a run with no dataset can only go to the cloud', () => {
  const lanes = runsHubContinueLanes({ run_id: 9, train_type: 'zimage' }, OK);
  assert.equal(lanes.local.available, false);
  assert.match(lanes.local.reason, /only be continued in the cloud/);
  assert.equal(lanes.cloud.available, true);
});

test('no run open → no picker at all (the dialog stays single-lane)', () => {
  assert.equal(runsHubContinueLanes(null, OK), null);
});

test('the Runs hub actually offers the picker and routes the local lane', () => {
  assert.match(page, /<ContinueDialog \{\.\.\.dialog\}/);
  assert.match(controller, /initialFromStep: initialStep, lanes, transportPlan/);
  assert.match(controller, /localContinuationAvailability\(target/);
  assert.match(cloud, /runsHubContinueLanes\(run/);
  assert.match(controller, /if \(lane === 'local'\)/);
  assert.match(controller, /localContinuationRequest\(run, selected\)/);
  assert.match(local, /canvasContinueRequest\(run, selected/);
  assert.match(canvasRequest, /train\/continue/);
  for (const key of ['base_model', 'train_type', 'variant']) assert.ok(canvasRequest.includes(key));
  assert.match(local, /expected_record_id = selected.expectedRecordId/);
});

test('a local continuation loops on the confirmable refusals like the panel does', () => {
  assert.match(controller, /await postWithConfirmations\(body => postJson\(request.url, body\), request.body, 'Continue anyway \(force\)'\)/);
  assert.match(controller, /continueAttemptOutcome\(\{ thrown \}\)/);
  assert.match(controller, /else setError\(outcome.error\)/);
});

test('the confirmable refusal markers have ONE definition, shared by both mounts', () => {
  const util = fs.readFileSync(new URL('./trainingRefusals.js', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
  const panel = fs.readFileSync(
    new URL('../components/dataset/TrainingPanel.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
  for (const marker of ['MISMATCH_CAPTION: ', 'UNCAPTIONED: ',
    'CAPTION_QUALITY: ', 'CUSTOM_WEIGHTS_UNVERIFIED: ']) {
    assert.ok(util.includes(marker), `${marker} must live in the shared util`);
  }
  // The readiness floor is a marker too, and it also belongs to the util — the
  // Runs hub's ↻ Retry answers it (GitHub #23), the dataset panel's own
  // "Continue anyway" checkbox answers it there.
  assert.ok(util.includes('NOT_READY: '), 'NOT_READY: must live in the shared util');
  // The panel imports from the shared util — WHICH names it takes is not the
  // contract. It gained `postWithConfirmations` when the cloud launch stopped
  // hand-rolling a retry that could never run: that loop tested `d.ok === false`
  // around a client that THROWS on a 409, so a confirmable refusal reached the
  // user as an error toast asking a question it gave no way to answer. Pinning
  // the exact import line would have made that fix look like a violation.
  assert.match(panel, /import \{[^}]*confirmableRetryFlag[^}]*\} from '\.\.\/\.\.\/utils\/trainingRefusals'/);
  assert.match(controller, /from '\.\.\/\.\.\/utils\/trainingRefusals\.js'/);
  assert.match(cloud, /from '@lds\/plugin-sdk\/training'/);
  assert.doesNotMatch(panel, /const CONFIRMABLE_REFUSALS = \[/);
  assert.doesNotMatch(page, /const CONFIRMABLE_REFUSALS = \[/);
  // neither mount may hand-roll the confirm loop again
  assert.doesNotMatch(page, /\[flag\]: true \}/);
});


test('Cloud contributes its continuation transport only while enabled; local remains independent', async t => {
  const { default: descriptor } = await import('../../../bundled/cloud_training/frontend/index.js');
  const { contributions, registerDescriptor, resetRegistry, setEnabled } = await import('../plugins/registry.js');
  const { localContinuationRequest } = await import('../components/runs/localContinuation.js');
  const manifest = JSON.parse(read('../../../bundled/cloud_training/plugin.json'));
  resetRegistry();
  t.after(resetRegistry);
  assert.equal(registerDescriptor(descriptor, { guideOwnership: manifest.guide_ownership }), true);
  setEnabled([]);
  assert.deepEqual(contributions('training.continue.lane', 'dataset'), []);
  const saved = { source: 'local', dataset_id: 3, record_id: 17, train_type: 'zimage',
    variant: 'turbo', base_model: 'fixture.safetensors', resume_steps: [100] };
  const payload = { lane: 'local', fromStep: 100, extraSteps: 50 };
  const localBefore = localContinuationRequest(saved, payload);
  assert.equal(localBefore.url, '/api/dataset/3/train/continue');
  assert.equal(localBefore.body.expected_record_id, 17);
  setEnabled(['cloud_training']);
  const [lane] = contributions('training.continue.lane', 'dataset');
  assert.equal(lane.id, 'cloud');
  assert.deepEqual(lane.request({ node: { source: 'cloud', run_id: 8 },
    body: { from_step: 100, extra_steps: 50, base_model: 'ignored', train_type: 'zimage' } }), {
    url: '/api/dataset/train/cloud/continue', body: { run_id: 8, from_step: 100, extra_steps: 50 },
  });
  assert.deepEqual(lane.request({ node: saved, body: localBefore.body }), {
    url: '/api/dataset/3/train/cloud/continue-local', body: localBefore.body,
  });
  setEnabled([]);
  assert.deepEqual(contributions('training.continue.lane', 'dataset'), []);
  assert.deepEqual(localContinuationRequest(saved, payload), localBefore);
});
