/** A finished run writes its checkpoints to disk, but the panel never re-read the
 * list: both status polls only refreshed their own state, so a LoRA that had just
 * finished training stayed invisible until the browse filter changed or the page
 * was reloaded ("sometimes I have to refresh the page to see the LoRAs"). */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const panel = fs.readFileSync(new URL('./TrainingPanel.jsx', import.meta.url), 'utf8');

// Execute the actual handlers with controlled requests/state; no React or server.
function handler(name, bindings) {
  const start = panel.indexOf(`  const ${name} = `);
  assert.ok(start >= 0, `missing ${name}`);
  const end = panel.indexOf('\n  };', start) + '\n  };'.length;
  return new Function(...Object.keys(bindings),
    `${panel.slice(start, end)}; return ${name};`)(...Object.values(bindings));
}

test('Refresh reloads the graph that is on screen, with the current list filter', () => {
  for (const view of ['graph', 'list']) {
    const lists = [];
    let graphs = 0;
    const refresh = handler('refreshCheckpoints', {
      checkpointBase: 'custom.safetensors', checkpointTrainType: 'krea', checkpointVariant: 'base',
      checkpointsView: view,
      loadCheckpoints: (...args) => lists.push(args),
      loadDatasetGraph: () => { graphs += 1; },
    });
    refresh({ type: 'click' });
    assert.deepEqual(lists, [['custom.safetensors', 'krea', 'base']]);
    assert.equal(graphs, view === 'graph' ? 1 : 0);
  }
  assert.match(panel, /onClick=\{refreshCheckpoints\}/);
});

test('a slow old graph response cannot erase the latest results or replace them with an error', async () => {
  for (const failOld of [false, true]) {
    let state;
    const pending = [];
    const load = handler('loadDatasetGraph', {
      datasetGraphRequest: { current: 0 },
      setDatasetGraph: (value) => { state = value; },
      fetchDatasetLineage: () => new Promise((resolve, reject) => pending.push({ resolve, reject })),
    });
    const old = load();
    const latest = load();
    const tree = { nodes: [{ record_id: 12, checkpoints: [{ step: 100 }] }] };
    pending[1].resolve(tree);
    await latest;
    if (failOld) pending[0].reject(new Error('old request failed'));
    else pending[0].resolve({ nodes: [] });
    await old;
    assert.deepEqual(state, { tree });
  }
});

test('results autoload is independent of the slow trainer/model catalog', () => {
  const effects = panel.slice(panel.indexOf('  // The manager is "open"'),
    panel.indexOf('  // The displayed Training recipe'));
  assert.doesNotMatch(effects, /!baseInfo|caps\.training_visible/);
  assert.match(effects, /loadDatasetGraph\(\)/);
  assert.match(effects, /loadCheckpoints\(/);
});

test('a run finishing on this dataset re-reads the checkpoints it produced', () => {
  assert.match(panel, /const runActiveHere = Boolean\(/);
  // both lanes count: a cloud run produces checkpoints exactly like a local one
  assert.match(panel, /status\.in_progress && status\.current\?\.dataset_id === ds\.currentId\)\s*\|\|\s*cloudActiveHere/);
  // acts on the FALLING edge only — "was active, now is not" means new files exist
  assert.match(panel, /if \(runWasActiveHere\.current && !runActiveHere\) \{/);
  assert.match(panel, /runWasActiveHere\.current = runActiveHere;/);
  assert.match(panel, /loadCheckpoints\(\);/);
});

test('the graph view is refreshed too, so the two views cannot disagree', () => {
  assert.match(panel,
    /if \(checkpointsView === 'graph' && checkpointManagerOpen\) loadDatasetGraph\(\);/);
});

test('the watcher depends on a boolean, not on the polled cloud object', () => {
  // The cloud poll returns a fresh object every 5s; depending on it directly would
  // re-run the effect constantly instead of only on the transition that matters.
  assert.match(panel, /\}, \[runActiveHere\]\);/);
});
