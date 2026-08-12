import assert from 'node:assert/strict';
import test from 'node:test';
import {
  MACHINE_LOAD_PREF_KEY, formatGb, loadTone, machineLoadSummary,
  readMachineLoadPref, shouldPoll, systemStatsSegments, writeMachineLoadPref,
} from './systemStats.js';

const memoryStore = () => {
  const data = {};
  return {
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => { data[key] = String(value); },
  };
};

test('a full machine reads as one line, work first, memory second', () => {
  const segments = systemStatsSegments({
    cpu_percent: 34, gpu_percent: 87,
    vram_used_gb: 21.3, vram_total_gb: 24,
    ram_used_gb: 45.2, ram_total_gb: 63.9,
  });
  assert.deepEqual(segments.map((s) => `${s.label} ${s.text}`),
    ['CPU 34%', 'GPU 87%', 'VRAM 21/24G', 'RAM 45/64G']);
});

test('a machine with no GPU draws two numbers, not four zeros', () => {
  // The whole reason the API omits fields: "GPU 0%" reads as an idle card.
  const segments = systemStatsSegments({
    cpu_percent: 12, ram_used_gb: 6.1, ram_total_gb: 16,
  });
  assert.deepEqual(segments.map((s) => s.key), ['cpu', 'ram']);
  assert.equal(segments.find((s) => s.key === 'ram').text, '6.1/16G');
});

test('a machine that answered nothing draws nothing at all', () => {
  assert.deepEqual(systemStatsSegments({}), []);
  assert.deepEqual(systemStatsSegments(null), []);
  assert.deepEqual(systemStatsSegments(undefined), []);
});

test('a total of zero is unknown, not a division by zero', () => {
  const segments = systemStatsSegments({ vram_used_gb: 0, vram_total_gb: 0 });
  assert.deepEqual(segments, []);
});

test('the tone steps at 50% and 80%, not only once a resource is in trouble', () => {
  assert.equal(loadTone(0.10), 'calm');
  assert.equal(loadTone(0.49), 'calm');
  assert.equal(loadTone(0.50), 'warm');
  assert.equal(loadTone(0.79), 'warm');
  assert.equal(loadTone(0.80), 'hot');
  assert.equal(loadTone(1), 'hot');
  // An unmeasured value must never paint a warning.
  assert.equal(loadTone(null), 'calm');
  assert.equal(loadTone(NaN), 'calm');
});

test('the tone of each segment comes from its own fraction, not the raw number', () => {
  const [cpu, gpu, vram, ram] = systemStatsSegments({
    cpu_percent: 95, gpu_percent: 5,
    vram_used_gb: 23.5, vram_total_gb: 24,
    ram_used_gb: 8, ram_total_gb: 64,
  });
  assert.equal(cpu.tone, 'hot');      // 95%
  assert.equal(gpu.tone, 'calm');     // 5%
  assert.equal(vram.tone, 'hot');     // 23.5/24 = 0.979
  assert.equal(ram.tone, 'calm');     // 8/64 = 0.125
});

test('gigabytes lose their decimal only where it is noise', () => {
  assert.equal(formatGb(21.3), '21');
  assert.equal(formatGb(23.99), '24');
  assert.equal(formatGb(9.6), '9.6');
  assert.equal(formatGb(4), '4');
  assert.equal(formatGb(null), '');
});

test('an out-of-range percentage is clamped instead of drawn as -3% or 140%', () => {
  const [low] = systemStatsSegments({ cpu_percent: -3 });
  const [high] = systemStatsSegments({ cpu_percent: 140 });
  assert.equal(low.text, '0%');
  assert.equal(high.text, '100%');
});

test('a hidden tab never polls, however enabled the widget is', () => {
  assert.equal(shouldPoll({ enabled: true, visibility: 'visible' }), true);
  assert.equal(shouldPoll({ enabled: true, visibility: 'hidden' }), false);
  assert.equal(shouldPoll({ enabled: false, visibility: 'visible' }), false);
  assert.equal(shouldPoll({ enabled: false, visibility: 'hidden' }), false);
});

test('an environment with no Page Visibility API still polls', () => {
  assert.equal(shouldPoll({ enabled: true, visibility: undefined }), true);
});

test('the readout is shown by default and remembers being folded away', () => {
  const store = memoryStore();
  assert.equal(readMachineLoadPref(store), true);
  writeMachineLoadPref(false, store);
  assert.equal(store.getItem(MACHINE_LOAD_PREF_KEY), 'off');
  assert.equal(readMachineLoadPref(store), false);
  writeMachineLoadPref(true, store);
  assert.equal(readMachineLoadPref(store), true);
});

test('storage that throws leaves the readout shown instead of crashing the board', () => {
  const hostile = {
    getItem() { throw new Error('storage disabled'); },
    setItem() { throw new Error('storage disabled'); },
  };
  assert.equal(readMachineLoadPref(hostile), true);
  assert.doesNotThrow(() => writeMachineLoadPref(false, hostile));
});

test('the tooltip never promises a GPU the machine does not have', () => {
  const cpuOnly = systemStatsSegments({ cpu_percent: 20, ram_used_gb: 4, ram_total_gb: 16 });
  const summary = machineLoadSummary(cpuOnly);
  assert.equal(summary, 'Machine load: CPU 20% · RAM 4/16G');
  assert.ok(!summary.includes('GPU'));
  assert.equal(machineLoadSummary([]), 'Machine load — nothing measurable here');
});
