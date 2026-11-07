import assert from 'node:assert/strict'
import { resetRegistry, setEnabled } from '../../src/plugins/registry.js'
import { registerBundledDescriptor } from './bundledDescriptors.mjs'
import { installRuntimeHost } from './runtimeHost.mjs'

/** Explicit owners, real manifests and the application's service graph. */
export function installPublicOwners(t, descriptors, { runtime = false } = {}) {
  if (runtime) installRuntimeHost(t)
  resetRegistry()
  for (const descriptor of descriptors) assert.equal(registerBundledDescriptor(descriptor), true)
  setEnabled(descriptors.map(descriptor => descriptor.id))
  t.after(resetRegistry)
}
