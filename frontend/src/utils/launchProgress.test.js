import test from 'node:test';
import assert from 'node:assert/strict';
import {
  formatElapsed,
  launchButtonLabel,
  launchProgressView,
  podBootFailureView,
  stopButtonLabel,
} from './launchProgress.js';

// Verbatim shape of what the backend forwards while a pod boots, taken from
// launch_view() with the production config that killed run #134
// (ready_timeout_minutes: 25).
const BOOTING = {
  active_step: 'boot',
  detail: 'Waiting for the pod to boot — pod up — waiting for the UI to answer',
  elapsed_seconds: 8 * 60 + 12,
  steps: [
    { key: 'staging', label: 'Preparing the dataset', state: 'done' },
    { key: 'offer', label: 'Searching for a GPU offer', state: 'done' },
    { key: 'boot', label: 'Renting the machine and booting the pod', state: 'active' },
    { key: 'upload', label: 'Uploading the dataset', state: 'pending' },
    { key: 'start', label: 'Starting the training job', state: 'pending' },
  ],
  boot_idle_limit_seconds: 25 * 60,
  boot_budget_seconds: 90 * 60,
};

test('a booting pod reads as a step plus a clock, not as a frozen sentence', () => {
  const v = launchProgressView(BOOTING);
  assert.equal(v.headline, 'Renting the machine and booting the pod — 8m elapsed');
  assert.equal(v.activeKey, 'boot');
  assert.equal(v.detail, 'Waiting for the pod to boot — pod up — waiting for the UI to answer');
});

test('the boot step announces its deadline — the answer run #134 never gave', () => {
  const v = launchProgressView(BOOTING);
  assert.match(v.note, /25 min/);
  assert.match(v.note, /released automatically/);
});

test('only the boot step has a deadline to announce', () => {
  const uploading = {
    ...BOOTING,
    steps: BOOTING.steps.map((s) => ({
      ...s,
      state: s.key === 'upload' ? 'active' : s.key === 'boot' ? 'done' : s.state,
    })),
  };
  assert.equal(launchProgressView(uploading).note, null);
  assert.equal(launchProgressView(uploading).activeKey, 'upload');
});

test('a boot deadline the install disabled is not invented', () => {
  assert.equal(launchProgressView({ ...BOOTING, boot_idle_limit_seconds: 0 }).note, null);
});

test('nothing to report degrades to null — the caller keeps its phase sentence', () => {
  assert.equal(launchProgressView(null), null);
  assert.equal(launchProgressView(undefined), null);
  assert.equal(launchProgressView({}), null);
  // Every step done and none active = the job is running; the checklist goes.
  assert.equal(launchProgressView({
    ...BOOTING, steps: BOOTING.steps.map((s) => ({ ...s, state: 'done' })),
  }), null);
});

test('an empty phase_detail is dropped rather than printed as a blank line', () => {
  assert.equal(launchProgressView({ ...BOOTING, detail: '   ' }).detail, null);
});

test('the clock stays readable from one second to two hours', () => {
  assert.equal(formatElapsed(0), '0s');
  assert.equal(formatElapsed(42), '42s');
  assert.equal(formatElapsed(59.6), '1m');
  assert.equal(formatElapsed(25 * 60), '25m');
  assert.equal(formatElapsed(3 * 3600 + 4 * 60), '3h 04m');
  assert.equal(formatElapsed(-5), '0s');
  assert.equal(formatElapsed(undefined), '0s');
});

// The real run-134 row: status 'error', pod destroyed, error verbatim.
const RUN_134 = {
  status: 'error',
  error: 'pod did not become ready in time — no boot progress for 25 min: '
    + 'pod up — waiting for the UI to answer',
};

test('the boot timeout is explained, including what became of the machine', () => {
  const v = podBootFailureView(RUN_134);
  assert.equal(v.title, 'The rented machine never started');
  assert.match(v.message, /released/);
  assert.match(v.message, /no longer billing/);
  assert.match(v.message, /again picks a different one/);
});

test('only a boot timeout gets the boot-timeout explanation', () => {
  assert.equal(podBootFailureView({ status: 'error', error: 'CUDA out of memory' }), null);
  // A kept pod is still billing — the "released" sentence would be false.
  assert.equal(podBootFailureView({ ...RUN_134, status: 'error_pod_kept' }), null);
  assert.equal(podBootFailureView({ status: 'training' }), null);
  assert.equal(podBootFailureView(null), null);
});

test('ending a launch is not worded like abandoning a trained run', () => {
  assert.equal(stopButtonLabel('preparing'), 'Cancel launch');
  assert.equal(stopButtonLabel('provisioning'), 'Cancel launch');
  assert.equal(stopButtonLabel('uploading'), 'Cancel launch');
  assert.equal(stopButtonLabel('training'), 'Stop run');
  assert.equal(stopButtonLabel('downloading'), 'Stop run');
  assert.equal(stopButtonLabel(undefined), 'Stop run');
});

test('the dialog button counts, so a working request is not read as a hang', () => {
  assert.equal(launchButtonLabel({ launching: false, elapsedSeconds: 0, fullMode: false }),
    '☁️ Rent & train');
  assert.equal(launchButtonLabel({ launching: false, elapsedSeconds: 0, fullMode: true }),
    '☁️ Rent GPU & train full model');
  // The first seconds still feel instant — no counter flicker for a fast POST.
  assert.equal(launchButtonLabel({ launching: true, elapsedSeconds: 1 }), 'Launching…');
  assert.equal(launchButtonLabel({ launching: true, elapsedSeconds: 34 }), 'Launching… 34s');
  assert.equal(launchButtonLabel({ launching: true, elapsedSeconds: 95 }), 'Launching… 1m');
});
