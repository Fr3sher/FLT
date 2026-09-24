/* 📷 The two halves of the camera vocabulary must not drift.
 *
 * The Python catalog (lds_camera_angles/camera_angles.py) is what the server
 * validates and renders; the JS tables (the core's utils/cameraAngles.js and
 * the plugin's cameraLane.js) are what the picker draws and what a tile
 * labels. Every `id` is written into user databases, so the two files are
 * read as TEXT here and compared row for row — a token that exists on one
 * side only would render some other angle under the name of the one asked
 * for, and no unit test on either side alone can see it. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  AZIMUTHS, DISTANCES, ELEVATIONS, MAX_VIEWS, REFERENCE_POSE, TRIGGER,
} from '../frontend/lib/cameraLane.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..', '..', '..');
const PY = path.join(HERE, '..', 'lds_camera_angles', 'camera_angles.py');
const source = fs.readFileSync(PY, 'utf8');

/** Every `{'id': ..., 'token': ..., 'label': ...}` row of one Python tuple. */
function pythonRows(name) {
  const block = source.slice(source.indexOf(`${name} = (`));
  const end = block.indexOf('\n)');
  assert.ok(end > 0, `${name} tuple not found in camera_angles.py`);
  const rows = [];
  for (const m of block.slice(0, end).matchAll(/'id':\s*'([^']+)'[^}]*?'token':\s*'([^']+)'[^}]*?'label':\s*'([^']+)'/g)) {
    rows.push({ id: m[1], token: m[2], label: m[3] });
  }
  return rows;
}

for (const [name, table] of [['AZIMUTHS', AZIMUTHS], ['ELEVATIONS', ELEVATIONS], ['DISTANCES', DISTANCES]]) {
  test(`${name}: id, token and label match the Python catalog row for row`, () => {
    const py = pythonRows(name);
    assert.equal(py.length, table.length, `${name}: ${py.length} Python rows vs ${table.length} JS rows`);
    py.forEach((row, i) => {
      assert.equal(table[i].id, row.id, `${name}[${i}].id`);
      assert.equal(table[i].token, row.token, `${name}[${i}].token`);
      assert.equal(table[i].label, row.label, `${name}[${i}].label`);
    });
  });
}

test('the trigger, the ceiling and the reference pose are the same on both sides', () => {
  assert.ok(source.includes(`TRIGGER = '${TRIGGER}'`),
    `camera_angles.py must define TRIGGER = '${TRIGGER}'`);
  assert.equal(MAX_VIEWS, 96);
  assert.ok(source.includes('MAX_VIEWS_PER_RUN = POSE_COUNT'),
    'camera_angles.py must define MAX_VIEWS_PER_RUN = POSE_COUNT');
  const [az, el, di] = REFERENCE_POSE.split('/');
  assert.ok(source.includes(`REFERENCE_POSE = ('${az}', '${el}', '${di}')`),
    `camera_angles.py must define REFERENCE_POSE = ('${az}', '${el}', '${di}')`);
});

test('both tables store the derivation kind under one spelling', () => {
  // The core keeps the historical row vocabulary; the independent product
  // emits that same persisted value. Every side must store a view under one kind,
  // or one surface's badge lies about the other's rows the day an image is
  // promoted between them.
  for (const mod of ['lora_test_studio.py', 'face_dataset_service.py']) {
    const src = fs.readFileSync(path.join(REPO, 'backend', 'app', 'services', mod), 'utf8');
    assert.ok(src.includes("CAMERA_ANGLE = 'camera_angle'"),
      `${mod} must store derivation_kind = camera_angle`);
  }
  const views = fs.readFileSync(path.join(HERE, '..', 'lds_camera_angles', 'views.py'), 'utf8');
  assert.ok(views.includes("CAMERA_ANGLE = 'camera_angle'"), 'the independent product preserves the persisted derivation vocabulary');
});

test('the caption phrase never leaks a prompt token', () => {
  // The phrase goes into TRAINING captions; `<sks>` or the LoRA's shot tokens
  // there would teach the trigger to expect them.
  const block = source.slice(source.indexOf('def pose_caption_phrase'));
  const body = block.slice(0, block.indexOf('\ndef ', 10) > 0 ? block.indexOf('\ndef ', 10) : undefined);
  assert.ok(!body.includes('<sks>'), 'the caption phrase must not carry the trigger');
  for (const row of [...AZIMUTHS, ...ELEVATIONS, ...DISTANCES]) {
    assert.ok(!body.includes(`'${row.token}'`), `caption phrase leaks the token ${row.token}`);
  }
});
