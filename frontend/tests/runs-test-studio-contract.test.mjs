/* Node cannot parse JSX, so this text contract protects the four Runs surfaces
   that open the selected dataset in Test Studio. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import { getHelpTopic } from '../src/help/helpRegistry.js';
import { WHATS_NEW } from '../src/whatsNew.js';
import { WHATS_NEW_ARCHIVE } from '../src/whatsNewArchive.js';
import { studioRunTarget } from '../src/utils/studioRunNavigation.js';

// The entry under test may have moved to the archive since it shipped
// (see whatsNew.js, rule "Keep the list tidy") — search the union.
const ALL_WHATS_NEW = [...WHATS_NEW, ...WHATS_NEW_ARCHIVE];

const source = fs.readFileSync(
  new URL('../src/components/runs/RunsHub.jsx', import.meta.url),
  'utf8',
).replace(/\r\n/g, '\n')
  + fs.readFileSync(new URL('../../bundled/cloud_training/frontend/CloudRunsHub.jsx', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
const guide = fs.readFileSync(
  new URL('../../docs/guide/using-the-app.md', import.meta.url),
  'utf8',
).replace(/\r\n/g, '\n');

test('Runs uses one dataset-aware helper for every Test Studio surface', () => {
  assert.match(source,
    /const openTestStudio = \(id, family\) => \{\s*const target = studioRunTarget\(id, family\);\s*if \(target\) navigate\(target\);/);
  assert.equal((source.match(/onClick=\{\(\) => openTestStudio\(/g) || []).length, 4,
    'history cards, active local/cloud runs, and folded recent groups stay covered');
  assert.equal((source.match(/\/>Test in Studio/g) || []).length, 4,
    'each Runs surface keeps a visible, text-labelled Studio action');
  assert.match(source, /data\.local_active\.current\.dataset_id != null/);
  assert.match(source, /group\.datasetId != null/);
});

test('run navigation selects the trained family and image lane instead of a remembered alternative', () => {
  for (const family of ['flux', 'anima', 'qwenimage21']) {
    const target = studioRunTarget(17, family);
    const [path, query] = target.split('?');
    assert.equal(path, '/dataset/studio/17');
    assert.equal(new URLSearchParams(query).get('family'), family);
    assert.equal(new URLSearchParams(query).get('lane'), 'image');
  }
  assert.equal(studioRunTarget(null, 'qwenimage21'), null);
  assert.equal(new URLSearchParams(studioRunTarget(17).split('?')[1]).get('family'), null);
  assert.equal((source.match(/openTestStudio\(run\.dataset_id, run\.train_type\)/g) || []).length, 2,
    'both history cards and active cloud rows retain the run family');
  assert.match(source, /openTestStudio\(data\.local_active\.current\.dataset_id, data\.local_active\.current\.train_type\)/);
  assert.match(source, /openTestStudio\(group\.datasetId, testRun\.train_type\)/);
});

test('Runs-to-Studio is discoverable in help, the guide, and What’s New', () => {
  const topic = getHelpTopic('runs-test-in-studio');
  assert.equal(topic?.app.route, '/cloud');
  assert.deepEqual(topic?.guide, {
    chapter: 'using-the-app',
    anchor: 'test-a-run-straight-from-runs',
  });
  assert.match(guide, /^## Test a run straight from Runs$/m);
  assert.match(guide, /🧪 Test in Studio/);

  const news = ALL_WHATS_NEW.find((entry) => entry.id === '2026-07-30-runs-test-in-studio');
  // Archived → no in-app target, by doctrine (whatsNew.js, "Keep the list tidy").
  assert.equal(news?.to, undefined);
  assert.match(news?.blurb || '', /🧪 Test in Studio/);
});
