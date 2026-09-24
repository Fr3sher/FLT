import assert from 'node:assert/strict'
import { resetRegistry, setEnabled } from '../../src/plugins/registry.js'
import { registerBundledDescriptor } from './bundledDescriptors.mjs'
import { installRuntimeHost } from './runtimeHost.mjs'
import klein from '../../../bundled/image_upscale/frontend/index.js'
import seed from '../../../bundled/seedvr2/frontend/index.js'

export function installRestorationOwners(t, { runtime = false, ids = ['image_upscale', 'seedvr2'] } = {}) {
  if (runtime) installRuntimeHost(t)
  resetRegistry()
  for (const descriptor of [klein, seed]) assert.equal(registerBundledDescriptor(descriptor), true)
  setEnabled(ids)
  t.after(() => resetRegistry())
}
