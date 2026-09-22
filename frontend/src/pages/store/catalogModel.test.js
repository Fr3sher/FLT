import assert from 'node:assert/strict';
import test from 'node:test';
import { availableUpdateIds, canSelectEntry, catalogEntries, catalogView, matchesFilter } from './catalogModel.js';

const release = { manifest: { id: 'example', version: '2.0.0' }, compatibility_issues: [] };
const product = { id: 'example', recommended: release, update_available: true };

test('catalog and installed registry share one card while keeping installed state authoritative', () => {
  const plugin = { id: 'example', version: '1.0.0', active: true, desired_enabled: false, pending_action: 'disable' };
  const entries = catalogEntries([product], [plugin]);
  assert.equal(entries.length, 1);
  assert.equal(entries[0].plugin, plugin);
  assert.equal(entries[0].release, release);
  assert.equal(canSelectEntry(entries[0]), false);
});

test('offline and empty catalogs preserve local-only and newly staged installs', () => {
  const local = { id: 'local', state: 'disabled' };
  const pending = { id: 'staged', active: false, pending_action: 'install' };
  const entries = catalogEntries(undefined, [local, pending]);
  assert.deepEqual(entries.map(entry => entry.plugin), [local, pending]);
  assert(entries.every(entry => matchesFilter(entry, 'installed')));
  assert(entries.every(entry => !canSelectEntry(entry) && !matchesFilter(entry, 'updates')));
});

test('installed and update filters use distinct membership without duplicating cards', () => {
  const entries = catalogEntries([product, { id: 'new', recommended: release }], [{ id: 'example' }, { id: 'local' }]);
  assert.deepEqual(entries.filter(entry => matchesFilter(entry, 'installed')).map(entry => entry.id), ['example', 'local']);
  assert.deepEqual(entries.filter(entry => matchesFilter(entry, 'updates')).map(entry => entry.id), ['example']);
  assert.equal(entries.filter(entry => matchesFilter(entry, 'all')).length, 3);
});

test('only compatible new releases and updates are eligible for bulk installation', () => {
  assert(canSelectEntry(catalogEntries([product], [{ id: 'example' }])[0]));
  assert(!canSelectEntry(catalogEntries([{ ...product, update_available: false }], [{ id: 'example' }])[0]));
  assert(!canSelectEntry(catalogEntries([{ ...product, recommended: { ...release, compatibility_issues: [{ message: 'Upgrade LDS' }] } }])[0]));
  assert(!canSelectEntry(catalogEntries([{ id: 'no-release' }])[0]));
});

test('old plugin links open the matching filter and purchases remains separate', () => {
  for (const [tab, filter] of [['discover', 'all'], ['installed', 'installed'], ['updates', 'updates']]) {
    assert.deepEqual(catalogView(new URLSearchParams({ tab, plugin: 'example' })), { tab: 'plugins', filter });
  }
  assert.deepEqual(catalogView(new URLSearchParams('tab=purchases')), { tab: 'purchases', filter: 'all' });
  assert.deepEqual(catalogView(new URLSearchParams('tab=plugins&filter=installed')), { tab: 'plugins', filter: 'installed' });
  assert.deepEqual(catalogView(new URLSearchParams('tab=unknown&filter=unknown')), { tab: 'plugins', filter: 'all' });
});

test('update all includes disabled installed plugins but excludes new, incompatible and pending packages', () => {
  const products = ['active', 'disabled', 'pending', 'incompatible', 'new', 'current'].map(id => ({
    ...product, id, update_available: id !== 'current',
    recommended: { ...release, compatibility_issues: id === 'incompatible' ? ['Requires a newer LDS'] : [] },
  }));
  const installed = ['active', 'disabled', 'pending', 'incompatible', 'current'].map(id => ({
    id, active: id !== 'disabled', pending_action: id === 'pending' ? 'update' : null,
  }));
  assert.deepEqual(availableUpdateIds(catalogEntries(products, installed)), ['active', 'disabled']);
});
