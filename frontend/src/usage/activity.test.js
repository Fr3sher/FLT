import test from 'node:test'
import assert from 'node:assert/strict'
import { usageFeature, shouldSendUsageActivity } from './activity.js'

test('only coarse core features are returned; identifiers and search never leave the browser', () => {
  assert.equal(usageFeature('/dataset/studio/example-dataset?prompt=private#image'), 'studio')
  assert.equal(usageFeature('/plugins/example-plugin/settings'), 'plugins')
  assert.equal(usageFeature('/settings/maintenance'), 'settings')
  assert.equal(usageFeature('/guide/settings-reference'), 'guide')
  assert.equal(usageFeature('/datasets/?search=private'), 'datasets')
  assert.equal(usageFeature('/cloud'), 'training')
  assert.equal(usageFeature('/bank'), 'bank')
  assert.equal(usageFeature('/gallery'), 'gallery')
  assert.equal(usageFeature('/setup'), 'setup')
  for (const path of ['/unregistered-plugin/example', '/bankish', '/dataset/studio/a/b', undefined]) {
    assert.equal(usageFeature(path), null)
  }
})

test('an activity requires consent, an actual interaction and a visible document', () => {
  const active = { enabled: true, trusted: true, visible: true, feature: 'bank', now: 100_000 }
  assert.equal(shouldSendUsageActivity(active), true)
  for (const key of ['enabled', 'trusted', 'visible']) {
    assert.equal(shouldSendUsageActivity({ ...active, [key]: false }), false)
    assert.equal(shouldSendUsageActivity({ ...active, [key]: undefined }), false)
  }
  assert.equal(shouldSendUsageActivity({ ...active, feature: '/bank/private' }), false)
  assert.equal(shouldSendUsageActivity({ ...active, now: NaN }), false)
})

test('repeated interactions are throttled for a minute, including backwards clock changes', () => {
  const active = { enabled: true, trusted: true, visible: true, feature: 'studio', lastSent: 100_000 }
  assert.equal(shouldSendUsageActivity({ ...active, now: 159_999 }), false)
  assert.equal(shouldSendUsageActivity({ ...active, now: 160_000 }), true)
  assert.equal(shouldSendUsageActivity({ ...active, now: 90_000 }), false)
})
