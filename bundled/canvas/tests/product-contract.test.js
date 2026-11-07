import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import canvas from '../frontend/index.js';
import { registerDescriptor, resetRegistry, setEnabled, navItems, routes,
  helpTopics, whatsNewEntries } from '../../../frontend/src/plugins/registry.js';

test('Canvas contributes its complete product only when enabled', () => {
  resetRegistry();
  const manifest = JSON.parse(readFileSync(new URL('../plugin.json', import.meta.url)));
  assert.equal(registerDescriptor(canvas, { guideOwnership: manifest.guide_ownership }), true);
  setEnabled([]);
  assert.deepEqual(navItems(), []);
  assert.deepEqual(routes(), []);
  assert.deepEqual(helpTopics(), []);
  assert.deepEqual(whatsNewEntries(), []);
  setEnabled(['canvas']);
  assert.equal(navItems().find(item => item.to === '/canvas').plugin, 'canvas');
  assert.equal(routes().find(item => item.path === '/canvas').plugin, 'canvas');
  assert.ok(helpTopics().some(topic => topic.id === 'page-canvas'));
  assert.ok(whatsNewEntries().length);
  resetRegistry();
});

test('Canvas alone declares no other product dependency or installation payload', () => {
  const manifest = JSON.parse(readFileSync(new URL('../plugin.json', import.meta.url)));
  assert.deepEqual(manifest.requires, []);
  assert.deepEqual(manifest.owns.install_actions, []);
  assert.equal(manifest.compatibility.api, '>=1.9,<2');
  const app = readFileSync(new URL('../../../frontend/src/App.jsx', import.meta.url), 'utf8');
  assert.doesNotMatch(app, /<Route path="\/canvas"|import\('\.\/pages\/CanvasPage'\)|<NavLink to="\/canvas"/);
});
