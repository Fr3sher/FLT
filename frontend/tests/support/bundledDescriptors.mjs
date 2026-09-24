import { readFileSync } from 'node:fs'
import { registerDescriptor } from '../../src/plugins/registry.js'

// Keep public descriptor tests on the same guide ownership contract as loading
// an installed package. Deriving ownership from the descriptor would hide drift.
export function registerBundledDescriptor(descriptor) {
  if (!/^[a-z][a-z0-9_]{1,31}$/.test(descriptor?.id || '')) {
    throw new Error('A bundled fixture needs a valid public package id')
  }
  const manifest = JSON.parse(readFileSync(
    new URL(`../../../bundled/${descriptor.id}/plugin.json`, import.meta.url), 'utf8'))
  if (manifest.id !== descriptor.id) throw new Error('Bundled fixture manifest id differs')
  return registerDescriptor(descriptor, {
    guideOwnership: manifest.guide_ownership, pluginName: manifest.name,
  })
}
